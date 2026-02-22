# ADR-0001: freeze-validation-target-boundary-and-pk

## Status

Accepted

## Context

DEV-003에서는 `config/validation_targets.yaml`에 verify #1~#5의 대상/PK/임계값/정책을 고정해야 하지만, 원문 스펙은 #2의 경계(±50%)를 문장으로만 제시하고 각 검증 항목별 PK 구성을 완전한 표 형태로 고정하지는 않았다. 구현 시점에 verify/rollback 후속 이슈가 즉시 소비 가능한 형태를 만들려면 경계 연산자와 PK를 설정 스키마에서 명시적으로 결정해야 한다. 또한 롤백 대상 Delta 테이블은 `.specs/ai_agent_spec.md`의 롤백 예시(`silver.wallet_snapshot`, `silver.ledger_entries`)와 정합해야 한다.

## Decision

DEV-003 설정에서는 #2 경계를 `절대 변동률 >= 0.5` 실패로 고정하고, verify/rollback 대상 PK를 `docs/upstream/data_contract.md`의 멱등 키 기준으로 명시한다.

## Rationale

대안 1은 #2 경계를 `>`로 두어 `=50%`를 통과시키는 방식이었지만, 스펙 문구가 "±50% 이상 변동"이므로 해석 일관성이 떨어져 기각했다. 대안 2는 경계를 숫자만 두고 연산자 해석을 코드에 위임하는 방식이었지만, 후속 구현에서 해석 분기가 다시 생겨 DEV-003의 "설정으로 고정" 목적을 약화하므로 기각했다. PK는 별도 신규 규칙을 만들지 않고 기존 업스트림 계약의 멱등 키(`wallet_snapshot`: `snapshot_ts,user_id`, `ledger_entries`: `tx_id,wallet_id`)를 재사용해 학습 비용을 줄이고 추적 가능성을 높였다. 이 선택의 트레이드오프는 향후 스키마 변경 시 설정과 ADR을 함께 갱신해야 한다는 점이지만, 현재 범위에서는 명시성과 일관성이 더 중요하다.
