from __future__ import annotations

from typing import Any

from graph.state import AgentState

READ_FIELDS = ("triage_report", "action_plan", "incident_id", "modified_params")
WRITE_FIELDS = ("approval_requested_ts",)


def run(state: AgentState) -> dict[str, Any]:
    _ = state
    raise NotImplementedError("propose node is not implemented in this skeleton.")
