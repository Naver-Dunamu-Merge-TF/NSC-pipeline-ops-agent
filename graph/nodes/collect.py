from __future__ import annotations

from typing import Any

from graph.state import AgentState

READ_FIELDS = ("pipeline", "run_id", "pipeline_states", "detected_issues")
WRITE_FIELDS = ("exceptions", "dq_tags", "bad_records_summary")


def run(state: AgentState) -> dict[str, Any]:
    _ = state
    raise NotImplementedError("collect node is not implemented in this skeleton.")
