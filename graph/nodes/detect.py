from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from graph.state import AgentState
from src.orchestrator.pipeline_monitoring_config import load_pipeline_monitoring_config
from src.orchestrator.utils.time import parse_pipeline_ts

READ_FIELDS = ("incident_id", "pipeline", "run_id", "detected_at", "fingerprint")
WRITE_FIELDS = ("pipeline_states", "detected_issues")

_LOGGER = logging.getLogger(__name__)
_CRITICAL_DQ_TAGS = {"SOURCE_STALE", "EVENT_DROP_SUSPECTED"}


def _has_pipeline_failure(state: dict[str, Any], pipeline: str | None) -> bool:
    if pipeline is None:
        return False
    pipeline_states = state.get("pipeline_states")
    if not isinstance(pipeline_states, dict):
        return False
    current = pipeline_states.get(pipeline)
    return isinstance(current, dict) and current.get("status") == "failure"


def _has_new_critical_exception(state: dict[str, Any]) -> bool:
    ledger = state.get("exception_ledger")
    if not isinstance(ledger, list):
        return False
    for row in ledger:
        if not isinstance(row, dict):
            continue
        if row.get("domain") != "dq":
            continue
        if row.get("severity") != "CRITICAL":
            continue
        if row.get("is_new", True) is False:
            continue
        return True
    return False


def _has_critical_dq_anomaly(state: dict[str, Any]) -> bool:
    dq_rows = state.get("dq_status")
    if not isinstance(dq_rows, list):
        return False
    for row in dq_rows:
        if not isinstance(row, dict):
            continue
        if row.get("severity") != "CRITICAL":
            continue
        if row.get("dq_tag") not in _CRITICAL_DQ_TAGS:
            continue
        return True
    return False


def _is_cutoff_delay(state: dict[str, Any], pipeline: str | None) -> bool:
    if pipeline is None:
        return False
    pipeline_states = state.get("pipeline_states")
    if not isinstance(pipeline_states, dict):
        return False
    current = pipeline_states.get(pipeline)
    if not isinstance(current, dict):
        return False

    detected_at = state.get("detected_at")
    last_success_ts = current.get("last_success_ts")
    if not isinstance(detected_at, str) or not isinstance(last_success_ts, str):
        return False

    config = load_pipeline_monitoring_config()
    pipeline_config = getattr(config.pipelines, pipeline, None)
    if pipeline_config is None:
        return False

    delay = parse_pipeline_ts(detected_at) - parse_pipeline_ts(last_success_ts)
    threshold = timedelta(minutes=pipeline_config.cutoff_delay_minutes)
    return delay > threshold


def run(state: AgentState) -> dict[str, Any]:
    working_state = dict(state)
    pipeline = working_state.get("pipeline")

    pipeline_states = working_state.get("pipeline_states")
    if not isinstance(pipeline_states, dict):
        pipeline_states = {}

    if bool(working_state.get("fingerprint_duplicate")):
        _LOGGER.info("detect heartbeat: duplicate fingerprint skip")
        return {
            "pipeline_states": pipeline_states,
            "detected_issues": [],
        }

    detected_issues: list[dict[str, str]] = []

    if _has_pipeline_failure(
        working_state, pipeline if isinstance(pipeline, str) else None
    ):
        detected_issues.append({"type": "failure", "severity": "critical"})

    if _has_new_critical_exception(working_state):
        detected_issues.append({"type": "new_exception", "severity": "critical"})

    if _has_critical_dq_anomaly(working_state):
        detected_issues.append({"type": "critical_dq", "severity": "critical"})

    if _is_cutoff_delay(working_state, pipeline if isinstance(pipeline, str) else None):
        detected_issues.append({"type": "cutoff_delay", "severity": "warning"})

    if not detected_issues:
        _LOGGER.info("detect heartbeat: normal")

    return {
        "pipeline_states": pipeline_states,
        "detected_issues": detected_issues,
    }
