# ADR-0018: status 키 보존을 위한 NULL 캐스팅

## Created At

2026-02-24 23:55 KST

## Status

PendingReview

## Context

`DEV-014-INFRA-SMOKE` 수행 중 `gold.pipeline_state`에 `status` 컬럼이 존재하지 않아 스모크 검증이 실패했다. 해당 스모크는 query-spec의 shape를 기준으로 결과 키 집합을 검증하므로, 실제 소스 컬럼 유무와 무관하게 `status` 키가 유지되어야 하며 출력 스키마의 후방 호환성이 필요했다.

## Decision

`gold.pipeline_state` 스모크에서 query-spec shape의 `status` 키를 보존하기 위해 `CAST(NULL AS STRING) AS status`를 사용하도록 결정한다.

## Rationale

대안 1은 `status` 키 자체를 query-spec에서 제거하는 방식이었으나, 기존 검증 계약과 소비자 기대 스키마를 깨뜨려 후방 호환성을 훼손하므로 기각했다. 대안 2는 업스트림 테이블에 `status` 컬럼을 즉시 추가하는 방식이었으나, 인프라 변경 범위와 배포 리스크가 커서 스모크 복구 목적에 비해 과도하므로 기각했다. 대안 3은 빈 문자열 같은 상수 리터럴을 `status`로 채우는 방식이었으나, 값이 존재하는 것처럼 오해를 유발해 의미적 정확성이 떨어지므로 기각했다. `CAST(NULL AS STRING) AS status`는 키 shape를 유지하면서 데이터 부재를 명시하고 타입 일관성까지 확보해 현재 문제를 최소 변경으로 해결한다.
