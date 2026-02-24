from __future__ import annotations

import json
import socket
import time
from typing import Any
from urllib import error, parse, request

from orchestrator.databricks_jobs_config import load_databricks_jobs_config
from utils.secrets import get_secret


_SUPPORTED_ACTIONS = {"backfill_silver", "retry_pipeline"}
_SUPPORTED_EXECUTE_MODES = {"dry-run", "live"}
_RUN_NOW_TIMEOUT_SECONDS = 20.0
_STATUS_TIMEOUT_SECONDS = 10.0
_TIMEOUT_RETRY_DELAY_SECONDS = 5.0
_API_5XX_RETRY_DELAY_SECONDS = 10.0
_MAX_TIMEOUT_RETRIES = 2
_MAX_5XX_RETRIES = 2


class _DatabricksHttpError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def run_databricks_job(action: str, parameters: dict[str, Any]) -> dict[str, Any]:
    if action not in _SUPPORTED_ACTIONS:
        raise ValueError(f"Unsupported action: {action}")

    pipeline = parameters.get("pipeline")
    if not isinstance(pipeline, str) or not pipeline:
        raise ValueError("parameters.pipeline is required")

    execute_mode = _resolve_execute_mode(parameters)

    config = load_databricks_jobs_config()
    pipeline_job_config = getattr(config.jobs, pipeline, None)
    refresh_job_id = getattr(pipeline_job_config, "refresh", None)
    if not isinstance(refresh_job_id, int):
        raise ValueError(f"Unknown pipeline: {pipeline}")

    if execute_mode == "dry-run":
        return {
            "status": "dry_run",
            "action": action,
            "pipeline": pipeline,
            "job_id": refresh_job_id,
            "parameters": parameters,
        }

    base_url, token = _load_databricks_auth()
    timeout_retries_left = _MAX_TIMEOUT_RETRIES
    api_5xx_retries_left = _MAX_5XX_RETRIES

    while True:
        try:
            payload = _http_json_request(
                method="POST",
                url=f"{base_url}/api/2.1/jobs/run-now",
                token=token,
                payload={"job_id": refresh_job_id},
                timeout_seconds=_RUN_NOW_TIMEOUT_SECONDS,
            )
            run_id = payload.get("run_id")
            if run_id is None:
                raise RuntimeError("Databricks run-now response missing run_id")
            return {
                "status": "submitted",
                "action": action,
                "pipeline": pipeline,
                "job_id": refresh_job_id,
                "job_run_id": str(run_id),
            }
        except TimeoutError as exc:
            try:
                active_run_id = _find_active_run_id_for_job(
                    base_url=base_url,
                    token=token,
                    job_id=refresh_job_id,
                )
            except Exception:
                active_run_id = None
            if active_run_id is not None:
                return {
                    "status": "submitted",
                    "action": action,
                    "pipeline": pipeline,
                    "job_id": refresh_job_id,
                    "job_run_id": active_run_id,
                }
            if timeout_retries_left <= 0:
                raise RuntimeError(
                    "Databricks run-now timed out after retries"
                ) from exc
            timeout_retries_left -= 1
            time.sleep(_TIMEOUT_RETRY_DELAY_SECONDS)
        except Exception as exc:
            if not _is_http_5xx_error(exc):
                raise
            try:
                active_run_id = _find_active_run_id_for_job(
                    base_url=base_url,
                    token=token,
                    job_id=refresh_job_id,
                )
            except Exception:
                active_run_id = None
            if active_run_id is not None:
                return {
                    "status": "submitted",
                    "action": action,
                    "pipeline": pipeline,
                    "job_id": refresh_job_id,
                    "job_run_id": active_run_id,
                }
            if api_5xx_retries_left <= 0:
                raise RuntimeError(
                    "Databricks run-now failed with 5xx after retries"
                ) from exc
            api_5xx_retries_left -= 1
            time.sleep(_API_5XX_RETRY_DELAY_SECONDS)


def check_job_status(job_run_id: str) -> dict[str, Any]:
    run_id = str(job_run_id).strip()
    if not run_id:
        raise ValueError("job_run_id is required")

    execute_mode = _resolve_execute_mode({})
    if execute_mode == "dry-run":
        return {
            "status": "dry_run",
            "job_run_id": run_id,
            "life_cycle_state": "UNKNOWN",
            "result_state": None,
        }

    base_url, token = _load_databricks_auth()
    query = parse.urlencode({"run_id": run_id})
    payload = _http_json_request(
        method="GET",
        url=f"{base_url}/api/2.1/jobs/runs/get?{query}",
        token=token,
        timeout_seconds=_STATUS_TIMEOUT_SECONDS,
    )
    raw_state = payload.get("state")
    state: dict[str, Any] = raw_state if isinstance(raw_state, dict) else {}
    life_cycle_state = str(state.get("life_cycle_state") or "UNKNOWN")
    result_state = state.get("result_state")

    return {
        "status": _map_lifecycle_to_status(life_cycle_state),
        "job_run_id": run_id,
        "life_cycle_state": life_cycle_state,
        "result_state": result_state,
    }


def _resolve_execute_mode(parameters: dict[str, Any]) -> str:
    raw_mode = parameters.get("execute_mode")
    if raw_mode is None:
        raw_mode = get_secret("agent-execute-mode")
    normalized = str(raw_mode).strip().lower().replace("_", "-")
    if normalized not in _SUPPORTED_EXECUTE_MODES:
        raise ValueError(f"Unsupported execute_mode: {raw_mode}")
    return normalized


def _load_databricks_auth() -> tuple[str, str]:
    raw_base_url = get_secret("databricks-host")
    raw_token = get_secret("databricks-agent-token")
    base_url = raw_base_url.strip().rstrip("/") if isinstance(raw_base_url, str) else ""
    token = raw_token.strip() if isinstance(raw_token, str) else ""
    if not base_url:
        raise ValueError("Missing databricks-host secret")
    if not token:
        raise ValueError("Missing databricks-agent-token secret")
    return base_url, token


def _find_active_run_id_for_job(
    *, base_url: str, token: str, job_id: int
) -> str | None:
    query = parse.urlencode(
        {"job_id": job_id, "active_only": "true", "limit": 1},
    )
    payload = _http_json_request(
        method="GET",
        url=f"{base_url}/api/2.1/jobs/runs/list?{query}",
        token=token,
        timeout_seconds=_STATUS_TIMEOUT_SECONDS,
    )
    runs = payload.get("runs")
    if not isinstance(runs, list) or not runs:
        return None
    first_run = runs[0]
    if not isinstance(first_run, dict):
        return None
    run_id = first_run.get("run_id")
    if run_id is None:
        return None
    return str(run_id)


def _http_json_request(
    *,
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float,
) -> dict[str, Any]:
    data: bytes | None = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method=method, headers=headers)

    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise _DatabricksHttpError(
            f"Databricks API error status={exc.code}: {detail or exc.reason}",
            status_code=exc.code,
        ) from exc
    except (error.URLError, socket.timeout, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        reason_text = str(reason).lower()
        if "timed out" in reason_text or isinstance(
            exc, (socket.timeout, TimeoutError)
        ):
            raise TimeoutError("Databricks request timed out") from exc
        raise _DatabricksHttpError(f"Databricks request failed: {reason}") from exc

    if not raw_body:
        return {}
    decoded = json.loads(raw_body)
    if not isinstance(decoded, dict):
        raise RuntimeError("Databricks response must be a JSON object")
    return decoded


def _is_http_5xx_error(exc: Exception) -> bool:
    return (
        isinstance(exc, _DatabricksHttpError)
        and exc.status_code is not None
        and 500 <= exc.status_code < 600
    )


def _map_lifecycle_to_status(life_cycle_state: str) -> str:
    if life_cycle_state in {"PENDING", "RUNNING", "QUEUED", "TERMINATING"}:
        return "running"
    if life_cycle_state == "TERMINATED":
        return "finished"
    if life_cycle_state in {"SKIPPED", "INTERNAL_ERROR"}:
        return "failed"
    return "unknown"
