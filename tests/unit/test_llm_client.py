from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPMessage
from pathlib import Path
from types import TracebackType
from typing import Any
from datetime import datetime, timezone
from urllib.error import HTTPError

import pytest

from tools import llm_client
from tools.llm_client import (
    LLMDailyCapExceeded,
    LLMPermanentError,
    invoke_llm,
)


def _env(db_path: Path, *, cap: str = "30") -> dict[str, str]:
    return {
        "LLM_DAILY_CAP": cap,
        "CHECKPOINT_DB_PATH": str(db_path),
    }


def test_invoke_llm_retries_429_with_exponential_backoff(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    caplog.set_level(logging.INFO)
    db_path = tmp_path / "checkpoints" / "agent.db"
    attempts = 0
    delays: list[float] = []

    def requester(timeout_seconds: float) -> str:
        nonlocal attempts
        assert timeout_seconds == 60.0
        attempts += 1
        if attempts < 4:
            raise HTTPError(
                url="https://example.test",
                code=429,
                msg="too many requests",
                hdrs=HTTPMessage(),
                fp=None,
            )
        return '{"status":"ok"}'

    result = invoke_llm(
        requester,
        environ=_env(db_path),
        sleep=delays.append,
        response_parser=json.loads,
    )

    assert result == {"status": "ok"}
    assert attempts == 4
    assert delays == [2.0, 4.0, 8.0]

    assert "Starting LLM logical invocation" in caplog.text
    assert "Starting LLM HTTP attempt 1" in caplog.text
    assert "Starting LLM HTTP attempt 2" in caplog.text
    assert "Starting LLM HTTP attempt 3" in caplog.text
    assert "Starting LLM HTTP attempt 4" in caplog.text


def test_invoke_llm_retries_retryable_response_status_codes(tmp_path: Path) -> None:
    db_path = tmp_path / "checkpoints" / "agent.db"
    attempts = 0
    delays: list[float] = []

    class Response:
        def __init__(self, status: int, body: str) -> None:
            self.status = status
            self.body = body

    def requester(timeout_seconds: float) -> Response:
        nonlocal attempts
        assert timeout_seconds == 60.0
        attempts += 1
        if attempts < 3:
            return Response(status=500, body='{"status":"retry"}')
        return Response(status=200, body='{"status":"ok"}')

    result = invoke_llm(
        requester,
        environ=_env(db_path),
        sleep=delays.append,
        response_parser=lambda response: json.loads(response.body),
    )

    assert result == {"status": "ok"}
    assert attempts == 3
    assert delays == [2.0, 4.0]


def test_invoke_llm_retries_retryable_http_error_status_codes(tmp_path: Path) -> None:
    db_path = tmp_path / "checkpoints" / "agent.db"
    attempts = 0
    delays: list[float] = []

    def requester(timeout_seconds: float) -> str:
        nonlocal attempts
        assert timeout_seconds == 60.0
        attempts += 1
        if attempts < 3:
            raise HTTPError(
                url="https://example.test",
                code=503,
                msg="service unavailable",
                hdrs=HTTPMessage(),
                fp=None,
            )
        return '{"status":"ok"}'

    result = invoke_llm(
        requester,
        environ=_env(db_path),
        sleep=delays.append,
        response_parser=json.loads,
    )

    assert result == {"status": "ok"}
    assert attempts == 3
    assert delays == [2.0, 4.0]


def test_invoke_llm_does_not_retry_permanent_http_failure(tmp_path: Path) -> None:
    db_path = tmp_path / "checkpoints" / "agent.db"
    attempts = 0

    def requester(timeout_seconds: float) -> str:
        del timeout_seconds
        nonlocal attempts
        attempts += 1
        raise HTTPError(
            url="https://example.test",
            code=401,
            msg="unauthorized",
            hdrs=HTTPMessage(),
            fp=None,
        )

    with pytest.raises(LLMPermanentError):
        invoke_llm(requester, environ=_env(db_path), response_parser=json.loads)

    assert attempts == 1


def test_invoke_llm_raises_explicit_error_when_daily_cap_is_reached(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "checkpoints" / "agent.db"
    calls = 0

    def requester(timeout_seconds: float) -> str:
        del timeout_seconds
        nonlocal calls
        calls += 1
        return '{"status":"ok"}'

    invoke_llm(requester, environ=_env(db_path, cap="1"), response_parser=json.loads)

    with pytest.raises(LLMDailyCapExceeded):
        invoke_llm(
            requester, environ=_env(db_path, cap="1"), response_parser=json.loads
        )

    assert calls == 1


def test_consume_daily_budget_resets_at_midnight_kst(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "checkpoints" / "agent.db"

    current_time = datetime(2026, 1, 1, 14, 59, tzinfo=timezone.utc)

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            if tz is None:
                return current_time
            return current_time.astimezone(tz)

    monkeypatch.setattr(llm_client, "datetime", FakeDateTime)

    first_result = llm_client._consume_daily_budget(str(db_path), daily_cap=1)

    current_time = datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc)
    second_result = llm_client._consume_daily_budget(str(db_path), daily_cap=1)

    assert first_result is True
    assert second_result is True


def test_consume_daily_budget_is_atomic_for_concurrent_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "checkpoints" / "agent.db"
    barrier = threading.Barrier(2)
    original_connect = llm_client.sqlite3.connect

    class ConnectionProxy:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self._conn = conn

        def __enter__(self) -> "ConnectionProxy":
            self._conn.__enter__()
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool:
            return self._conn.__exit__(exc_type, exc, tb)

        def execute(self, sql: str, params: Any = ()) -> Any:
            normalized = " ".join(sql.split())
            if normalized.startswith("INSERT INTO llm_daily_usage"):
                barrier.wait(timeout=5)
            return self._conn.execute(sql, params)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._conn, name)

    def connect_proxy(*args: Any, **kwargs: Any) -> ConnectionProxy:
        return ConnectionProxy(original_connect(*args, **kwargs))

    monkeypatch.setattr(llm_client.sqlite3, "connect", connect_proxy)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                llm_client._consume_daily_budget,
                str(db_path),
                daily_cap=1,
            )
            for _ in range(2)
        ]
        results = [future.result() for future in futures]

    assert sorted(results) == [False, True]
