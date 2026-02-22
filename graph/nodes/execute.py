from __future__ import annotations

from typing import Any

from graph.state import AgentState

READ_FIELDS = ("action_plan", "human_decision", "pipeline")
WRITE_FIELDS = ("pre_execute_table_version", "execution_result")


def run(state: AgentState) -> dict[str, Any]:
    _ = state
    raise NotImplementedError("execute node is not implemented in this skeleton.")
