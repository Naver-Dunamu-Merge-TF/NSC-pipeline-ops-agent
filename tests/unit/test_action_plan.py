from __future__ import annotations

import pytest

from orchestrator.action_plan import (
    classify_action_plan_version,
    validate_action_plan,
    validate_action_plan_contract,
    validate_v2_plus_required_fields,
)


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


def test_classify_action_plan_version_defaults_to_v1_without_discriminator() -> None:
    version = classify_action_plan_version(
        {
            "action": "skip_and_report",
            "parameters": {
                "pipeline": "silver_orders",
                "reason": "source is still stale",
            },
        }
    )

    assert version == "v1"


def test_classify_action_plan_version_detects_v2_plus() -> None:
    version = classify_action_plan_version(
        {
            "schema_version": "v2",
            "action": "skip_and_report",
            "parameters": {
                "pipeline": "silver_orders",
                "reason": "source is still stale",
            },
        }
    )

    assert version == "v2_plus"


def test_classify_action_plan_version_rejects_explicit_v1_discriminator() -> None:
    with pytest.raises(ValueError, match="omit schema_version"):
        classify_action_plan_version(
            {
                "schema_version": "v1",
                "action": "skip_and_report",
                "parameters": {
                    "pipeline": "silver_orders",
                    "reason": "source is still stale",
                },
            }
        )


def test_classify_action_plan_version_rejects_invalid_discriminator_format() -> None:
    with pytest.raises(ValueError, match="must match"):
        classify_action_plan_version(
            {
                "schema_version": "2",
                "action": "skip_and_report",
                "parameters": {
                    "pipeline": "silver_orders",
                    "reason": "source is still stale",
                },
            }
        )


def test_validate_action_plan_contract_accepts_v1_without_schema_version() -> None:
    validate_action_plan_contract(
        {
            "action": "skip_and_report",
            "parameters": {
                "pipeline": "silver_orders",
                "reason": "source is still stale",
            },
        }
    )


def test_validate_action_plan_contract_accepts_v2_plus_with_optional_fields() -> None:
    validate_action_plan_contract(
        {
            "schema_version": "v2",
            "action": "skip_and_report",
            "parameters": {
                "pipeline": "silver_orders",
                "reason": "source is still stale",
            },
            "expected_outcome": "manual escalation continues",
            "caveats": ["wait for upstream fix"],
        }
    )


def test_validate_action_plan_contract_rejects_unknown_v2_plus_top_level_field() -> (
    None
):
    with pytest.raises(ValueError, match="Unexpected action_plan fields"):
        validate_action_plan_contract(
            {
                "schema_version": "v2",
                "action": "skip_and_report",
                "parameters": {
                    "pipeline": "silver_orders",
                    "reason": "source is still stale",
                },
                "operator_note": "not part of v2+ contract",
            }
        )


def test_validate_action_plan_contract_rejects_non_string_v2_plus_caveat_item() -> None:
    with pytest.raises(ValueError, match="action_plan.caveats"):
        validate_action_plan_contract(
            {
                "schema_version": "v2",
                "action": "skip_and_report",
                "parameters": {
                    "pipeline": "silver_orders",
                    "reason": "source is still stale",
                },
                "caveats": [1],
            }
        )


@pytest.mark.parametrize(
    ("field_to_remove", "expected_message"),
    [
        ("schema_version", "schema_version"),
        ("action", "action"),
        ("parameters", "parameters"),
    ],
)
def test_validate_v2_plus_required_fields_rejects_missing_field(
    field_to_remove: str, expected_message: str
) -> None:
    action_plan = {
        "schema_version": "v2",
        "action": "skip_and_report",
        "parameters": {
            "pipeline": "silver_orders",
            "reason": "source is still stale",
        },
    }
    del action_plan[field_to_remove]

    with pytest.raises(ValueError, match=expected_message):
        validate_v2_plus_required_fields(action_plan)


def test_v2_plus_compatibility_rejects_unknown_action_same_as_v1() -> None:
    v1_action_plan = {
        "action": "backfill_sliver",
        "parameters": {
            "pipeline": "silver_orders",
            "date_kst": "2026-02-23",
            "run_mode": "full",
        },
    }
    v2_action_plan = {
        "schema_version": "v2",
        "action": "backfill_sliver",
        "parameters": {
            "pipeline": "silver_orders",
            "date_kst": "2026-02-23",
            "run_mode": "full",
        },
    }

    with pytest.raises(ValueError, match="Allowed actions"):
        validate_action_plan(v1_action_plan["action"], v1_action_plan["parameters"])

    validate_action_plan_contract(v2_action_plan)
    with pytest.raises(ValueError, match="Allowed actions"):
        validate_action_plan(v2_action_plan["action"], v2_action_plan["parameters"])


def test_v2_plus_compatibility_rejects_missing_required_parameter_same_as_v1() -> None:
    v1_action_plan = {
        "action": "backfill_silver",
        "parameters": {
            "pipeline": "silver_orders",
            "date_kst": "2026-02-23",
        },
    }
    v2_action_plan = {
        "schema_version": "v2",
        "action": "backfill_silver",
        "parameters": {
            "pipeline": "silver_orders",
            "date_kst": "2026-02-23",
        },
    }

    with pytest.raises(ValueError, match="Missing required parameters"):
        validate_action_plan(v1_action_plan["action"], v1_action_plan["parameters"])

    validate_action_plan_contract(v2_action_plan)
    with pytest.raises(ValueError, match="Missing required parameters"):
        validate_action_plan(v2_action_plan["action"], v2_action_plan["parameters"])


def test_v2_plus_compatibility_accepts_valid_action_and_parameters() -> None:
    action_plan = {
        "schema_version": "v2",
        "action": "retry_pipeline",
        "parameters": {
            "pipeline": "silver_orders",
            "run_mode": "full",
        },
    }

    validate_action_plan_contract(action_plan)
    validate_action_plan(action_plan["action"], action_plan["parameters"])
