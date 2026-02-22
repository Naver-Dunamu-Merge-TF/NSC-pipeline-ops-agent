from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sudocode_orchestrator.validation_targets_config import (
    load_validation_targets_config,
)


def test_load_validation_targets_config_success() -> None:
    config = load_validation_targets_config()

    assert config.verify.check_1.table == "gold.pipeline_state"
    assert config.verify.check_1.pk == ["pipeline_name"]
    assert config.verify.check_1.expected_status == "success"
    assert config.verify.check_1.failure_policy == "escalate_without_rollback"

    assert config.verify.check_2.max_change_ratio == 0.5
    assert config.verify.check_2.failure_comparison == ">="
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
