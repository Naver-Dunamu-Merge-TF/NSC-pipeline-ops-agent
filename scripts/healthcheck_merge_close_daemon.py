from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone


def _parse_iso8601(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


def _load_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return _load_json(path)


def _save_state(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")


def _coerce_int(value: object, *, default: int) -> int:
    if isinstance(value, int):
        return value
    return default


def evaluate_health(
    *,
    heartbeat_path: Path,
    state_path: Path,
    now_iso: str | None = None,
    heartbeat_max_age_seconds: int = 120,
    failure_budget: int = 3,
) -> dict[str, object]:
    now_dt = (
        _parse_iso8601(now_iso) if now_iso is not None else datetime.now(timezone.utc)
    )

    if not heartbeat_path.exists():
        return {
            "status": "unhealthy",
            "reason": "missing-heartbeat",
            "exit_code": 1,
            "consecutive_poll_failures": 0,
        }

    heartbeat = _load_json(heartbeat_path)
    updated_at = heartbeat.get("updated_at")
    poll_ok = heartbeat.get("poll_ok")
    safe_mode = heartbeat.get("safe_mode", False)

    if not isinstance(updated_at, str) or not isinstance(poll_ok, bool):
        return {
            "status": "unhealthy",
            "reason": "invalid-heartbeat",
            "exit_code": 1,
            "consecutive_poll_failures": 0,
        }

    heartbeat_dt = _parse_iso8601(updated_at)
    age_seconds = int((now_dt - heartbeat_dt).total_seconds())

    state = _load_state(state_path)
    previous_updated_at = state.get("last_heartbeat_updated_at")
    consecutive_poll_failures = _coerce_int(
        state.get("consecutive_poll_failures", 0), default=0
    )
    if previous_updated_at != updated_at:
        if poll_ok:
            consecutive_poll_failures = 0
        else:
            consecutive_poll_failures += 1
        _save_state(
            state_path,
            {
                "last_heartbeat_updated_at": updated_at,
                "consecutive_poll_failures": consecutive_poll_failures,
            },
        )

    if safe_mode:
        return {
            "status": "unhealthy",
            "reason": "safe-mode",
            "exit_code": 1,
            "heartbeat_age_seconds": age_seconds,
            "consecutive_poll_failures": consecutive_poll_failures,
        }

    if age_seconds > heartbeat_max_age_seconds:
        return {
            "status": "unhealthy",
            "reason": "stale-heartbeat",
            "exit_code": 1,
            "heartbeat_age_seconds": age_seconds,
            "consecutive_poll_failures": consecutive_poll_failures,
        }

    if consecutive_poll_failures >= max(1, failure_budget):
        return {
            "status": "degraded",
            "reason": "poll-failure-budget-exhausted",
            "exit_code": 0,
            "heartbeat_age_seconds": age_seconds,
            "consecutive_poll_failures": consecutive_poll_failures,
        }

    return {
        "status": "healthy",
        "reason": "ok",
        "exit_code": 0,
        "heartbeat_age_seconds": age_seconds,
        "consecutive_poll_failures": consecutive_poll_failures,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/healthcheck_merge_close_daemon.py",
        description="Healthcheck for merge-close daemon heartbeat and poll budget",
    )
    parser.add_argument(
        "--heartbeat-path",
        type=Path,
        default=Path(".runtime/merge-close-heartbeat.json"),
        help="Path to daemon heartbeat JSON file",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=Path(".runtime/merge-close-health-state.json"),
        help="Path for healthcheck state used for poll failure budget",
    )
    parser.add_argument(
        "--heartbeat-max-age-seconds",
        type=int,
        default=120,
        help="Maximum acceptable heartbeat age in seconds",
    )
    parser.add_argument(
        "--failure-budget",
        type=int,
        default=3,
        help="Consecutive poll failure budget before degraded status",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    result = evaluate_health(
        heartbeat_path=args.heartbeat_path,
        state_path=args.state_path,
        heartbeat_max_age_seconds=args.heartbeat_max_age_seconds,
        failure_budget=args.failure_budget,
    )
    print(json.dumps(result, sort_keys=True))
    return _coerce_int(result.get("exit_code"), default=1)


if __name__ == "__main__":
    raise SystemExit(main())
