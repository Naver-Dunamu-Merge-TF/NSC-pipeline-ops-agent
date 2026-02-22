from __future__ import annotations

from typing import Any

from graph.state import AgentState
from sudocode_orchestrator.action_plan import validate_action_plan
from tools import databricks_jobs

READ_FIELDS = ("action_plan", "human_decision", "pipeline")
WRITE_FIELDS = ("pre_execute_table_version", "execution_result")


def run(state: AgentState) -> dict[str, Any]:
    action_plan = state.get("action_plan")
    if action_plan is None:
        raise ValueError("action_plan is required")
    if not isinstance(action_plan, dict):
        raise ValueError("action_plan must be a dict")

    if "action" not in action_plan:
        raise ValueError("action_plan.action is required")
    if "parameters" not in action_plan:
        raise ValueError("action_plan.parameters is required")

    parameters = action_plan["parameters"]
    if not isinstance(parameters, dict):
        raise ValueError("action_plan.parameters must be a dict")

    pipeline = state.get("pipeline")
    if pipeline is None:
        raise ValueError("pipeline is required")

    if state.get("human_decision") != "approve":
        raise ValueError("human_decision must be 'approve'")

    action = action_plan["action"]
    validate_action_plan(action, parameters)

    pre_execute_table_version = {"pipeline": pipeline}

    if action == "skip_and_report":
        execution_result: dict[str, Any] = {
            "status": "skipped",
            "action": action,
            "reason": parameters["reason"],
        }
    else:
        execution_result = databricks_jobs.run_databricks_job(action, parameters)

    return {
        "pre_execute_table_version": pre_execute_table_version,
        "execution_result": execution_result,
    }
