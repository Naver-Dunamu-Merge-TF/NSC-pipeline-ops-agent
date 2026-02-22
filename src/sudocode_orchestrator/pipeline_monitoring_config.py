from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BoundaryConfig(_StrictModel):
    cutoff_delay_comparison: Literal[">"]


class DailyBatchPipelineConfig(_StrictModel):
    schedule_kst: str
    expected_completion_kst: str
    poll_after_kst: str
    cutoff_delay_minutes: int
    warning_at_kst: str


class MicrobatchPipelineConfig(_StrictModel):
    schedule: str
    expected_completion_minutes: int
    poll_every_minutes: int
    cutoff_delay_minutes: int
    warning_after_consecutive_misses: int


class PipelinesConfig(_StrictModel):
    pipeline_silver: DailyBatchPipelineConfig
    pipeline_b: DailyBatchPipelineConfig
    pipeline_c: DailyBatchPipelineConfig
    pipeline_a: MicrobatchPipelineConfig


class PipelineMonitoringConfig(_StrictModel):
    boundary: BoundaryConfig
    pipelines: PipelinesConfig


def default_pipeline_monitoring_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "pipeline_monitoring.yaml"


def load_pipeline_monitoring_config(
    config_path: str | Path | None = None,
) -> PipelineMonitoringConfig:
    path = (
        Path(config_path)
        if config_path is not None
        else default_pipeline_monitoring_config_path()
    )
    with path.open("r", encoding="utf-8") as handle:
        raw_config: dict[str, Any] = yaml.safe_load(handle)
    return PipelineMonitoringConfig.model_validate(raw_config)
