from __future__ import annotations

from typing import Any

from sudocode_orchestrator.databricks_jobs_config import load_databricks_jobs_config


_SUPPORTED_ACTIONS = {"backfill_silver", "retry_pipeline"}


def run_databricks_job(action: str, parameters: dict[str, Any]) -> dict[str, Any]:
    if action not in _SUPPORTED_ACTIONS:
        raise ValueError(f"Unsupported action: {action}")

    pipeline = parameters.get("pipeline")
    if not isinstance(pipeline, str) or not pipeline:
        raise ValueError("parameters.pipeline is required")

    execute_mode = parameters.get("execute_mode", "dry_run")
    if execute_mode != "dry_run":
        raise ValueError(f"Unsupported execute_mode: {execute_mode}")

    config = load_databricks_jobs_config()
    pipeline_job_config = getattr(config.jobs, pipeline, None)
    refresh_job_id = getattr(pipeline_job_config, "refresh", None)
    if not isinstance(refresh_job_id, int):
        raise ValueError(f"Unknown pipeline: {pipeline}")

    return {
        "status": execute_mode,
        "action": action,
        "pipeline": pipeline,
        "job_id": refresh_job_id,
        "parameters": parameters,
    }


def check_job_status(job_run_id: str) -> dict[str, Any]:
    _ = job_run_id
    raise NotImplementedError("Job status checks are not implemented in this skeleton.")
