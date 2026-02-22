from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TableTarget(_StrictModel):
    table: str
    pk: list[str]


class VerifyCheck1Config(_StrictModel):
    table: str
    pk: list[str]
    expected_status: Literal["success"]
    failure_policy: Literal["escalate_without_rollback"]


class VerifyCheck2Config(_StrictModel):
    targets: list[TableTarget]
    max_change_ratio: float
    failure_comparison: Literal[">="]
    zero_baseline_policy: Literal["fail_if_current_positive"]
    rollback_on_failure: Literal[True]


class VerifyCheck3Config(_StrictModel):
    targets: list[TableTarget]
    duplicate_threshold: int
    failure_comparison: Literal[">="]
    rollback_on_failure: Literal[True]


class VerifyCheck4Config(_StrictModel):
    table: str
    pk: list[str]
    dq_tags: list[str]
    rollback_on_failure: Literal[False]


class VerifyCheck5Config(_StrictModel):
    table: str
    pk: list[str]
    bad_records_rate_threshold: float
    failure_comparison: Literal[">"]
    rollback_on_failure: Literal[True]


class VerifyChecksConfig(_StrictModel):
    check_1: VerifyCheck1Config
    check_2: VerifyCheck2Config
    check_3: VerifyCheck3Config
    check_4: VerifyCheck4Config
    check_5: VerifyCheck5Config


class RollbackConfig(_StrictModel):
    delta_tables: list[TableTarget]


class ValidationTargetsConfig(_StrictModel):
    verify: VerifyChecksConfig
    rollback: RollbackConfig


def default_validation_targets_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "validation_targets.yaml"


def load_validation_targets_config(
    config_path: str | Path | None = None,
) -> ValidationTargetsConfig:
    path = (
        Path(config_path)
        if config_path is not None
        else default_validation_targets_config_path()
    )
    with path.open("r", encoding="utf-8") as handle:
        raw_config: dict[str, Any] = yaml.safe_load(handle)
    return ValidationTargetsConfig.model_validate(raw_config)
