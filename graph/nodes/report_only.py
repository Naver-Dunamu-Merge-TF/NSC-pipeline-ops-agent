from __future__ import annotations

from typing import Any

from graph.state import AgentState

READ_FIELDS = ("detected_issues", "pipeline_states")
WRITE_FIELDS = ("final_status",)


def run(state: AgentState) -> dict[str, Any]:
    _ = state
    raise NotImplementedError("report_only node is not implemented in this skeleton.")
