from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from sudocode_orchestrator.snapshot import emit_snapshot_json, validate_snapshot


def _valid_snapshot() -> dict[str, object]:
    return {
        "schema_version": "loop_snapshot.v1",
        "session_id": "123e4567-e89b-12d3-a456-426614174000",
        "orchestrator_id": "orch-1",
        "issue_id": "i-abc1",
        "task_id": "DEV-001",
        "event_type": "SESSION_START",
        "stage": "RUNNING",
        "status": "START",
        "attempts": {"spec": 1, "quality": 0},
        "failed_items": [],
        "fix_list": [],
        "verify": {
            "command": "python -m pytest tests/unit/test_snapshot.py -q",
            "exit_code": 0,
            "produced_at": datetime(
                2026, 2, 21, 12, 0, tzinfo=timezone.utc
            ).isoformat(),
        },
        "timestamp": datetime(2026, 2, 21, 12, 1, tzinfo=timezone.utc).isoformat(),
    }


def test_validate_snapshot_accepts_valid_payload() -> None:
    payload = _valid_snapshot()

    result = validate_snapshot(payload)

    assert result == payload


def test_validate_snapshot_rejects_invalid_schema_version() -> None:
    payload = _valid_snapshot()
    payload["schema_version"] = "loop_snapshot.v2"

    with pytest.raises(ValueError, match="schema_version"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_missing_required_field() -> None:
    payload = _valid_snapshot()
    del payload["issue_id"]

    with pytest.raises(ValueError, match="issue_id"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_invalid_enums() -> None:
    payload = _valid_snapshot()
    payload["event_type"] = "SOMETHING_ELSE"

    with pytest.raises(ValueError, match="event_type"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_incomplete_verify() -> None:
    payload = _valid_snapshot()
    payload["verify"] = {"command": "pytest", "exit_code": 0}

    with pytest.raises(ValueError, match="produced_at"):
        validate_snapshot(payload)


def test_validate_snapshot_allows_null_verify() -> None:
    payload = _valid_snapshot()
    payload["verify"] = None

    result = validate_snapshot(payload)

    assert result["verify"] is None


def test_validate_snapshot_rejects_invalid_verify_types() -> None:
    payload = _valid_snapshot()
    payload["verify"] = {
        "command": 12,
        "exit_code": 0,
        "produced_at": datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc).isoformat(),
    }

    with pytest.raises(ValueError, match="verify.command"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_unknown_top_level_field() -> None:
    payload = _valid_snapshot()
    payload["extra"] = "not-allowed"

    with pytest.raises(ValueError, match="Unknown top-level field"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_non_object_attempts() -> None:
    payload = _valid_snapshot()
    payload["attempts"] = 1

    with pytest.raises(ValueError, match="attempts"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_incomplete_attempts_object() -> None:
    payload = _valid_snapshot()
    payload["attempts"] = {"spec": 1}

    with pytest.raises(ValueError, match="attempts.quality"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_old_attempt_keys() -> None:
    payload = _valid_snapshot()
    payload["attempts"] = {"spec_review": 1, "quality_review": 0}

    with pytest.raises(ValueError, match="Unknown attempts field"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_non_string_failed_items() -> None:
    payload = _valid_snapshot()
    payload["failed_items"] = ["one", 2]

    with pytest.raises(ValueError, match="failed_items"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_non_string_fix_list() -> None:
    payload = _valid_snapshot()
    payload["fix_list"] = ["one", 2]

    with pytest.raises(ValueError, match="fix_list"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_non_string_required_top_level_field() -> None:
    payload = _valid_snapshot()
    payload["session_id"] = 123

    with pytest.raises(ValueError, match="session_id"):
        validate_snapshot(payload)


def test_validate_snapshot_allows_non_uuid_session_id_string() -> None:
    payload = _valid_snapshot()
    payload["session_id"] = "sess-20260221-001"

    result = validate_snapshot(payload)

    assert result["session_id"] == "sess-20260221-001"


def test_validate_snapshot_rejects_empty_session_id() -> None:
    payload = _valid_snapshot()
    payload["session_id"] = "   "

    with pytest.raises(ValueError, match="session_id"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_naive_timestamp() -> None:
    payload = _valid_snapshot()
    payload["timestamp"] = "2026-02-21T12:01:00"

    with pytest.raises(ValueError, match="timestamp"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_non_utc_timestamp() -> None:
    payload = _valid_snapshot()
    payload["timestamp"] = "2026-02-21T12:01:00+01:00"

    with pytest.raises(ValueError, match="timestamp"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_naive_verify_produced_at() -> None:
    payload = _valid_snapshot()
    payload["verify"] = {
        "command": "pytest tests/unit/test_snapshot.py -q",
        "exit_code": 0,
        "produced_at": "2026-02-21T12:00:00",
    }

    with pytest.raises(ValueError, match="verify.produced_at"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_bool_attempt_values() -> None:
    payload = _valid_snapshot()
    payload["attempts"] = {"spec": True, "quality": False}

    with pytest.raises(ValueError, match="attempts.spec"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_negative_attempt_spec() -> None:
    payload = _valid_snapshot()
    payload["attempts"] = {"spec": -1, "quality": 0}

    with pytest.raises(ValueError, match="attempts.spec"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_negative_attempt_quality() -> None:
    payload = _valid_snapshot()
    payload["attempts"] = {"spec": 1, "quality": -1}

    with pytest.raises(ValueError, match="attempts.quality"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_bool_verify_exit_code() -> None:
    payload = _valid_snapshot()
    payload["verify"] = {
        "command": "pytest tests/unit/test_snapshot.py -q",
        "exit_code": True,
        "produced_at": datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc).isoformat(),
    }

    with pytest.raises(ValueError, match="verify.exit_code"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_negative_verify_exit_code() -> None:
    payload = _valid_snapshot()
    payload["verify"] = {
        "command": "pytest tests/unit/test_snapshot.py -q",
        "exit_code": -1,
        "produced_at": datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc).isoformat(),
    }

    with pytest.raises(ValueError, match="verify.exit_code"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_malformed_verify_produced_at_with_space() -> None:
    payload = _valid_snapshot()
    payload["verify"] = {
        "command": "pytest tests/unit/test_snapshot.py -q",
        "exit_code": 0,
        "produced_at": "2026-02-21 12:00:00+00:00",
    }

    with pytest.raises(ValueError, match="verify.produced_at"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_malformed_verify_produced_at_invalid_month() -> None:
    payload = _valid_snapshot()
    payload["verify"] = {
        "command": "pytest tests/unit/test_snapshot.py -q",
        "exit_code": 0,
        "produced_at": "2026-13-21T12:00:00+00:00",
    }

    with pytest.raises(ValueError, match="verify.produced_at"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_unknown_verify_field() -> None:
    payload = _valid_snapshot()
    payload["verify"] = {
        "command": "pytest tests/unit/test_snapshot.py -q",
        "exit_code": 0,
        "produced_at": datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc).isoformat(),
        "stderr": "unexpected",
    }

    with pytest.raises(ValueError, match="Unknown verify field"):
        validate_snapshot(payload)


def test_validate_snapshot_rejects_non_utc_verify_produced_at() -> None:
    payload = _valid_snapshot()
    payload["verify"] = {
        "command": "pytest tests/unit/test_snapshot.py -q",
        "exit_code": 0,
        "produced_at": "2026-02-21T12:00:00+01:00",
    }

    with pytest.raises(ValueError, match="verify.produced_at"):
        validate_snapshot(payload)


def test_emit_snapshot_json_serializes_validated_payload() -> None:
    payload = _valid_snapshot()
    payload["verify"] = {
        "command": "pytest tests/unit/test_snapshot.py -q",
        "exit_code": 0,
        "produced_at": datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc).isoformat(),
        "output_ref": "s3://logs/sess-123.txt",
    }

    encoded = emit_snapshot_json(payload)
    decoded = json.loads(encoded)

    assert decoded["schema_version"] == "loop_snapshot.v1"
    assert decoded["verify"]["output_ref"] == "s3://logs/sess-123.txt"
