from __future__ import annotations

import importlib


NODE_EXPECTATIONS = {
    "detect": (
        (
            "incident_id",
            "pipeline",
            "run_id",
            "detected_at",
            "fingerprint",
            "fingerprint_duplicate",
        ),
        ("pipeline_states", "detected_issues"),
    ),
    "collect": (
        ("pipeline", "run_id", "pipeline_states", "detected_issues"),
        ("exceptions", "dq_tags", "bad_records_summary"),
    ),
    "report_only": (
        (
            "incident_id",
            "pipeline",
            "detected_at",
            "detected_issues",
            "pipeline_states",
        ),
        ("final_status",),
    ),
    "analyze": (
        ("bad_records_summary", "pipeline"),
        ("dq_analysis",),
    ),
    "triage": (
        (
            "dq_analysis",
            "exceptions",
            "dq_tags",
            "pipeline_states",
            "pipeline",
            "detected_at",
        ),
        ("triage_report", "triage_report_raw", "action_plan"),
    ),
    "propose": (
        ("triage_report", "action_plan", "incident_id", "modified_params"),
        ("approval_requested_ts",),
    ),
    "execute": (
        ("action_plan", "human_decision", "pipeline"),
        ("pre_execute_table_version", "execution_result"),
    ),
    "verify": (
        ("execution_result", "action_plan", "pre_execute_table_version", "pipeline"),
        ("validation_results", "final_status"),
    ),
    "rollback": (
        ("pre_execute_table_version", "validation_results", "pipeline"),
        ("execution_result", "final_status"),
    ),
    "postmortem": (
        (
            "incident_id",
            "pipeline",
            "detected_at",
            "triage_report",
            "action_plan",
            "human_decision",
            "human_decision_by",
            "human_decision_ts",
            "execution_result",
            "validation_results",
            "final_status",
        ),
        ("postmortem_report", "postmortem_generated_at"),
    ),
}


def test_skeleton_modules_are_importable() -> None:
    importlib.import_module("graph")
    importlib.import_module("graph.graph")
    importlib.import_module("graph.state")
    importlib.import_module("graph.nodes")
    importlib.import_module("tools")
    importlib.import_module("tools.alerting")
    importlib.import_module("tools.data_collector")
    importlib.import_module("tools.databricks_jobs")
    importlib.import_module("tools.domain_validator")
    importlib.import_module("utils")
    importlib.import_module("utils.time")
    importlib.import_module("llmops")
    importlib.import_module("llmops.eval_runner")
    importlib.import_module("llmops.prompt_registry")


def test_node_stubs_expose_read_write_contracts() -> None:
    for node_name, expected in NODE_EXPECTATIONS.items():
        module = importlib.import_module(f"graph.nodes.{node_name}")
        assert module.READ_FIELDS == expected[0]
        assert module.WRITE_FIELDS == expected[1]
        assert callable(module.run)
