from __future__ import annotations

import pytest

from orchestrator.action_plan import validate_action_plan


def test_validate_action_plan_rejects_unknown_action() -> None:
    with pytest.raises(ValueError, match="Allowed actions"):
        validate_action_plan("backfill_sliver", {"pipeline": "silver_orders"})


def test_validate_action_plan_rejects_missing_required_parameter() -> None:
    with pytest.raises(ValueError, match="Missing required parameters"):
        validate_action_plan(
            "backfill_silver",
            {
                "pipeline": "silver_orders",
                "date_kst": "2026-02-23",
            },
        )


def test_validate_action_plan_rejects_forbidden_extra_parameter() -> None:
    with pytest.raises(ValueError, match="Unexpected parameters"):
        validate_action_plan(
            "retry_pipeline",
            {
                "pipeline": "silver_orders",
                "run_mode": "full",
                "date_kst": "2026-02-23",
            },
        )


def test_validate_action_plan_rejects_invalid_date_kst_format() -> None:
    with pytest.raises(ValueError, match="date_kst must be YYYY-MM-DD"):
        validate_action_plan(
            "backfill_silver",
            {
                "pipeline": "silver_orders",
                "date_kst": "2026/02/23",
                "run_mode": "full",
            },
        )


def test_validate_action_plan_rejects_invalid_parameter_types() -> None:
    with pytest.raises(ValueError, match="Invalid parameter types"):
        validate_action_plan(
            "backfill_silver",
            {
                "pipeline": "silver_orders",
                "date_kst": "2026-02-23",
                "run_mode": 1,
            },
        )


def test_validate_action_plan_accepts_valid_backfill_silver_payload() -> None:
    validate_action_plan(
        "backfill_silver",
        {
            "pipeline": "silver_orders",
            "date_kst": "2026-02-23",
            "run_mode": "full",
        },
    )


def test_validate_action_plan_accepts_skip_and_report_schema() -> None:
    validate_action_plan(
        "skip_and_report",
        {
            "pipeline": "silver_orders",
            "reason": "source is still stale",
        },
    )
