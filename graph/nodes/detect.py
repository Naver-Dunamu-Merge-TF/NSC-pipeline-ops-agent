from __future__ import annotations

from typing import Any

from graph.state import AgentState

READ_FIELDS = ("incident_id", "pipeline", "run_id", "detected_at", "fingerprint")
WRITE_FIELDS = ("pipeline_states", "detected_issues")


def run(state: AgentState) -> dict[str, Any]:
    detected_issues = state.get("detected_issues")
    if detected_issues is None:
        detected_issues = []

    pipeline_states = state.get("pipeline_states")
    if pipeline_states is None:
        pipeline_states = {}

    return {
        "pipeline_states": pipeline_states,
        "detected_issues": detected_issues,
    }
