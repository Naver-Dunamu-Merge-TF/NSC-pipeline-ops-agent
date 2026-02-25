from __future__ import annotations

from typing import Any

from graph.nodes import detect


def _base_state() -> dict[str, Any]:
    return {
        "incident_id": "inc-016",
        "pipeline": "pipeline_silver",
        "run_id": "run-016",
        "detected_at": "2026-02-18T15:40:00+00:00",
        "fingerprint": "fp-016",
        "pipeline_states": {
            "pipeline_silver": {
                "status": "success",
                "last_success_ts": "2026-02-18T15:10:00+00:00",
            }
        },
        "exception_ledger": [],
        "dq_status": [],
    }


def test_detect_classifies_trigger_priority_in_spec_order() -> None:
    state = _base_state()
    state["pipeline_states"]["pipeline_silver"]["status"] = "failure"
    state["pipeline_states"]["pipeline_silver"]["last_success_ts"] = (
        "2026-02-18T14:30:00+00:00"
    )
    state["exception_ledger"] = [
        {
            "domain": "dq",
            "severity": "CRITICAL",
            "exception_type": "SchemaViolation",
        }
    ]
    state["dq_status"] = [
        {
            "severity": "CRITICAL",
            "dq_tag": "SOURCE_STALE",
            "source_table": "bronze.orders",
        }
    ]

    result = detect.run(state)

    assert [issue["type"] for issue in result["detected_issues"]] == [
        "failure",
        "new_exception",
        "critical_dq",
        "cutoff_delay",
    ]


def test_detect_identifies_cutoff_delay_only_scenario() -> None:
    state = _base_state()
    state["pipeline_states"]["pipeline_silver"]["last_success_ts"] = (
        "2026-02-18T15:09:59+00:00"
    )

    result = detect.run(state)

    assert result["detected_issues"] == [
        {"type": "cutoff_delay", "severity": "warning"}
    ]


def test_detect_identifies_failure_only_scenario() -> None:
    state = _base_state()
    state["pipeline_states"]["pipeline_silver"]["status"] = "failure"

    result = detect.run(state)

    assert result["detected_issues"] == [{"type": "failure", "severity": "critical"}]


def test_detect_identifies_critical_dq_only_scenario() -> None:
    state = _base_state()
    state["dq_status"] = [
        {
            "severity": "CRITICAL",
            "dq_tag": "SOURCE_STALE",
            "source_table": "bronze.orders",
        }
    ]

    result = detect.run(state)

    assert result["detected_issues"] == [
        {"type": "critical_dq", "severity": "critical"}
    ]


def test_detect_identifies_new_exception_only_scenario() -> None:
    state = _base_state()
    state["exception_ledger"] = [
        {
            "domain": "dq",
            "severity": "CRITICAL",
            "exception_type": "SchemaViolation",
            "is_new": True,
        }
    ]

    result = detect.run(state)

    assert result["detected_issues"] == [
        {"type": "new_exception", "severity": "critical"}
    ]


def test_detect_cutoff_delay_boundary_is_strictly_greater_than_threshold() -> None:
    state = _base_state()
    state["detected_at"] = "2026-02-18T15:40:00+00:00"
    state["pipeline_states"]["pipeline_silver"]["last_success_ts"] = (
        "2026-02-18T15:10:00+00:00"
    )

    equal_threshold = detect.run(state)
    assert [issue["type"] for issue in equal_threshold["detected_issues"]] == []

    state["pipeline_states"]["pipeline_silver"]["last_success_ts"] = (
        "2026-02-18T15:09:59+00:00"
    )
    greater_than_threshold = detect.run(state)
    assert [issue["type"] for issue in greater_than_threshold["detected_issues"]] == [
        "cutoff_delay"
    ]


def test_detect_dq_trigger_requires_critical_not_warn() -> None:
    state = _base_state()
    state["dq_status"] = [
        {
            "severity": "WARN",
            "dq_tag": "SOURCE_STALE",
        }
    ]

    warn_only = detect.run(state)
    assert [issue["type"] for issue in warn_only["detected_issues"]] == []

    state["dq_status"] = [
        {
            "severity": "CRITICAL",
            "dq_tag": "SOURCE_STALE",
        }
    ]
    critical = detect.run(state)
    assert [issue["type"] for issue in critical["detected_issues"]] == ["critical_dq"]


def test_detect_duplicate_fingerprint_skips_immediately() -> None:
    state = _base_state()
    state["fingerprint_duplicate"] = True
    state["pipeline_states"]["pipeline_silver"]["status"] = "failure"
    state["exception_ledger"] = [{"domain": "dq", "severity": "CRITICAL"}]
    state["dq_status"] = [{"severity": "CRITICAL", "dq_tag": "SOURCE_STALE"}]

    result = detect.run(state)

    assert result["detected_issues"] == []
