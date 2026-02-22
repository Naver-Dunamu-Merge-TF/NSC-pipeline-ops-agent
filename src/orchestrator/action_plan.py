from __future__ import annotations

from datetime import datetime


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
