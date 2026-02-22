from __future__ import annotations

from typing import Any

from graph.state import AgentState

READ_FIELDS = ("pre_execute_table_version", "validation_results", "pipeline")
WRITE_FIELDS = ("execution_result", "final_status")


def run(state: AgentState) -> dict[str, Any]:
    _ = state
    raise NotImplementedError("rollback node is not implemented in this skeleton.")
