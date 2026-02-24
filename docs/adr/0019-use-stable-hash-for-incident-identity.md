# ADR-0019: 안정 해시 기반 incident 식별자 채택

## Created At

2026-02-25 01:02 KST

## Status

Confirmed

## Context

동일한 의미의 이슈 집합이 입력 순서나 직렬화 방식 차이로 서로 다른 `incident_id` 및 fingerprint를 생성하면, 중복 incident가 발생하고 집계 일관성이 깨진다. DEV-012에서는 저영향·가역 범위에서 incident 식별 규칙을 명시적으로 고정해 재현성과 비교 가능성을 확보해야 한다. 특히 `detected_issues`의 순서 의존성을 제거하지 않으면 입력 순서만 바뀌어도 서로 다른 fingerprint가 생성되어 동일 incident 판단이 불가능해진다.

## Decision

`incident_id`는 `inc-` + SHA-256 앞 16자리 hex로 고정하고, fingerprint는 `detected_issues`를 stable JSON으로 직렬화한 뒤 canonicalization(정렬)하여 순서 무관하게 SHA-256 64hex를 생성하는 방식으로 결정한다.

## Rationale

대안 1은 UUID v4 같은 난수 기반 ID를 매번 생성하는 방식이었으나, 동일 입력에 대해 결정적 재현이 불가능해 중복 감지와 회귀 검증에 불리하므로 기각했다. 대안 2는 `detected_issues` 원본 순서를 그대로 직렬화해 해시를 계산하는 방식이었으나, 의미적으로 동일한 데이터도 순서 차이만으로 해시가 달라져 순서 무관 동등성 요구를 충족하지 못하므로 기각했다. 대안 3은 SHA-256 대신 짧은 비암호학 해시를 사용하는 방식이었으나, 충돌 가능성과 장기 운영 시 식별 안정성 측면에서 불확실성이 커 기각했다. 최종안은 구현 영향이 작고 되돌리기 쉬우면서도, 결정적 식별자 생성과 순서 독립 fingerprint를 동시에 보장해 운영 일관성을 높인다.

## Follow-up 점검 체크리스트 (i-42k2)

ADR-0019 규약(결정적 `incident_id`, 순서 무관 fingerprint) 변경 또는 회귀 점검 시 아래 경로를 우선 확인한다.

- [ ] `tests/unit/test_incident_utils.py` - `inc-[0-9a-f]{16}` 형식, 동일 입력 결정성, `detected_issues` 순서 무관 fingerprint 검증.
- [ ] `tests/unit/test_ai_agent_state_models.py` - 상태 계약에 `incident_id`/`fingerprint` 필드가 유지되는지 검증.
- [ ] `tests/unit/test_ai_agent_skeleton_imports.py` - 오케스트레이터 스켈레톤 입력/출력 계약에서 사건 식별 필드가 누락되지 않는지 검증.
- [ ] `tests/unit/test_graph_build_and_smoke.py` - 그래프 스모크 경로에서 `incident_id`/`fingerprint` 전달 형태가 유지되는지 점검.
- [ ] `.specs/ai_agent_spec.md` - AgentState 정의 및 중복 방지 규칙(`fingerprint` SSOT) 설명이 ADR-0019와 일치하는지 확인.
- [ ] `.specs/data_contract.md` - `last_run_id`의 fingerprint 생성/추적 목적이 현재 규약과 충돌 없는지 확인.
- [ ] `.specs/rag_incident_retrieval_spec.md` - `incident_id` 고유 제약/조회 계약이 식별 규약과 정합한지 확인.
- [ ] `docs/adr/0019-use-stable-hash-for-incident-identity.md` - Decision/Rationale/Trigger 섹션의 최신화 여부 확인.

## ADR-0019 갱신 트리거

아래 중 하나라도 해당하면 후속 이슈에서 ADR-0019 갱신(또는 supersede ADR 추가)을 필수로 수행한다.

1. `incident_id` 생성 규칙(해시 알고리즘, prefix `inc-`, 길이 16hex)을 변경할 때.
2. fingerprint 생성 입력(`detected_issues`) 또는 canonicalization/정렬 규칙을 변경할 때.
3. 순서 무관 동등성(동일 의미의 `detected_issues`는 동일 fingerprint) 보장을 완화/폐기할 때.
4. 중복 방지 SSOT 키를 fingerprint 외 값으로 전환하거나, 체크포인터/저장소에서 식별 키 정책을 변경할 때.
5. 해시 충돌 대응 정책, 재현성 요구 수준, 혹은 운영 감사 추적 요구가 변경될 때.

## `.specs` 보강 후보

현재 즉시 수정은 아니며, 신규/후속 이슈에서 아래 보강을 후보로 검토한다.

- 후보 1: `.specs/ai_agent_spec.md` - ADR-0019 직접 참조 섹션(예: "Incident Identity Policy")을 추가해 해시 규약과 테스트 기준을 연결.
- 후보 2: `.specs/rag_incident_retrieval_spec.md` - `incident_id` UNIQUE 제약이 해시 규약 변경 시 어떤 마이그레이션 영향을 받는지 명시.
- 후보 3: `.specs/data_contract.md` - `last_run_id` 누락/`None` 케이스에서 `incident_id`/fingerprint 결정성 기대 동작을 명문화.
