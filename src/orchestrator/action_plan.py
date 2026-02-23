from __future__ import annotations

from datetime import datetime
import re


ACTION_PARAMETER_SCHEMA: dict[str, dict[str, type]] = {
    "backfill_silver": {
        "pipeline": str,
        "date_kst": str,
        "run_mode": str,
    },
    "retry_pipeline": {
        "pipeline": str,
        "run_mode": str,
    },
    "skip_and_report": {
        "pipeline": str,
        "reason": str,
    },
}

ACTION_PLAN_VERSION_FIELD = "schema_version"
_VERSION_DISCRIMINATOR_PATTERN = re.compile(r"^v([1-9][0-9]*)$")
_V2_PLUS_REQUIRED_FIELDS = frozenset(
    {"action", "parameters", ACTION_PLAN_VERSION_FIELD}
)
_V2_PLUS_OPTIONAL_FIELD_TYPES: dict[str, type] = {
    "expected_outcome": str,
    "caveats": list,
}


def classify_action_plan_version(action_plan: dict[str, object]) -> str:
    raw_version = action_plan.get(ACTION_PLAN_VERSION_FIELD)
    if raw_version is None:
        return "v1"

    if not isinstance(raw_version, str):
        raise ValueError(
            "action_plan.schema_version must be a string matching 'v<major>'"
        )

    match = _VERSION_DISCRIMINATOR_PATTERN.fullmatch(raw_version)
    if match is None:
        raise ValueError("action_plan.schema_version must match 'v<major>'")

    major = int(match.group(1))
    if major == 1:
        raise ValueError("action_plan v1 must omit schema_version")

    return "v2_plus"


def validate_action_plan(action: str, parameters: dict[str, object]) -> None:
    if action not in ACTION_PARAMETER_SCHEMA:
        allowed = ", ".join(sorted(ACTION_PARAMETER_SCHEMA))
        raise ValueError(f"Invalid action '{action}'. Allowed actions: {allowed}")

    expected_schema = ACTION_PARAMETER_SCHEMA[action]
    missing = sorted(key for key in expected_schema if key not in parameters)
    if missing:
        missing_names = ", ".join(missing)
        raise ValueError(
            f"Missing required parameters for action '{action}': {missing_names}"
        )

    unexpected = sorted(key for key in parameters if key not in expected_schema)
    if unexpected:
        unexpected_names = ", ".join(unexpected)
        raise ValueError(
            f"Unexpected parameters for action '{action}': {unexpected_names}"
        )

    invalid_types: list[str] = []
    for key, expected_type in expected_schema.items():
        value = parameters[key]
        if not isinstance(value, expected_type):
            invalid_types.append(
                f"{key} must be {expected_type.__name__}, got {type(value).__name__}"
            )
    if invalid_types:
        raise ValueError(
            f"Invalid parameter types for action '{action}': {'; '.join(invalid_types)}"
        )

    if action == "backfill_silver":
        _validate_date_kst(parameters["date_kst"])


def validate_action_plan_contract(action_plan: dict[str, object]) -> None:
    action_plan_version = classify_action_plan_version(action_plan)
    if action_plan_version != "v2_plus":
        return

    validate_v2_plus_required_fields(action_plan)

    allowed_fields = _V2_PLUS_REQUIRED_FIELDS | set(_V2_PLUS_OPTIONAL_FIELD_TYPES)
    unexpected = sorted(field for field in action_plan if field not in allowed_fields)
    if unexpected:
        unexpected_names = ", ".join(unexpected)
        raise ValueError(f"Unexpected action_plan fields for v2+: {unexpected_names}")

    expected_outcome = action_plan.get("expected_outcome")
    if expected_outcome is not None and not isinstance(expected_outcome, str):
        raise ValueError("action_plan.expected_outcome must be a string")

    caveats = action_plan.get("caveats")
    if caveats is not None:
        if not isinstance(caveats, list) or not all(
            isinstance(caveat, str) for caveat in caveats
        ):
            raise ValueError("action_plan.caveats must be a list[str]")


def validate_v2_plus_required_fields(action_plan: dict[str, object]) -> None:
    missing = sorted(
        field for field in _V2_PLUS_REQUIRED_FIELDS if field not in action_plan
    )
    if missing:
        missing_names = ", ".join(missing)
        raise ValueError(
            f"Missing required action_plan fields for v2+: {missing_names}"
        )

    return


def _validate_date_kst(date_kst: object) -> None:
    if not isinstance(date_kst, str):
        raise ValueError("date_kst must be YYYY-MM-DD")
    try:
        parsed = datetime.strptime(date_kst, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("date_kst must be YYYY-MM-DD") from exc
    normalized = parsed.strftime("%Y-%m-%d")
    if normalized != date_kst:
        raise ValueError("date_kst must be YYYY-MM-DD")
