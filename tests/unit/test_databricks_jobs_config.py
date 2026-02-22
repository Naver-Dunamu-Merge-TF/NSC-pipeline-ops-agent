from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from orchestrator.databricks_jobs_config import load_databricks_jobs_config


def test_load_databricks_jobs_config_success() -> None:
    config = load_databricks_jobs_config()

    jobs = config.model_dump()["jobs"]
    assert set(jobs) == {"pipeline_silver", "pipeline_b", "pipeline_c", "pipeline_a"}
    assert all(isinstance(job["refresh"], int) for job in jobs.values())


def test_load_databricks_jobs_config_raises_on_missing_required_key(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "databricks_jobs.yaml"
    config_path.write_text(
        """
jobs:
  pipeline_silver:
    refresh: 101001
  pipeline_b:
    refresh: 101002
  pipeline_c:
    refresh: 101003
""".strip()
    )

    with pytest.raises(ValidationError, match="pipeline_a"):
        load_databricks_jobs_config(config_path)


def test_load_databricks_jobs_config_raises_on_non_numeric_job_id(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "databricks_jobs.yaml"
    config_path.write_text(
        """
jobs:
  pipeline_silver:
    refresh: "101001"
  pipeline_b:
    refresh: 101002
  pipeline_c:
    refresh: 101003
  pipeline_a:
    refresh: 101004
""".strip()
    )

    with pytest.raises(ValidationError, match="refresh"):
        load_databricks_jobs_config(config_path)


def test_load_databricks_jobs_config_raises_on_duplicate_key(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "databricks_jobs.yaml"
    config_path.write_text(
        """
jobs:
  pipeline_silver:
    refresh: 101001
  pipeline_b:
    refresh: 101002
    refresh: 999999
  pipeline_c:
    refresh: 101003
  pipeline_a:
    refresh: 101004
""".strip()
    )

    with pytest.raises(
        yaml.constructor.ConstructorError, match="Duplicate key: refresh"
    ) as exc_info:
        load_databricks_jobs_config(config_path)

    assert exc_info.value.problem_mark is not None
    assert exc_info.value.problem_mark.line == 5
    assert exc_info.value.problem_mark.column == 4
