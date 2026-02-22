from __future__ import annotations

from typing import Any, Optional, TypedDict

from pydantic import BaseModel, ConfigDict


class _SpecModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionPlan(TypedDict):
    action: str
    parameters: dict[str, Any]
    expected_outcome: str
    caveats: list[str]


class TriageReport(_SpecModel):
    summary: str
    failure_ts: str
    root_causes: list[dict[str, Any]]
    impact: list[dict[str, Any]]
    proposed_action: dict[str, Any]
    expected_outcome: str
    caveats: list[str]


class AgentState(TypedDict):
    incident_id: str
    pipeline: str
    run_id: Optional[str]
    detected_at: str
    fingerprint: Optional[str]

    pipeline_states: dict[str, Any]
    detected_issues: list[Any]

    exceptions: list[Any]
    dq_tags: list[Any]
    bad_records_summary: dict[str, Any]

    dq_analysis: Optional[str]
    triage_report: Optional[dict[str, Any]]
    triage_report_raw: Optional[str]

    action_plan: Optional[ActionPlan]
    approval_requested_ts: Optional[str]
    human_decision: Optional[str]
    human_decision_by: Optional[str]
    human_decision_ts: Optional[str]
    modified_params: Optional[dict[str, Any]]

    execution_result: Optional[dict[str, Any]]
    validation_results: Optional[dict[str, Any]]
    pre_execute_table_version: Optional[dict[str, Any]]
    final_status: Optional[str]

    postmortem_report: Optional[str]
    postmortem_generated_at: Optional[str]
