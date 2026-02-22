# ADR-0003: define-action-plan-parameter-schema

## Status

Confirmed

## Context

DEV-007은 execute 단계가 허용된 조치만 수행하도록 `action` 화이트리스트와 액션별 파라미터 검증을 요구한다. 근거 스펙은 `.specs/ai_agent_spec.md`의 "가드레일 — 실행 가능 조치 화이트리스트"(허용 조치 3종), `ops01_triage` 규칙(제안 가능한 action 제한), 그리고 `proposed_action.parameters` 예시(`backfill_silver`의 `pipeline/date_kst/run_mode`)이며, `.specs/data_contract.md`는 `date_kst`를 date 의미값으로 정의한다. 다만 스펙에는 `retry_pipeline`과 `skip_and_report`의 최소 필수 파라미터, `run_mode` 허용값 집합, `date_kst` 문자열 파싱 엄격도(예: `YYYY-MM-DD` 고정 여부)가 명시적으로 고정되어 있지 않아 구현 시점의 정책 결정이 필요했다.

## Decision

`backfill_silver`는 `pipeline/date_kst/run_mode`, `retry_pipeline`은 `pipeline/run_mode`, `skip_and_report`는 `pipeline/reason`을 각각 필수 파라미터로 고정하고 허용되지 않은 추가 파라미터를 거부하며 `date_kst`는 `YYYY-MM-DD` 형식만 허용하고 향후 파라미터 확장은 하위호환 영향 검토를 전제로 스키마 버전 업(v2+)으로만 도입하기로 결정한다.

## Rationale

이 결정은 execute 입력을 최소한의 명시적 스키마로 제한해 오작동 가능성을 줄이기 위한 것이다. 대안 1은 `retry_pipeline`과 `skip_and_report`를 느슨한 자유 파라미터(dict any)로 두는 방법이었지만, 이 경우 제안/수정 단계에서 오타나 불필요 키가 조용히 통과되어 실행 경계가 약해진다. 대안 2는 `skip_and_report` 파라미터를 완전히 비워 두는 방법이었지만, 어떤 파이프라인 맥락에서 스킵했는지와 사유를 일관되게 남기기 어렵다. 대안 3은 날짜를 범용 파서로 허용하는 방법이었지만, `2026-2-3` 같은 표현이 혼재되어 운영 로그와 재현성이 떨어진다. 대안 4는 추가 파라미터를 무시(soft-accept)하는 방식이었지만, 잘못된 입력을 조기에 차단하지 못해 장애 원인 추적이 늦어진다. `run_mode`와 `pipeline`의 허용값(enum) 고정은 현재 스펙에 단일 표준 목록이 없어 이번 결정 범위에서 제외하고 타입 검증만 적용하며, 값 집합 고정은 별도 스펙/이슈에서 정의하는 것이 변경 비용과 정합성 측면에서 안전하다. 따라서 액션별 필수 키를 명시하고 추가 키를 금지하며 날짜 형식을 엄격히 고정하고, 확장 시에는 버전 업으로만 도입하는 현재 선택이 가장 보수적이고 검증 가능한 경계다.
