from __future__ import annotations

from typing import get_type_hints, is_typeddict

from pydantic import BaseModel

from graph.state import ActionPlan, AgentState, TriageReport


def test_action_plan_fields_match_spec() -> None:
    assert is_typeddict(ActionPlan)
    assert issubclass(ActionPlan, dict)
    assert set(get_type_hints(ActionPlan)) == {
        "action",
        "parameters",
        "expected_outcome",
        "caveats",
    }


def test_triage_report_fields_match_spec() -> None:
    assert issubclass(TriageReport, BaseModel)
    assert set(TriageReport.model_fields) == {
        "summary",
        "failure_ts",
        "root_causes",
        "impact",
        "proposed_action",
        "expected_outcome",
        "caveats",
    }


def test_agent_state_fields_match_spec() -> None:
    assert is_typeddict(AgentState)
    assert issubclass(AgentState, dict)
    assert set(get_type_hints(AgentState)) == {
        "incident_id",
        "pipeline",
        "run_id",
        "detected_at",
        "fingerprint",
        "fingerprint_duplicate",
        "pipeline_states",
        "detected_issues",
        "exceptions",
        "dq_tags",
        "bad_records_summary",
        "dq_analysis",
        "triage_report",
        "triage_report_raw",
        "action_plan",
        "approval_requested_ts",
        "human_decision",
        "human_decision_by",
        "human_decision_ts",
        "modified_params",
        "execution_result",
        "validation_results",
        "pre_execute_table_version",
        "final_status",
        "postmortem_report",
        "postmortem_generated_at",
    }
