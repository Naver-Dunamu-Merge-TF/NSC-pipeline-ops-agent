from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


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


ADR_0002_CHECK_2_MAX_CHANGE_RATIO = 0.5
ADR_0002_REQUIRED_TARGETS = (
    ("silver.wallet_snapshot", ("snapshot_ts", "user_id")),
    ("silver.ledger_entries", ("tx_id", "wallet_id")),
)
ADR_0002_REQUIRED_DQ_STATUS_TABLE = "silver.dq_status"
ADR_0002_REQUIRED_DQ_STATUS_PK = ["run_id", "source_table"]


def _normalized_target_signatures(
    targets: list[TableTarget],
) -> list[tuple[str, tuple[str, ...]]]:
    return sorted((target.table, tuple(target.pk)) for target in targets)


def _target_signature_to_dict(signature: tuple[str, tuple[str, ...]]) -> dict[str, Any]:
    table, pk = signature
    return {"table": table, "pk": list(pk)}


def _expected_target_dicts() -> list[dict[str, Any]]:
    return [
        _target_signature_to_dict(signature) for signature in ADR_0002_REQUIRED_TARGETS
    ]


def _received_target_dicts(targets: list[TableTarget]) -> list[dict[str, Any]]:
    return [target.model_dump() for target in targets]


def _raise_invariant_error(path: str, expected: Any, received: Any) -> None:
    raise ValueError(
        f"ADR-0002 invariant violation at {path}: "
        f"expected={expected!r}, received={received!r}"
    )


class ValidationTargetsConfig(_StrictModel):
    verify: VerifyChecksConfig
    rollback: RollbackConfig

    @model_validator(mode="after")
    def _enforce_adr_0002_invariants(self) -> ValidationTargetsConfig:
        expected_targets = _expected_target_dicts()
        expected_target_signatures = sorted(ADR_0002_REQUIRED_TARGETS)

        if self.verify.check_2.max_change_ratio != ADR_0002_CHECK_2_MAX_CHANGE_RATIO:
            _raise_invariant_error(
                path="verify.check_2.max_change_ratio",
                expected=ADR_0002_CHECK_2_MAX_CHANGE_RATIO,
                received=self.verify.check_2.max_change_ratio,
            )

        check_2_targets = _normalized_target_signatures(self.verify.check_2.targets)
        if check_2_targets != expected_target_signatures:
            _raise_invariant_error(
                path="verify.check_2.targets",
                expected=expected_targets,
                received=_received_target_dicts(self.verify.check_2.targets),
            )

        check_3_targets = _normalized_target_signatures(self.verify.check_3.targets)
        if check_3_targets != expected_target_signatures:
            _raise_invariant_error(
                path="verify.check_3.targets",
                expected=expected_targets,
                received=_received_target_dicts(self.verify.check_3.targets),
            )

        if self.verify.check_4.table != ADR_0002_REQUIRED_DQ_STATUS_TABLE:
            _raise_invariant_error(
                path="verify.check_4.table",
                expected=ADR_0002_REQUIRED_DQ_STATUS_TABLE,
                received=self.verify.check_4.table,
            )
        if self.verify.check_4.pk != ADR_0002_REQUIRED_DQ_STATUS_PK:
            _raise_invariant_error(
                path="verify.check_4.pk",
                expected=ADR_0002_REQUIRED_DQ_STATUS_PK,
                received=self.verify.check_4.pk,
            )

        if self.verify.check_5.table != ADR_0002_REQUIRED_DQ_STATUS_TABLE:
            _raise_invariant_error(
                path="verify.check_5.table",
                expected=ADR_0002_REQUIRED_DQ_STATUS_TABLE,
                received=self.verify.check_5.table,
            )
        if self.verify.check_5.pk != ADR_0002_REQUIRED_DQ_STATUS_PK:
            _raise_invariant_error(
                path="verify.check_5.pk",
                expected=ADR_0002_REQUIRED_DQ_STATUS_PK,
                received=self.verify.check_5.pk,
            )

        rollback_targets = _normalized_target_signatures(self.rollback.delta_tables)
        if rollback_targets != expected_target_signatures:
            _raise_invariant_error(
                path="rollback.delta_tables",
                expected=expected_targets,
                received=_received_target_dicts(self.rollback.delta_tables),
            )

        return self


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
