from __future__ import annotations

import json
import logging
from typing import Any

from graph.state import AgentState
from utils import time as time_utils

READ_FIELDS = (
    "incident_id",
    "pipeline",
    "detected_at",
    "detected_issues",
    "pipeline_states",
)
WRITE_FIELDS = ("final_status",)

LOGGER = logging.getLogger(__name__)


def _normalize_issue(issue: Any) -> Any:
    return json.loads(json.dumps(issue, sort_keys=True, ensure_ascii=True))


def run(state: AgentState) -> dict[str, Any]:
    detected_issues = state.get("detected_issues") or []
    pipeline_states = state.get("pipeline_states") or {}
    pipeline = state.get("pipeline")
    pipeline_state = (
        pipeline_states.get(pipeline, {}) if isinstance(pipeline_states, dict) else {}
    )
    detected_at = state.get("detected_at")

    payload = {
        "incident_id": state.get("incident_id"),
        "pipeline": pipeline,
        "report_artifact_storage": "log_only",
        "detected_issues": [_normalize_issue(issue) for issue in detected_issues],
        "major_status": {
            "detected_at_kst": time_utils.to_kst(detected_at) if detected_at else None,
            "last_success_kst": (
                time_utils.to_kst(pipeline_state["last_success_ts"])
                if isinstance(pipeline_state, dict)
                and pipeline_state.get("last_success_ts")
                else None
            ),
            "pipeline_status": (
                pipeline_state.get("status", "unknown")
                if isinstance(pipeline_state, dict)
                else "unknown"
            ),
        },
    }
    LOGGER.info(
        "report_only payload: %s",
        json.dumps(payload, sort_keys=True, ensure_ascii=True),
    )

    return {"final_status": "reported"}
