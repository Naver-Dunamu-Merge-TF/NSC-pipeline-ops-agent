# ADR-0001: freeze-validation-target-boundary-and-pk

## Status

Accepted

## Context

DEV-003에서 `config/validation_targets.yaml`에 verify #1~#5의 대상/PK/임계값/정책을 고정하려고 의사결정하던 시점에는, 원문 스펙이 #2의 경계(±50%)를 문장으로만 제시했고 검증 항목별 PK 구성을 완전한 표 형태로 고정하지 않았다. verify/rollback 후속 이슈가 즉시 소비 가능한 형태를 만들려면 당시 경계 연산자와 PK를 설정 스키마에서 명시적으로 확정할 필요가 있었다. 또한 롤백 대상 Delta 테이블은 `.specs/ai_agent_spec.md`의 롤백 예시(`silver.wallet_snapshot`, `silver.ledger_entries`)와 정합해야 했다.

## Decision

DEV-003 설정에서는 #2 경계를 `절대 변동률 >= 0.5` 실패로 고정한다. PK 규칙 범위는 verify #2/#3의 롤백 대상 테이블(`silver.wallet_snapshot`, `silver.ledger_entries`)에 한해 `docs/upstream/data_contract.md`의 업스트림 멱등 키를 사용하고, verify #4/#5의 `silver.dq_status`는 별도 규칙으로 `run_id,source_table`을 고정한다.

## Rationale

대안 1은 #2 경계를 `>`로 두어 `=50%`를 통과시키는 방식이었지만, 스펙 문구가 "±50% 이상 변동"이므로 해석 일관성이 떨어져 기각했다. 대안 2는 경계를 숫자만 두고 연산자 해석을 코드에 위임하는 방식이었지만, 후속 구현에서 해석 분기가 다시 생겨 DEV-003의 "설정으로 고정" 목적을 약화하므로 기각했다. PK는 신규 규칙을 만들지 않고 verify #2/#3 롤백 대상에는 업스트림 계약의 멱등 키(`wallet_snapshot`: `snapshot_ts,user_id`, `ledger_entries`: `tx_id,wallet_id`)를 재사용했으며, verify #4/#5의 `silver.dq_status`는 운영 식별자(`run_id,source_table`)로 분리 고정해 검증 의도를 분명히 했다.

## Consequences

PK 또는 임계값이 바뀌면 `config/validation_targets.yaml`을 우선 갱신하고, 같은 변경을 `.specs/ai_agent_spec.md`에 동기화한다. 이후 결정 변경 이력은 본 ADR을 덮어쓰기하지 않고 superseding ADR로 추가 기록해 문서 간 규칙 일치성과 의사결정 추적성을 함께 유지한다.
