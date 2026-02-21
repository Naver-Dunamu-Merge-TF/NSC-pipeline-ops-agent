from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Mapping, cast

SCHEMA_VERSION = "loop_snapshot.v1"

REQUIRED_FIELDS = {
    "schema_version",
    "session_id",
    "orchestrator_id",
    "issue_id",
    "task_id",
    "event_type",
    "stage",
    "status",
    "attempts",
    "failed_items",
    "fix_list",
    "verify",
    "timestamp",
}

EVENT_TYPES = {
    "SESSION_START",
    "IMPLEMENT_DONE",
    "SPEC_REVIEW_PASS",
    "SPEC_REVIEW_FAIL",
    "SPEC_FIX_APPLIED",
    "QUALITY_REVIEW_PASS",
    "QUALITY_REVIEW_FAIL",
    "QUALITY_FIX_APPLIED",
    "OVERFLOW_FIX_CREATED",
    "VERIFY_FAILED",
    "SESSION_DONE",
    "SESSION_ERROR",
}

STAGES = {
    "RUNNING",
    "SPEC_REVIEW",
    "SPEC_FIX",
    "QUALITY_REVIEW",
    "QUALITY_FIX",
    "VERIFICATION",
    "OVERFLOW",
    "DONE",
}

STATUSES = {
    "START",
    "PASS",
    "FAIL",
    "FIX_CREATED",
    "VERIFY_FAILED",
}

TOP_LEVEL_STRING_FIELDS = {
    "schema_version",
    "session_id",
    "orchestrator_id",
    "issue_id",
    "task_id",
    "event_type",
    "stage",
    "status",
    "timestamp",
}

ISO_8601_UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$"
)


def _parse_iso_utc(value: str, field_name: str) -> None:
    if ISO_8601_UTC_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Invalid {field_name}: must be ISO-8601 UTC string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: must be ISO-8601 UTC string") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"Invalid {field_name}: must be ISO-8601 UTC string")
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"Invalid {field_name}: must be ISO-8601 UTC string")


def _is_strict_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_snapshot(snapshot: Mapping[str, object]) -> dict[str, object]:
    payload = dict(snapshot)
    unknown_fields = sorted(set(payload) - REQUIRED_FIELDS)
    if unknown_fields:
        raise ValueError(f"Unknown top-level field(s): {', '.join(unknown_fields)}")

    missing_fields = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing_fields:
        raise ValueError(
            f"Missing required field(s): {', '.join(sorted(missing_fields))}"
        )

    for field_name in TOP_LEVEL_STRING_FIELDS:
        if not isinstance(payload[field_name], str):
            raise ValueError(f"Invalid {field_name}: must be str")

    schema_version = payload["schema_version"]
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"Invalid schema_version: expected {SCHEMA_VERSION}")

    if not cast(str, payload["session_id"]).strip():
        raise ValueError("Invalid session_id: must be non-empty string")

    event_type = payload["event_type"]
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Invalid event_type: {event_type}")

    stage = payload["stage"]
    if stage not in STAGES:
        raise ValueError(f"Invalid stage: {stage}")

    status = payload["status"]
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")

    attempts = payload["attempts"]
    if not isinstance(attempts, Mapping):
        raise ValueError("Invalid attempts: must be object")

    attempts_payload = dict(attempts)
    attempts_keys = {"spec", "quality"}
    unknown_attempt_keys = sorted(set(attempts_payload) - attempts_keys)
    if unknown_attempt_keys:
        raise ValueError(
            f"Unknown attempts field(s): {', '.join(unknown_attempt_keys)}"
        )

    for field_name in ("spec", "quality"):
        if field_name not in attempts_payload:
            raise ValueError(f"Missing attempts.{field_name}")
        if not _is_strict_int(attempts_payload[field_name]):
            raise ValueError(f"Invalid attempts.{field_name}: must be int")
        if attempts_payload[field_name] < 0:
            raise ValueError(f"Invalid attempts.{field_name}: must be >= 0")

    for field_name in ("failed_items", "fix_list"):
        field_value = payload[field_name]
        if not isinstance(field_value, list):
            raise ValueError(f"Invalid {field_name}: must be list")
        for item in field_value:
            if not isinstance(item, str):
                raise ValueError(f"Invalid {field_name}: must be list[str]")

    _parse_iso_utc(cast(str, payload["timestamp"]), "timestamp")

    verify = payload["verify"]
    if verify is None:
        payload["attempts"] = attempts_payload
        payload["verify"] = None
        return payload

    if not isinstance(verify, Mapping):
        raise ValueError("Invalid verify: must be object")

    verify_payload = dict(verify)
    unknown_verify_fields = sorted(
        set(verify_payload) - {"command", "exit_code", "produced_at", "output_ref"}
    )
    if unknown_verify_fields:
        raise ValueError(f"Unknown verify field(s): {', '.join(unknown_verify_fields)}")

    for field_name in ("command", "exit_code", "produced_at"):
        if field_name not in verify_payload:
            raise ValueError(f"Missing verify.{field_name}")

    if not isinstance(verify_payload["command"], str):
        raise ValueError("Invalid verify.command: must be str")
    if not _is_strict_int(verify_payload["exit_code"]):
        raise ValueError("Invalid verify.exit_code: must be int")
    if verify_payload["exit_code"] < 0:
        raise ValueError("Invalid verify.exit_code: must be >= 0")
    if not isinstance(verify_payload["produced_at"], str):
        raise ValueError("Invalid verify.produced_at: must be ISO-8601 string")
    _parse_iso_utc(verify_payload["produced_at"], "verify.produced_at")

    if "output_ref" in verify_payload and not isinstance(
        verify_payload["output_ref"], str
    ):
        raise ValueError("Invalid verify.output_ref: must be str")

    payload["attempts"] = attempts_payload
    payload["verify"] = verify_payload
    return payload


def emit_snapshot_json(snapshot: Mapping[str, object]) -> str:
    validated = validate_snapshot(snapshot)
    return json.dumps(validated, sort_keys=True)
