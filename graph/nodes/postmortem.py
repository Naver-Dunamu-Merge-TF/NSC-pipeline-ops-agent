from __future__ import annotations

from typing import Any

from graph.state import AgentState

READ_FIELDS = (
    "incident_id",
    "pipeline",
    "detected_at",
    "triage_report",
    "action_plan",
    "human_decision",
    "human_decision_by",
    "human_decision_ts",
    "execution_result",
    "validation_results",
    "final_status",
)
WRITE_FIELDS = ("postmortem_report", "postmortem_generated_at")


def run(state: AgentState) -> dict[str, Any]:
    _ = state
    raise NotImplementedError("postmortem node is not implemented in this skeleton.")
