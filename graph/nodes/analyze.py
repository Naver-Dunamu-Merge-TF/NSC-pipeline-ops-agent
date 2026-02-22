from __future__ import annotations

from typing import Any

from graph.state import AgentState

READ_FIELDS = ("bad_records_summary", "pipeline")
WRITE_FIELDS = ("dq_analysis",)


def run(state: AgentState) -> dict[str, Any]:
    _ = state
    raise NotImplementedError("analyze node is not implemented in this skeleton.")
