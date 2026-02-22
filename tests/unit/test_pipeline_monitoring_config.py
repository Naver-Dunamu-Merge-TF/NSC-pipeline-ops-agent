from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sudocode_orchestrator.pipeline_monitoring_config import (
    load_pipeline_monitoring_config,
)


def test_load_pipeline_monitoring_config_success() -> None:
    config = load_pipeline_monitoring_config()

    assert config.boundary.cutoff_delay_comparison == ">"

    assert config.pipelines.pipeline_silver.schedule_kst == "00:00"
    assert config.pipelines.pipeline_silver.expected_completion_kst == "00:10"
    assert config.pipelines.pipeline_silver.poll_after_kst == "00:10"
    assert config.pipelines.pipeline_silver.cutoff_delay_minutes == 30
    assert config.pipelines.pipeline_silver.warning_at_kst == "00:30"

    assert config.pipelines.pipeline_b.schedule_kst == "00:20"
    assert config.pipelines.pipeline_b.expected_completion_kst == "00:35"
    assert config.pipelines.pipeline_b.poll_after_kst == "00:35"
    assert config.pipelines.pipeline_b.cutoff_delay_minutes == 30
    assert config.pipelines.pipeline_b.warning_at_kst == "00:50"

    assert config.pipelines.pipeline_c.schedule_kst == "00:35"
    assert config.pipelines.pipeline_c.expected_completion_kst == "00:45"
    assert config.pipelines.pipeline_c.poll_after_kst == "00:45"
    assert config.pipelines.pipeline_c.cutoff_delay_minutes == 30
    assert config.pipelines.pipeline_c.warning_at_kst == "01:05"

    assert config.pipelines.pipeline_a.schedule == "every_10_minutes"
    assert config.pipelines.pipeline_a.expected_completion_minutes == 2
    assert config.pipelines.pipeline_a.poll_every_minutes == 5
    assert config.pipelines.pipeline_a.cutoff_delay_minutes == 20
    assert config.pipelines.pipeline_a.warning_after_consecutive_misses == 2


def test_load_pipeline_monitoring_config_raises_on_missing_required_key(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "pipeline_monitoring.yaml"
    config_path.write_text(
        """
boundary:
  cutoff_delay_comparison: ">"
pipelines:
  pipeline_silver:
    schedule_kst: "00:00"
    expected_completion_kst: "00:10"
    cutoff_delay_minutes: 30
    warning_at_kst: "00:30"
  pipeline_b:
    schedule_kst: "00:20"
    expected_completion_kst: "00:35"
    poll_after_kst: "00:35"
    cutoff_delay_minutes: 30
    warning_at_kst: "00:50"
  pipeline_c:
    schedule_kst: "00:35"
    expected_completion_kst: "00:45"
    poll_after_kst: "00:45"
    cutoff_delay_minutes: 30
    warning_at_kst: "01:05"
  pipeline_a:
    schedule: "every_10_minutes"
    expected_completion_minutes: 2
    poll_every_minutes: 5
    cutoff_delay_minutes: 20
    warning_after_consecutive_misses: 2
""".strip()
    )

    with pytest.raises(ValidationError, match="poll_after_kst"):
        load_pipeline_monitoring_config(config_path)


def test_load_pipeline_monitoring_config_raises_on_type_error(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "pipeline_monitoring.yaml"
    config_path.write_text(
        """
boundary:
  cutoff_delay_comparison: ">"
pipelines:
  pipeline_silver:
    schedule_kst: "00:00"
    expected_completion_kst: "00:10"
    poll_after_kst: "00:10"
    cutoff_delay_minutes: "30"
    warning_at_kst: "00:30"
  pipeline_b:
    schedule_kst: "00:20"
    expected_completion_kst: "00:35"
    poll_after_kst: "00:35"
    cutoff_delay_minutes: 30
    warning_at_kst: "00:50"
  pipeline_c:
    schedule_kst: "00:35"
    expected_completion_kst: "00:45"
    poll_after_kst: "00:45"
    cutoff_delay_minutes: 30
    warning_at_kst: "01:05"
  pipeline_a:
    schedule: "every_10_minutes"
    expected_completion_minutes: 2
    poll_every_minutes: 5
    cutoff_delay_minutes: 20
    warning_after_consecutive_misses: 2
""".strip()
    )

    with pytest.raises(ValidationError, match="cutoff_delay_minutes"):
        load_pipeline_monitoring_config(config_path)
