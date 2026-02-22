from __future__ import annotations

from typing import Any


def run_databricks_job(action: str, parameters: dict[str, Any]) -> dict[str, Any]:
    _ = (action, parameters)
    raise NotImplementedError(
        "Databricks job execution is not implemented in this skeleton."
    )


def check_job_status(job_run_id: str) -> dict[str, Any]:
    _ = job_run_id
    raise NotImplementedError("Job status checks are not implemented in this skeleton.")
