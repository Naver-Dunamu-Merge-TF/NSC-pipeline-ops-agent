# ADR-0008: adopt-query-spec-builders-with-utc-window

## Created At
2026-02-23 17:35 KST

## Status
PendingReview

## Context
DEV-014에서 `data_collector`와 `collect_pipeline_context`의 쿼리 조합 방식을 정리하는 과정에서, 쿼리 정의의 일관성과 시간 범위 기본값의 예측 가능성을 함께 확보해야 했다. 특히 `dq_status`와 `exception_ledger`는 동일한 문맥에서 호출되므로, 호출자가 기간을 명시하지 않아도 재현 가능한 기본 조회 구간이 필요했다.

## Decision
`data_collector`는 `{sql, params, result_shape}`를 반환하는 순수 query-spec builder를 사용하고, `collect_pipeline_context`는 `dq_status`/`exception_ledger` 쿼리 조합 시 기본값으로 UTC 기준 최근 24시간 윈도우를 적용하기로 결정한다.

## Rationale
쿼리 문자열을 실행 로직과 분리해 query-spec으로 고정하면 테스트와 재사용이 쉬워지고, `result_shape`를 함께 명시해 후속 처리의 기대 스키마를 명확히 할 수 있다. 기본 시간 범위를 UTC 24시간으로 통일하면 환경별 로컬 타임존 차이로 인한 해석 불일치를 줄이면서도 운영 영향이 작은 보수적 기본값을 제공한다. 대안으로 호출 지점마다 임의 기간을 강제하거나 로컬 타임존 기본값을 두는 방법을 검토했지만, 전자는 호출 부담이 커지고 후자는 실행 환경에 따라 결과 일관성이 떨어져 채택하지 않았다.
