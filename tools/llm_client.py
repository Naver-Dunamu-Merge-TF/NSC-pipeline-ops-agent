from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib import error

REQUEST_TIMEOUT_SECONDS = 60.0
RETRY_DELAYS_SECONDS = (2.0, 4.0, 8.0)
RETRYABLE_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
DEFAULT_LLM_DAILY_CAP = 30
DEFAULT_CHECKPOINT_DB_PATH = "checkpoints/agent.db"
KST = timezone(timedelta(hours=9))


class LLMError(RuntimeError):
    pass


class LLMTransientError(LLMError):
    pass


class LLMPermanentError(LLMError):
    pass


class LLMDailyCapExceeded(LLMError):
    pass


def invoke_llm(
    requester: Callable[[float], Any],
    *,
    environ: Mapping[str, str] | None = None,
    checkpoint_db_path: str | None = None,
    response_parser: Callable[[Any], Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    env = environ if environ is not None else os.environ
    daily_cap = _parse_daily_cap(env.get("LLM_DAILY_CAP"))
    db_path = checkpoint_db_path or env.get(
        "CHECKPOINT_DB_PATH", DEFAULT_CHECKPOINT_DB_PATH
    )

    if not _consume_daily_budget(db_path, daily_cap=daily_cap):
        raise LLMDailyCapExceeded(
            f"LLM daily cap reached: {daily_cap} requests for {_today_kst_key()}"
        )

    for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
        try:
            response = requester(REQUEST_TIMEOUT_SECONDS)
            status = getattr(response, "status", None)
            if status is not None:
                status_code = int(status)
                if not (200 <= status_code < 300):
                    if status_code in RETRYABLE_HTTP_STATUS_CODES:
                        raise LLMTransientError(f"http status {status_code}")
                    if status_code in {401, 403, 404}:
                        raise LLMPermanentError(f"http status {status_code}")
                    raise LLMPermanentError(f"http status {status_code}")

            if response_parser is None:
                return response

            try:
                return response_parser(response)
            except (TypeError, ValueError) as exc:
                raise LLMPermanentError("response parse/validation failure") from exc
        except Exception as exc:
            classified = _classify_error(exc)
            if isinstance(classified, LLMTransientError) and attempt < len(
                RETRY_DELAYS_SECONDS
            ):
                sleep(RETRY_DELAYS_SECONDS[attempt])
                continue
            if classified is exc:
                raise classified
            raise classified from exc

    raise LLMTransientError("retry attempts exhausted")


def _classify_error(exc: Exception) -> LLMError:
    if isinstance(exc, LLMError):
        return exc
    if isinstance(exc, error.HTTPError):
        if exc.code in RETRYABLE_HTTP_STATUS_CODES:
            return LLMTransientError(f"http status {exc.code}")
        if exc.code in {401, 403, 404}:
            return LLMPermanentError(f"http status {exc.code}")
        return LLMPermanentError(f"http status {exc.code}")
    if isinstance(exc, (TimeoutError, ConnectionError, error.URLError)):
        return LLMTransientError(str(exc).strip() or exc.__class__.__name__)
    return LLMPermanentError(str(exc).strip() or exc.__class__.__name__)


def _parse_daily_cap(raw: str | None) -> int:
    if raw is None or not raw.strip():
        return DEFAULT_LLM_DAILY_CAP
    try:
        cap = int(raw)
    except ValueError as exc:
        raise LLMPermanentError("LLM_DAILY_CAP must be an integer") from exc
    if cap <= 0:
        raise LLMPermanentError("LLM_DAILY_CAP must be a positive integer")
    return cap


def _consume_daily_budget(db_path: str, *, daily_cap: int) -> bool:
    _ensure_parent_dir(db_path)
    date_key = _today_kst_key()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_daily_usage (
                day_key TEXT PRIMARY KEY,
                request_count INTEGER NOT NULL
            )
            """
        )
        cursor = conn.execute(
            """
            INSERT INTO llm_daily_usage(day_key, request_count)
            VALUES (?, 1)
            ON CONFLICT(day_key) DO UPDATE
            SET request_count = llm_daily_usage.request_count + 1
            WHERE llm_daily_usage.request_count < ?
            """,
            (date_key, daily_cap),
        )
        return cursor.rowcount == 1


def _today_kst_key() -> str:
    return datetime.now(KST).date().isoformat()


def _ensure_parent_dir(db_path: str) -> None:
    if db_path == ":memory:":
        return
    Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


__all__ = [
    "DEFAULT_LLM_DAILY_CAP",
    "LLMDailyCapExceeded",
    "LLMError",
    "LLMPermanentError",
    "LLMTransientError",
    "REQUEST_TIMEOUT_SECONDS",
    "invoke_llm",
]
