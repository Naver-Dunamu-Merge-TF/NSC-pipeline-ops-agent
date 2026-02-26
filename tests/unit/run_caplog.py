import pytest
from pathlib import Path
from http.client import HTTPMessage
from urllib.error import HTTPError
import json
import logging
from tools.llm_client import invoke_llm

def _env(db_path: Path, *, cap: str = "30") -> dict[str, str]:
    return {
        "LLM_DAILY_CAP": cap,
        "CHECKPOINT_DB_PATH": str(db_path),
    }

def test_debug(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)
    db_path = tmp_path / "checkpoints" / "agent.db"
    attempts = 0

    def requester(timeout_seconds: float) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise HTTPError(
                url="https://example.test",
                code=429,
                msg="too many requests",
                hdrs=HTTPMessage(),
                fp=None,
            )
        return '{"status":"ok"}'

    invoke_llm(
        requester,
        environ=_env(db_path),
        sleep=lambda _: None,
        response_parser=json.loads,
    )
    for r in caplog.records:
        print(f"Captured: {r.name}, {r.levelname}, {r.message}")

