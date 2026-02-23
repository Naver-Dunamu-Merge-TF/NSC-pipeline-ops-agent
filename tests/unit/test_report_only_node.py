from __future__ import annotations

import json
import logging
from typing import Any

from graph.nodes import report_only


def _base_state() -> dict[str, Any]:
    return {
        "incident_id": "inc-904x",
        "pipeline": "pipeline_silver",
        "detected_at": "2026-02-18T15:03:00Z",
        "detected_issues": [
            {
                "type": "cutoff_delay",
                "severity": "warning",
            }
        ],
        "pipeline_states": {
            "pipeline_silver": {
                "status": "late",
                "last_success_ts": "2026-02-18T14:03:00Z",
            }
        },
    }


def test_report_only_sets_reported_status_and_logs_deterministic_payload(
    caplog,
) -> None:
    state = _base_state()

    with caplog.at_level(logging.INFO, logger=report_only.__name__):
        result = report_only.run(state)

    assert result == {"final_status": "reported"}
    assert len(caplog.records) == 1
    assert caplog.records[0].message.startswith("report_only payload: ")

    payload = json.loads(caplog.records[0].message.split(": ", 1)[1])
    assert payload == {
        "incident_id": "inc-904x",
        "pipeline": "pipeline_silver",
        "report_artifact_storage": "log_only",
        "detected_issues": [{"severity": "warning", "type": "cutoff_delay"}],
        "major_status": {
            "detected_at_kst": "2026-02-19 00:03 KST",
            "last_success_kst": "2026-02-18 23:03 KST",
            "pipeline_status": "late",
        },
    }


def test_report_only_handles_empty_issues_and_missing_pipeline_states(caplog) -> None:
    state = _base_state()
    state["detected_issues"] = []
    del state["pipeline_states"]

    with caplog.at_level(logging.INFO, logger=report_only.__name__):
        result = report_only.run(state)

    assert result == {"final_status": "reported"}
    payload = json.loads(caplog.records[0].message.split(": ", 1)[1])
    assert payload == {
        "incident_id": "inc-904x",
        "pipeline": "pipeline_silver",
        "report_artifact_storage": "log_only",
        "detected_issues": [],
        "major_status": {
            "detected_at_kst": "2026-02-19 00:03 KST",
            "last_success_kst": None,
            "pipeline_status": "unknown",
        },
    }
