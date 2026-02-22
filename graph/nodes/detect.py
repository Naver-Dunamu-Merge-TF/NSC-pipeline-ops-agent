from __future__ import annotations

from typing import Any

from graph.state import AgentState

READ_FIELDS = ("incident_id", "pipeline", "run_id", "detected_at", "fingerprint")
WRITE_FIELDS = ("pipeline_states", "detected_issues")


def run(state: AgentState) -> dict[str, Any]:
    _ = state
    raise NotImplementedError("detect node is not implemented in this skeleton.")
