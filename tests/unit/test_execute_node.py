from __future__ import annotations

from typing import Any

import pytest

from graph.nodes import execute


def _base_state() -> dict[str, Any]:
    return {
        "pipeline": "pipeline_silver",
        "action_plan": {
            "action": "skip_and_report",
            "parameters": {
                "pipeline": "pipeline_silver",
                "reason": "upstream stale source",
            },
        },
        "human_decision": "approve",
    }


def test_execute_requires_action_plan() -> None:
    state = _base_state()
    state["action_plan"] = None

    with pytest.raises(ValueError, match="action_plan is required"):
        execute.run(state)


def test_execute_requires_action_plan_to_be_dict() -> None:
    state = _base_state()
    state["action_plan"] = "skip_and_report"

    with pytest.raises(ValueError, match="action_plan must be a dict"):
        execute.run(state)


def test_execute_requires_action_key_in_action_plan() -> None:
    state = _base_state()
    state["action_plan"] = {
        "parameters": {
            "pipeline": "pipeline_silver",
            "reason": "upstream stale source",
        }
    }

    with pytest.raises(ValueError, match="action_plan.action is required"):
        execute.run(state)


def test_execute_requires_parameters_key_in_action_plan() -> None:
    state = _base_state()
    state["action_plan"] = {"action": "skip_and_report"}

    with pytest.raises(ValueError, match="action_plan.parameters is required"):
        execute.run(state)


def test_execute_requires_parameters_to_be_dict() -> None:
    state = _base_state()
    state["action_plan"] = {
        "action": "skip_and_report",
        "parameters": "not-a-dict",
    }

    with pytest.raises(ValueError, match="action_plan.parameters must be a dict"):
        execute.run(state)


def test_execute_rejects_explicit_v1_schema_version() -> None:
    state = _base_state()
    state["action_plan"]["schema_version"] = "v1"

    with pytest.raises(ValueError, match="omit schema_version"):
        execute.run(state)


def test_execute_rejects_v2_plus_action_plan_until_contract_is_extended() -> None:
    state = _base_state()
    state["action_plan"]["schema_version"] = "v2"

    with pytest.raises(ValueError, match=r"v2\+ ActionPlan is not supported"):
        execute.run(state)


def test_execute_requires_pipeline_in_state() -> None:
    state = _base_state()
    del state["pipeline"]

    with pytest.raises(ValueError, match="pipeline is required"):
        execute.run(state)


def test_execute_requires_approved_human_decision() -> None:
    state = _base_state()
    state["human_decision"] = "reject"

    with pytest.raises(ValueError, match="human_decision must be 'approve'"):
        execute.run(state)


def test_execute_skip_and_report_returns_skipped_without_job_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validate_calls: list[tuple[str, dict[str, object]]] = []
    job_calls: list[tuple[str, dict[str, Any]]] = []

    def _fake_validate(action: str, parameters: dict[str, object]) -> None:
        validate_calls.append((action, parameters))

    def _fake_run_job(action: str, parameters: dict[str, Any]) -> dict[str, Any]:
        job_calls.append((action, parameters))
        return {"status": "should_not_happen"}

    monkeypatch.setattr(execute, "validate_action_plan", _fake_validate)
    monkeypatch.setattr(execute.databricks_jobs, "run_databricks_job", _fake_run_job)

    result = execute.run(_base_state())

    assert validate_calls == [
        (
            "skip_and_report",
            {
                "pipeline": "pipeline_silver",
                "reason": "upstream stale source",
            },
        )
    ]
    assert job_calls == []
    assert result["pre_execute_table_version"] == {"pipeline": "pipeline_silver"}
    assert result["execution_result"] == {
        "status": "skipped",
        "action": "skip_and_report",
        "reason": "upstream stale source",
    }


@pytest.mark.parametrize("action", ["backfill_silver", "retry_pipeline"])
def test_execute_runs_databricks_job_for_executable_actions(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    parameters = {
        "pipeline": "pipeline_silver",
        "run_mode": "full",
    }
    if action == "backfill_silver":
        parameters["date_kst"] = "2026-02-23"

    state = _base_state()
    state["action_plan"] = {
        "action": action,
        "parameters": parameters,
    }

    validate_calls: list[tuple[str, dict[str, object]]] = []
    job_calls: list[tuple[str, dict[str, Any]]] = []

    def _fake_validate(
        validated_action: str, validated_parameters: dict[str, object]
    ) -> None:
        validate_calls.append((validated_action, validated_parameters))

    def _fake_run_job(
        job_action: str, job_parameters: dict[str, Any]
    ) -> dict[str, Any]:
        job_calls.append((job_action, job_parameters))
        return {"status": "submitted", "job_run_id": "123"}

    monkeypatch.setattr(execute, "validate_action_plan", _fake_validate)
    monkeypatch.setattr(execute.databricks_jobs, "run_databricks_job", _fake_run_job)

    result = execute.run(state)

    assert validate_calls == [(action, parameters)]
    assert job_calls == [(action, parameters)]
    assert result["pre_execute_table_version"] == {"pipeline": "pipeline_silver"}
    assert result["execution_result"] == {"status": "submitted", "job_run_id": "123"}
