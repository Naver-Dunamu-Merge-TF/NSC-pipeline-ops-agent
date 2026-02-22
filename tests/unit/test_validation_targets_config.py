from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from orchestrator.validation_targets_config import (
    load_validation_targets_config,
)


def _base_validation_targets_config() -> dict[str, Any]:
    return {
        "verify": {
            "check_1": {
                "table": "gold.pipeline_state",
                "pk": ["pipeline_name"],
                "expected_status": "success",
                "failure_policy": "escalate_without_rollback",
            },
            "check_2": {
                "targets": [
                    {
                        "table": "silver.wallet_snapshot",
                        "pk": ["snapshot_ts", "user_id"],
                    },
                    {"table": "silver.ledger_entries", "pk": ["tx_id", "wallet_id"]},
                ],
                "max_change_ratio": 0.5,
                "failure_comparison": ">=",
                "zero_baseline_policy": "fail_if_current_positive",
                "rollback_on_failure": True,
            },
            "check_3": {
                "targets": [
                    {
                        "table": "silver.wallet_snapshot",
                        "pk": ["snapshot_ts", "user_id"],
                    },
                    {"table": "silver.ledger_entries", "pk": ["tx_id", "wallet_id"]},
                ],
                "duplicate_threshold": 1,
                "failure_comparison": ">=",
                "rollback_on_failure": True,
            },
            "check_4": {
                "table": "silver.dq_status",
                "pk": ["run_id", "source_table"],
                "dq_tags": ["SOURCE_STALE", "EVENT_DROP_SUSPECTED"],
                "rollback_on_failure": False,
            },
            "check_5": {
                "table": "silver.dq_status",
                "pk": ["run_id", "source_table"],
                "bad_records_rate_threshold": 0.05,
                "failure_comparison": ">",
                "rollback_on_failure": True,
            },
        },
        "rollback": {
            "delta_tables": [
                {"table": "silver.wallet_snapshot", "pk": ["snapshot_ts", "user_id"]},
                {"table": "silver.ledger_entries", "pk": ["tx_id", "wallet_id"]},
            ]
        },
    }


def _write_config(path: Path, config: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(config, sort_keys=False))


def test_load_validation_targets_config_success() -> None:
    config = load_validation_targets_config()

    assert config.verify.check_1.table == "gold.pipeline_state"
    assert config.verify.check_1.pk == ["pipeline_name"]
    assert config.verify.check_1.expected_status == "success"
    assert config.verify.check_1.failure_policy == "escalate_without_rollback"

    assert config.verify.check_2.max_change_ratio == 0.5
    assert config.verify.check_2.failure_comparison == ">="
    assert config.verify.check_2.zero_baseline_policy == "fail_if_current_positive"
    assert config.verify.check_2.rollback_on_failure is True
    assert config.verify.check_2.targets[0].table == "silver.wallet_snapshot"
    assert config.verify.check_2.targets[0].pk == ["snapshot_ts", "user_id"]
    assert config.verify.check_2.targets[1].table == "silver.ledger_entries"
    assert config.verify.check_2.targets[1].pk == ["tx_id", "wallet_id"]

    assert config.verify.check_3.duplicate_threshold == 1
    assert config.verify.check_3.failure_comparison == ">="
    assert config.verify.check_3.rollback_on_failure is True

    assert config.verify.check_4.table == "silver.dq_status"
    assert config.verify.check_4.pk == ["run_id", "source_table"]
    assert config.verify.check_4.dq_tags == ["SOURCE_STALE", "EVENT_DROP_SUSPECTED"]
    assert config.verify.check_4.rollback_on_failure is False

    assert config.verify.check_5.table == "silver.dq_status"
    assert config.verify.check_5.pk == ["run_id", "source_table"]
    assert config.verify.check_5.bad_records_rate_threshold == 0.05
    assert config.verify.check_5.failure_comparison == ">"
    assert config.verify.check_5.rollback_on_failure is True

    assert config.rollback.delta_tables[0].table == "silver.wallet_snapshot"
    assert config.rollback.delta_tables[1].table == "silver.ledger_entries"


def test_load_validation_targets_config_raises_on_missing_required_key(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "validation_targets.yaml"
    config_path.write_text(
        """
verify:
  check_1:
    table: "gold.pipeline_state"
    pk: ["pipeline_name"]
    expected_status: "success"
    failure_policy: "escalate_without_rollback"
  check_2:
    targets:
      - table: "silver.wallet_snapshot"
        pk: ["snapshot_ts", "user_id"]
      - table: "silver.ledger_entries"
        pk: ["tx_id", "wallet_id"]
    max_change_ratio: 0.5
    failure_comparison: ">="
    zero_baseline_policy: "fail_if_current_positive"
    rollback_on_failure: true
  check_3:
    targets:
      - table: "silver.wallet_snapshot"
        pk: ["snapshot_ts", "user_id"]
      - table: "silver.ledger_entries"
        pk: ["tx_id", "wallet_id"]
    duplicate_threshold: 1
    failure_comparison: ">="
    rollback_on_failure: true
  check_4:
    table: "silver.dq_status"
    pk: ["run_id", "source_table"]
    dq_tags: ["SOURCE_STALE", "EVENT_DROP_SUSPECTED"]
    rollback_on_failure: false
rollback:
  delta_tables:
    - table: "silver.wallet_snapshot"
      pk: ["snapshot_ts", "user_id"]
    - table: "silver.ledger_entries"
      pk: ["tx_id", "wallet_id"]
""".strip()
    )

    with pytest.raises(ValidationError, match="check_5"):
        load_validation_targets_config(config_path)


def test_load_validation_targets_config_raises_on_pk_type_error(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "validation_targets.yaml"
    config_path.write_text(
        """
verify:
  check_1:
    table: "gold.pipeline_state"
    pk: ["pipeline_name"]
    expected_status: "success"
    failure_policy: "escalate_without_rollback"
  check_2:
    targets:
      - table: "silver.wallet_snapshot"
        pk: "snapshot_ts"
      - table: "silver.ledger_entries"
        pk: ["tx_id", "wallet_id"]
    max_change_ratio: 0.5
    failure_comparison: ">="
    zero_baseline_policy: "fail_if_current_positive"
    rollback_on_failure: true
  check_3:
    targets:
      - table: "silver.wallet_snapshot"
        pk: ["snapshot_ts", "user_id"]
      - table: "silver.ledger_entries"
        pk: ["tx_id", "wallet_id"]
    duplicate_threshold: 1
    failure_comparison: ">="
    rollback_on_failure: true
  check_4:
    table: "silver.dq_status"
    pk: ["run_id", "source_table"]
    dq_tags: ["SOURCE_STALE", "EVENT_DROP_SUSPECTED"]
    rollback_on_failure: false
  check_5:
    table: "silver.dq_status"
    pk: ["run_id", "source_table"]
    bad_records_rate_threshold: 0.05
    failure_comparison: ">"
    rollback_on_failure: true
rollback:
  delta_tables:
    - table: "silver.wallet_snapshot"
      pk: ["snapshot_ts", "user_id"]
    - table: "silver.ledger_entries"
      pk: ["tx_id", "wallet_id"]
""".strip()
    )

    with pytest.raises(ValidationError, match="pk"):
        load_validation_targets_config(config_path)


def test_load_validation_targets_config_raises_on_check_2_ratio_drift(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "validation_targets.yaml"
    config_path.write_text(
        """
verify:
  check_1:
    table: "gold.pipeline_state"
    pk: ["pipeline_name"]
    expected_status: "success"
    failure_policy: "escalate_without_rollback"
  check_2:
    targets:
      - table: "silver.wallet_snapshot"
        pk: ["snapshot_ts", "user_id"]
      - table: "silver.ledger_entries"
        pk: ["tx_id", "wallet_id"]
    max_change_ratio: 0.6
    failure_comparison: ">="
    zero_baseline_policy: "fail_if_current_positive"
    rollback_on_failure: true
  check_3:
    targets:
      - table: "silver.wallet_snapshot"
        pk: ["snapshot_ts", "user_id"]
      - table: "silver.ledger_entries"
        pk: ["tx_id", "wallet_id"]
    duplicate_threshold: 1
    failure_comparison: ">="
    rollback_on_failure: true
  check_4:
    table: "silver.dq_status"
    pk: ["run_id", "source_table"]
    dq_tags: ["SOURCE_STALE", "EVENT_DROP_SUSPECTED"]
    rollback_on_failure: false
  check_5:
    table: "silver.dq_status"
    pk: ["run_id", "source_table"]
    bad_records_rate_threshold: 0.05
    failure_comparison: ">"
    rollback_on_failure: true
rollback:
  delta_tables:
    - table: "silver.wallet_snapshot"
      pk: ["snapshot_ts", "user_id"]
    - table: "silver.ledger_entries"
      pk: ["tx_id", "wallet_id"]
""".strip()
    )

    with pytest.raises(ValidationError, match="check_2.max_change_ratio"):
        load_validation_targets_config(config_path)


def test_load_validation_targets_config_raises_on_dq_status_pk_drift(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "validation_targets.yaml"
    config_path.write_text(
        """
verify:
  check_1:
    table: "gold.pipeline_state"
    pk: ["pipeline_name"]
    expected_status: "success"
    failure_policy: "escalate_without_rollback"
  check_2:
    targets:
      - table: "silver.wallet_snapshot"
        pk: ["snapshot_ts", "user_id"]
      - table: "silver.ledger_entries"
        pk: ["tx_id", "wallet_id"]
    max_change_ratio: 0.5
    failure_comparison: ">="
    zero_baseline_policy: "fail_if_current_positive"
    rollback_on_failure: true
  check_3:
    targets:
      - table: "silver.wallet_snapshot"
        pk: ["snapshot_ts", "user_id"]
      - table: "silver.ledger_entries"
        pk: ["tx_id", "wallet_id"]
    duplicate_threshold: 1
    failure_comparison: ">="
    rollback_on_failure: true
  check_4:
    table: "silver.dq_status"
    pk: ["run_id"]
    dq_tags: ["SOURCE_STALE", "EVENT_DROP_SUSPECTED"]
    rollback_on_failure: false
  check_5:
    table: "silver.dq_status"
    pk: ["run_id", "source_table"]
    bad_records_rate_threshold: 0.05
    failure_comparison: ">"
    rollback_on_failure: true
rollback:
  delta_tables:
    - table: "silver.wallet_snapshot"
      pk: ["snapshot_ts", "user_id"]
    - table: "silver.ledger_entries"
      pk: ["tx_id", "wallet_id"]
""".strip()
    )

    with pytest.raises(ValidationError, match="check_4.pk"):
        load_validation_targets_config(config_path)


def test_load_validation_targets_config_accepts_reordered_targets_and_delta_tables(
    tmp_path: Path,
) -> None:
    config = _base_validation_targets_config()
    config["verify"]["check_2"]["targets"].reverse()
    config["verify"]["check_3"]["targets"].reverse()
    config["rollback"]["delta_tables"].reverse()

    config_path = tmp_path / "validation_targets.yaml"
    _write_config(config_path, config)

    loaded = load_validation_targets_config(config_path)
    assert loaded.verify.check_2.max_change_ratio == 0.5


def test_load_validation_targets_config_raises_on_check_3_targets_drift(
    tmp_path: Path,
) -> None:
    config = _base_validation_targets_config()
    config["verify"]["check_3"]["targets"][1]["pk"] = ["tx_id"]

    config_path = tmp_path / "validation_targets.yaml"
    _write_config(config_path, config)

    with pytest.raises(ValidationError, match="verify.check_3.targets"):
        load_validation_targets_config(config_path)


def test_load_validation_targets_config_raises_on_check_5_table_drift(
    tmp_path: Path,
) -> None:
    config = _base_validation_targets_config()
    config["verify"]["check_5"]["table"] = "silver.dq_status_v2"

    config_path = tmp_path / "validation_targets.yaml"
    _write_config(config_path, config)

    with pytest.raises(ValidationError, match="verify.check_5.table") as excinfo:
        load_validation_targets_config(config_path)

    error_message = str(excinfo.value)
    assert "expected='silver.dq_status'" in error_message
    assert "received='silver.dq_status_v2'" in error_message


def test_load_validation_targets_config_raises_on_check_5_pk_drift(
    tmp_path: Path,
) -> None:
    config = _base_validation_targets_config()
    config["verify"]["check_5"]["pk"] = ["run_id"]

    config_path = tmp_path / "validation_targets.yaml"
    _write_config(config_path, config)

    with pytest.raises(ValidationError, match="verify.check_5.pk"):
        load_validation_targets_config(config_path)


def test_load_validation_targets_config_raises_on_rollback_delta_tables_drift(
    tmp_path: Path,
) -> None:
    config = _base_validation_targets_config()
    config["rollback"]["delta_tables"][1]["table"] = "silver.ledger_entries_v2"

    config_path = tmp_path / "validation_targets.yaml"
    _write_config(config_path, config)

    with pytest.raises(ValidationError, match="rollback.delta_tables"):
        load_validation_targets_config(config_path)
