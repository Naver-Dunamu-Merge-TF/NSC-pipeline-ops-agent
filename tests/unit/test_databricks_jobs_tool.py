from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tools.databricks_jobs import (
    _DatabricksHttpError,
    check_job_status,
    run_databricks_job,
)


def _fake_jobs_config() -> SimpleNamespace:
    return SimpleNamespace(
        jobs=SimpleNamespace(
            pipeline_silver=SimpleNamespace(refresh=101001),
            pipeline_b=SimpleNamespace(refresh=101002),
            pipeline_c=SimpleNamespace(refresh=101003),
            pipeline_a=SimpleNamespace(refresh=101004),
        )
    )


@pytest.fixture(autouse=True)
def _patch_default_execute_mode_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_get_secret(key: str) -> str:
        if key == "agent-execute-mode":
            return "dry-run"
        raise AssertionError(f"Unexpected secret lookup: {key}")

    monkeypatch.setattr("tools.databricks_jobs.get_secret", _fake_get_secret)


def test_run_databricks_job_resolves_refresh_job_id_from_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    result = run_databricks_job(
        "backfill_silver",
        {
            "pipeline": "pipeline_silver",
            "date_kst": "2026-02-23",
            "run_mode": "full",
        },
    )

    assert result == {
        "status": "dry_run",
        "action": "backfill_silver",
        "pipeline": "pipeline_silver",
        "job_id": 101001,
        "parameters": {
            "pipeline": "pipeline_silver",
            "date_kst": "2026-02-23",
            "run_mode": "full",
        },
    }


def test_run_databricks_job_allows_retry_pipeline_and_resolves_job_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    result = run_databricks_job(
        "retry_pipeline",
        {
            "pipeline": "pipeline_b",
        },
    )

    assert result["job_id"] == 101002


def test_run_databricks_job_rejects_unsupported_action() -> None:
    with pytest.raises(ValueError, match="Unsupported action"):
        run_databricks_job("skip_and_report", {"pipeline": "pipeline_silver"})


def test_run_databricks_job_rejects_missing_pipeline_parameter() -> None:
    with pytest.raises(ValueError, match="parameters.pipeline is required"):
        run_databricks_job("backfill_silver", {"date_kst": "2026-02-23"})


def test_run_databricks_job_rejects_unknown_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    with pytest.raises(ValueError, match="Unknown pipeline: pipeline_x"):
        run_databricks_job("retry_pipeline", {"pipeline": "pipeline_x"})


@pytest.mark.parametrize("pipeline", ["__class__", "model_dump"])
def test_run_databricks_job_rejects_attribute_collision_pipeline_values(
    monkeypatch: pytest.MonkeyPatch,
    pipeline: str,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    with pytest.raises(ValueError, match=rf"Unknown pipeline: {pipeline}"):
        run_databricks_job("retry_pipeline", {"pipeline": pipeline})


def test_run_databricks_job_rejects_unsupported_execute_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    with pytest.raises(ValueError, match="Unsupported execute_mode: execute"):
        run_databricks_job(
            "retry_pipeline",
            {"pipeline": "pipeline_b", "execute_mode": "execute"},
        )


def test_run_databricks_job_dry_run_does_not_call_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    def _should_not_be_called(*_: object, **__: object) -> dict[str, Any]:
        raise AssertionError("HTTP call must not happen in dry-run")

    monkeypatch.setattr(
        "tools.databricks_jobs._http_json_request", _should_not_be_called
    )

    result = run_databricks_job("retry_pipeline", {"pipeline": "pipeline_b"})

    assert result["status"] == "dry_run"


def test_run_databricks_job_live_calls_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    calls: list[tuple[str, str, dict[str, Any]]] = []

    def _fake_get_secret(key: str) -> str:
        if key == "agent-execute-mode":
            return "live"
        if key == "databricks-host":
            return "https://adb.example.com"
        if key == "databricks-agent-token":
            return "token"
        raise AssertionError(f"Unexpected secret lookup: {key}")

    def _fake_http_json_request(
        *,
        method: str,
        url: str,
        token: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        calls.append((method, url, payload or {}))
        assert token == "token"
        assert timeout_seconds > 0
        return {"run_id": 998877}

    monkeypatch.setattr("tools.databricks_jobs.get_secret", _fake_get_secret)
    monkeypatch.setattr(
        "tools.databricks_jobs._http_json_request",
        _fake_http_json_request,
    )

    result = run_databricks_job("retry_pipeline", {"pipeline": "pipeline_b"})

    assert result["status"] == "submitted"
    assert result["job_run_id"] == "998877"
    assert calls == [
        (
            "POST",
            "https://adb.example.com/api/2.1/jobs/run-now",
            {"job_id": 101002},
        )
    ]


def test_run_databricks_job_live_uses_databricks_host_secret_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    looked_up_secret_keys: list[str] = []

    def _fake_get_secret(key: str) -> str:
        looked_up_secret_keys.append(key)
        if key == "agent-execute-mode":
            return "live"
        if key == "databricks-host":
            return "https://adb.example.com"
        if key == "databricks-agent-token":
            return "token"
        raise AssertionError(f"Unexpected secret lookup: {key}")

    def _fake_http_json_request(
        *,
        method: str,
        url: str,
        token: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        _ = method, url, token, payload, timeout_seconds
        return {"run_id": 998877}

    monkeypatch.setattr("tools.databricks_jobs.get_secret", _fake_get_secret)
    monkeypatch.setattr(
        "tools.databricks_jobs._http_json_request",
        _fake_http_json_request,
    )

    run_databricks_job("retry_pipeline", {"pipeline": "pipeline_b"})

    assert looked_up_secret_keys == [
        "agent-execute-mode",
        "databricks-host",
        "databricks-agent-token",
    ]


def test_run_databricks_job_retries_5xx_after_status_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    sleep_calls: list[float] = []
    request_urls: list[str] = []

    def _fake_get_secret(key: str) -> str:
        if key == "agent-execute-mode":
            return "live"
        if key == "databricks-host":
            return "https://adb.example.com"
        if key == "databricks-agent-token":
            return "token"
        raise AssertionError(f"Unexpected secret lookup: {key}")

    responses = iter(
        [
            _DatabricksHttpError(
                "Databricks API error status=503: temporary",
                status_code=503,
            ),
            {"runs": []},
            {"run_id": 777},
        ]
    )

    def _fake_http_json_request(
        *,
        method: str,
        url: str,
        token: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        _ = method, token, payload, timeout_seconds
        request_urls.append(url)
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("tools.databricks_jobs.get_secret", _fake_get_secret)
    monkeypatch.setattr(
        "tools.databricks_jobs._http_json_request",
        _fake_http_json_request,
    )
    monkeypatch.setattr("tools.databricks_jobs.time.sleep", sleep_calls.append)

    result = run_databricks_job("retry_pipeline", {"pipeline": "pipeline_b"})

    assert result["status"] == "submitted"
    assert result["job_run_id"] == "777"
    assert request_urls == [
        "https://adb.example.com/api/2.1/jobs/run-now",
        "https://adb.example.com/api/2.1/jobs/runs/list?job_id=101002&active_only=true&limit=1",
        "https://adb.example.com/api/2.1/jobs/run-now",
    ]
    assert sleep_calls == [10.0]


def test_run_databricks_job_retries_when_active_run_lookup_fails_after_5xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    sleep_calls: list[float] = []
    request_urls: list[str] = []

    def _fake_get_secret(key: str) -> str:
        if key == "agent-execute-mode":
            return "live"
        if key == "databricks-host":
            return "https://adb.example.com"
        if key == "databricks-agent-token":
            return "token"
        raise AssertionError(f"Unexpected secret lookup: {key}")

    responses = iter(
        [
            _DatabricksHttpError(
                "Databricks API error status=503: temporary",
                status_code=503,
            ),
            RuntimeError("runs/list failed"),
            {"run_id": 888},
        ]
    )

    def _fake_http_json_request(
        *,
        method: str,
        url: str,
        token: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        _ = method, token, payload, timeout_seconds
        request_urls.append(url)
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("tools.databricks_jobs.get_secret", _fake_get_secret)
    monkeypatch.setattr(
        "tools.databricks_jobs._http_json_request",
        _fake_http_json_request,
    )
    monkeypatch.setattr("tools.databricks_jobs.time.sleep", sleep_calls.append)

    result = run_databricks_job("retry_pipeline", {"pipeline": "pipeline_b"})

    assert result["status"] == "submitted"
    assert result["job_run_id"] == "888"
    assert request_urls == [
        "https://adb.example.com/api/2.1/jobs/run-now",
        "https://adb.example.com/api/2.1/jobs/runs/list?job_id=101002&active_only=true&limit=1",
        "https://adb.example.com/api/2.1/jobs/run-now",
    ]
    assert sleep_calls == [10.0]


def test_run_databricks_job_5xx_checks_active_run_before_any_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    sleep_calls: list[float] = []
    request_urls: list[str] = []

    def _fake_get_secret(key: str) -> str:
        if key == "agent-execute-mode":
            return "live"
        if key == "databricks-host":
            return "https://adb.example.com"
        if key == "databricks-agent-token":
            return "token"
        raise AssertionError(f"Unexpected secret lookup: {key}")

    responses = iter(
        [
            _DatabricksHttpError(
                "Databricks API error status=503: temporary",
                status_code=503,
            ),
            {"runs": [{"run_id": 9900}]},
        ]
    )

    def _fake_http_json_request(
        *,
        method: str,
        url: str,
        token: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        _ = method, token, payload, timeout_seconds
        request_urls.append(url)
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("tools.databricks_jobs.get_secret", _fake_get_secret)
    monkeypatch.setattr(
        "tools.databricks_jobs._http_json_request",
        _fake_http_json_request,
    )
    monkeypatch.setattr("tools.databricks_jobs.time.sleep", sleep_calls.append)

    result = run_databricks_job("retry_pipeline", {"pipeline": "pipeline_b"})

    assert result["status"] == "submitted"
    assert result["job_run_id"] == "9900"
    assert request_urls == [
        "https://adb.example.com/api/2.1/jobs/run-now",
        "https://adb.example.com/api/2.1/jobs/runs/list?job_id=101002&active_only=true&limit=1",
    ]
    assert sleep_calls == []


def test_run_databricks_job_retries_when_active_run_lookup_fails_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    sleep_calls: list[float] = []
    request_urls: list[str] = []

    def _fake_get_secret(key: str) -> str:
        if key == "agent-execute-mode":
            return "live"
        if key == "databricks-host":
            return "https://adb.example.com"
        if key == "databricks-agent-token":
            return "token"
        raise AssertionError(f"Unexpected secret lookup: {key}")

    responses = iter(
        [
            TimeoutError("timed out"),
            RuntimeError("runs/list failed"),
            {"run_id": 889},
        ]
    )

    def _fake_http_json_request(
        *,
        method: str,
        url: str,
        token: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        _ = method, token, payload, timeout_seconds
        request_urls.append(url)
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("tools.databricks_jobs.get_secret", _fake_get_secret)
    monkeypatch.setattr(
        "tools.databricks_jobs._http_json_request",
        _fake_http_json_request,
    )
    monkeypatch.setattr("tools.databricks_jobs.time.sleep", sleep_calls.append)

    result = run_databricks_job("retry_pipeline", {"pipeline": "pipeline_b"})

    assert result["status"] == "submitted"
    assert result["job_run_id"] == "889"
    assert request_urls == [
        "https://adb.example.com/api/2.1/jobs/run-now",
        "https://adb.example.com/api/2.1/jobs/runs/list?job_id=101002&active_only=true&limit=1",
        "https://adb.example.com/api/2.1/jobs/run-now",
    ]
    assert sleep_calls == [5.0]


def test_run_databricks_job_does_not_parse_5xx_from_plain_exception_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    def _fake_get_secret(key: str) -> str:
        if key == "agent-execute-mode":
            return "live"
        if key == "databricks-host":
            return "https://adb.example.com"
        if key == "databricks-agent-token":
            return "token"
        raise AssertionError(f"Unexpected secret lookup: {key}")

    def _fake_http_json_request(
        *,
        method: str,
        url: str,
        token: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        _ = method, url, token, payload, timeout_seconds
        raise Exception("HTTP 503 temporary")

    monkeypatch.setattr("tools.databricks_jobs.get_secret", _fake_get_secret)
    monkeypatch.setattr(
        "tools.databricks_jobs._http_json_request",
        _fake_http_json_request,
    )

    with pytest.raises(Exception, match="HTTP 503 temporary"):
        run_databricks_job("retry_pipeline", {"pipeline": "pipeline_b"})


def test_run_databricks_job_rejects_non_string_databricks_host_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    def _fake_get_secret(key: str) -> str:
        if key == "agent-execute-mode":
            return "live"
        if key == "databricks-host":
            return 123  # type: ignore[return-value]
        if key == "databricks-agent-token":
            return "token"
        raise AssertionError(f"Unexpected secret lookup: {key}")

    monkeypatch.setattr("tools.databricks_jobs.get_secret", _fake_get_secret)

    with pytest.raises(ValueError, match="Missing databricks-host secret"):
        run_databricks_job("retry_pipeline", {"pipeline": "pipeline_b"})


def test_run_databricks_job_timeout_checks_running_before_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tools.databricks_jobs.load_databricks_jobs_config",
        _fake_jobs_config,
    )

    request_urls: list[str] = []

    def _fake_get_secret(key: str) -> str:
        if key == "agent-execute-mode":
            return "live"
        if key == "databricks-host":
            return "https://adb.example.com"
        if key == "databricks-agent-token":
            return "token"
        raise AssertionError(f"Unexpected secret lookup: {key}")

    responses = iter(
        [
            TimeoutError("timed out"),
            {"runs": [{"run_id": 4321}]},
        ]
    )

    def _fake_http_json_request(
        *,
        method: str,
        url: str,
        token: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        _ = method, token, payload, timeout_seconds
        request_urls.append(url)
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("tools.databricks_jobs.get_secret", _fake_get_secret)
    monkeypatch.setattr(
        "tools.databricks_jobs._http_json_request",
        _fake_http_json_request,
    )

    result = run_databricks_job("retry_pipeline", {"pipeline": "pipeline_b"})

    assert result["status"] == "submitted"
    assert result["job_run_id"] == "4321"
    assert request_urls == [
        "https://adb.example.com/api/2.1/jobs/run-now",
        "https://adb.example.com/api/2.1/jobs/runs/list?job_id=101002&active_only=true&limit=1",
    ]


def test_check_job_status_returns_databricks_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_get_secret(key: str) -> str:
        if key == "agent-execute-mode":
            return "live"
        if key == "databricks-host":
            return "https://adb.example.com"
        if key == "databricks-agent-token":
            return "token"
        raise AssertionError(f"Unexpected secret lookup: {key}")

    def _fake_http_json_request(
        *,
        method: str,
        url: str,
        token: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        _ = method, url, token, payload, timeout_seconds
        return {
            "run_id": 5678,
            "state": {"life_cycle_state": "RUNNING", "result_state": None},
        }

    monkeypatch.setattr("tools.databricks_jobs.get_secret", _fake_get_secret)
    monkeypatch.setattr(
        "tools.databricks_jobs._http_json_request",
        _fake_http_json_request,
    )

    result = check_job_status("5678")

    assert result == {
        "status": "running",
        "job_run_id": "5678",
        "life_cycle_state": "RUNNING",
        "result_state": None,
    }
