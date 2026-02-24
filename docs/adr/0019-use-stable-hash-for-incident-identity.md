# ADR-0019: 안정 해시 기반 incident 식별자 채택

## Created At

2026-02-25 01:02 KST

## Status

PendingReview

## Context

동일한 의미의 이슈 집합이 입력 순서나 직렬화 방식 차이로 서로 다른 `incident_id` 및 fingerprint를 생성하면, 중복 incident가 발생하고 집계 일관성이 깨진다. DEV-012에서는 저영향·가역 범위에서 incident 식별 규칙을 명시적으로 고정해 재현성과 비교 가능성을 확보해야 한다. 특히 `detected_issues`의 순서 의존성을 제거하지 않으면 입력 순서만 바뀌어도 서로 다른 fingerprint가 생성되어 동일 incident 판단이 불가능해진다.

## Decision

`incident_id`는 `inc-` + SHA-256 앞 16자리 hex로 고정하고, fingerprint는 `detected_issues`를 stable JSON으로 직렬화한 뒤 canonicalization(정렬)하여 순서 무관하게 SHA-256 64hex를 생성하는 방식으로 결정한다.

## Rationale

대안 1은 UUID v4 같은 난수 기반 ID를 매번 생성하는 방식이었으나, 동일 입력에 대해 결정적 재현이 불가능해 중복 감지와 회귀 검증에 불리하므로 기각했다. 대안 2는 `detected_issues` 원본 순서를 그대로 직렬화해 해시를 계산하는 방식이었으나, 의미적으로 동일한 데이터도 순서 차이만으로 해시가 달라져 순서 무관 동등성 요구를 충족하지 못하므로 기각했다. 대안 3은 SHA-256 대신 짧은 비암호학 해시를 사용하는 방식이었으나, 충돌 가능성과 장기 운영 시 식별 안정성 측면에서 불확실성이 커 기각했다. 최종안은 구현 영향이 작고 되돌리기 쉬우면서도, 결정적 식별자 생성과 순서 독립 fingerprint를 동시에 보장해 운영 일관성을 높인다.
