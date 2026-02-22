from __future__ import annotations

from typing import Any

from graph.state import AgentState

READ_FIELDS = (
    "execution_result",
    "action_plan",
    "pre_execute_table_version",
    "pipeline",
)
WRITE_FIELDS = ("validation_results", "final_status")


def run(state: AgentState) -> dict[str, Any]:
    _ = state
    raise NotImplementedError("verify node is not implemented in this skeleton.")
