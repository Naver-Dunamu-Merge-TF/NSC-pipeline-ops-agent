from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType


def _load_script_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "healthcheck_merge_close_daemon.py"
    )
    spec = importlib.util.spec_from_file_location(
        "healthcheck_merge_close_daemon", script_path
    )
    if spec is None or spec.loader is None:
        raise AssertionError("failed to load healthcheck_merge_close_daemon.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script_module()


def _write_heartbeat(path: Path, *, updated_at: str, poll_ok: bool = True) -> None:
    path.write_text(
        json.dumps(
            {
                "updated_at": updated_at,
                "poll_ok": poll_ok,
                "safe_mode": False,
            }
        ),
        encoding="utf-8",
    )


def test_healthcheck_fails_when_heartbeat_is_stale(tmp_path: Path) -> None:
    heartbeat = tmp_path / "heartbeat.json"
    state = tmp_path / "state.json"
    _write_heartbeat(heartbeat, updated_at="2026-02-22T11:58:00Z", poll_ok=True)

    result = SCRIPT.evaluate_health(
        heartbeat_path=heartbeat,
        state_path=state,
        now_iso="2026-02-22T12:00:30Z",
        heartbeat_max_age_seconds=120,
        failure_budget=3,
    )

    assert result["status"] == "unhealthy"
    assert result["exit_code"] == 1
    assert result["reason"] == "stale-heartbeat"


def test_healthcheck_degrades_when_failure_budget_is_exhausted(tmp_path: Path) -> None:
    heartbeat = tmp_path / "heartbeat.json"
    state = tmp_path / "state.json"

    _write_heartbeat(heartbeat, updated_at="2026-02-22T12:00:00Z", poll_ok=False)
    SCRIPT.evaluate_health(
        heartbeat_path=heartbeat,
        state_path=state,
        now_iso="2026-02-22T12:00:05Z",
        heartbeat_max_age_seconds=120,
        failure_budget=2,
    )

    _write_heartbeat(heartbeat, updated_at="2026-02-22T12:00:30Z", poll_ok=False)
    result = SCRIPT.evaluate_health(
        heartbeat_path=heartbeat,
        state_path=state,
        now_iso="2026-02-22T12:00:35Z",
        heartbeat_max_age_seconds=120,
        failure_budget=2,
    )

    assert result["status"] == "degraded"
    assert result["exit_code"] == 0
    assert result["reason"] == "poll-failure-budget-exhausted"
    assert result["consecutive_poll_failures"] == 2


def test_healthcheck_passes_when_heartbeat_fresh_and_poll_healthy(
    tmp_path: Path,
) -> None:
    heartbeat = tmp_path / "heartbeat.json"
    state = tmp_path / "state.json"
    _write_heartbeat(heartbeat, updated_at="2026-02-22T12:00:00Z", poll_ok=True)

    result = SCRIPT.evaluate_health(
        heartbeat_path=heartbeat,
        state_path=state,
        now_iso="2026-02-22T12:00:10Z",
        heartbeat_max_age_seconds=120,
        failure_budget=3,
    )

    assert result["status"] == "healthy"
    assert result["exit_code"] == 0
    assert result["reason"] == "ok"
    assert result["consecutive_poll_failures"] == 0
