# ADR-0001: define-action-plan-parameter-schema

## Status

Accepted

## Context

DEV-007은 execute 단계가 허용된 조치만 수행하도록 `action` 화이트리스트와 액션별 파라미터 검증을 요구한다. 스펙에서는 `backfill_silver`의 예시 필수 파라미터(`pipeline`, `date_kst`, `run_mode`)만 명시되어 있고, `retry_pipeline`과 `skip_and_report`의 최소 필수 파라미터는 구체화되어 있지 않다. 또한 `date_kst`의 형식 허용 범위(예: `YYYY-MM-DD` 엄격 고정 vs 느슨한 날짜 파서 허용)도 구현 시점에 결정이 필요했다.

## Decision

`backfill_silver`는 `pipeline/date_kst/run_mode`, `retry_pipeline`은 `pipeline/run_mode`, `skip_and_report`는 `pipeline/reason`을 각각 필수 파라미터로 고정하고 허용되지 않은 추가 파라미터를 거부하며, `date_kst`는 `YYYY-MM-DD` 형식만 허용하도록 결정한다.

## Rationale

이 결정은 execute 입력을 최소한의 명시적 스키마로 제한해 오작동 가능성을 줄이기 위한 것이다. 대안 1은 `retry_pipeline`과 `skip_and_report`를 느슨한 자유 파라미터(dict any)로 두는 방법이었지만, 이 경우 제안/수정 단계에서 오타나 불필요 키가 조용히 통과되어 실행 경계가 약해진다. 대안 2는 `skip_and_report` 파라미터를 완전히 비워 두는 방법이었지만, 어떤 파이프라인 맥락에서 스킵했는지와 사유를 일관되게 남기기 어렵다. 대안 3은 날짜를 범용 파서로 허용하는 방법이었지만, `2026-2-3` 같은 표현이 혼재되어 운영 로그와 재현성이 떨어진다. 따라서 액션별 필수 키를 명시하고 추가 키를 금지하며, 날짜 형식을 엄격히 고정하는 현재 선택이 가장 보수적이고 검증 가능한 경계다.
