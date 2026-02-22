from __future__ import annotations

from types import SimpleNamespace

import pytest

from tools.databricks_jobs import run_databricks_job


def _fake_jobs_config() -> SimpleNamespace:
    return SimpleNamespace(
        jobs=SimpleNamespace(
            pipeline_silver=SimpleNamespace(refresh=101001),
            pipeline_b=SimpleNamespace(refresh=101002),
            pipeline_c=SimpleNamespace(refresh=101003),
            pipeline_a=SimpleNamespace(refresh=101004),
        )
    )


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
