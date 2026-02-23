# ADR-0005: defer-actionplan-version-discriminator

## Created At

2026-02-23 03:44 KST

## Status

Confirmed

## Context

`.specs/ai_agent_spec.md`의 ADR-0003 ActionPlan 계약을 반영하는 과정에서, 버전 판별자 SSOT와 허용/거부 정책을 문서·코드에 동기화해야 하는 요구가 명확해졌다. 기존 ADR-0005는 판별자 위치·필드·판별 방식을 TBD로 두고 있어 현재 적용된 규칙과 불일치하며 docs gate 불일치를 유발했다.

## Decision

ActionPlan 버전 판별 규칙을 다음과 같이 확정한다.

- 판별자 위치(SSOT): `action_plan.schema_version`(top-level)
- 형식/허용 규칙: `schema_version`은 `^v[1-9][0-9]*$`를 만족하는 문자열만 버전 지정으로 인정
- v1 정책: legacy v1은 `schema_version` 미포함만 허용하며, 명시 `"v1"`은 거부
- v2+ 정책: 판별(`"v2"`, `"v3"` ...)은 허용하되, execute는 계약 확정 전까지 거부

## Rationale

대안 1은 판별자 위치를 계속 TBD로 유지하는 방식이지만, 문서와 구현의 기준점이 달라져 gate 불일치가 반복되므로 기각했다. 대안 2는 `version` 등 별도 필드를 도입하는 방식이지만, 이미 반영된 `action_plan.schema_version` SSOT와 충돌해 하위호환 비용이 커지므로 기각했다. 채택안은 현행 구현과 동일하게 `action_plan.schema_version` + 정규식 규칙을 확정하고, v1은 무버전만 허용하며, v2+는 판별만 허용하고 execute를 차단하는 운영 안전장치를 유지하는 방식이다. 이 방식은 현재 계약 상태를 보수적으로 고정하면서도 향후 v2+ 계약 확정 시 확장 경로를 명확히 남긴다.
