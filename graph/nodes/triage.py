from __future__ import annotations

from typing import Any

from graph.state import AgentState

READ_FIELDS = (
    "dq_analysis",
    "exceptions",
    "dq_tags",
    "pipeline_states",
    "pipeline",
    "detected_at",
)
WRITE_FIELDS = ("triage_report", "triage_report_raw", "action_plan")


def run(state: AgentState) -> dict[str, Any]:
    _ = state
    raise NotImplementedError("triage node is not implemented in this skeleton.")
