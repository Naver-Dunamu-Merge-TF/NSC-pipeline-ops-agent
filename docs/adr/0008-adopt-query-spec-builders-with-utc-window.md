# ADR-0008: adopt-query-spec-builders-with-utc-window

## Created At
2026-02-23 17:35 KST

## Status
Confirmed

## Context
DEV-014에서 `data_collector`와 `collect_pipeline_context`의 쿼리 조합 방식을 정리하는 과정에서, 쿼리 정의의 일관성과 시간 범위 기본값의 예측 가능성을 함께 확보해야 했다. 특히 `dq_status`와 `exception_ledger`는 동일한 문맥에서 호출되므로, 호출자가 기간을 명시하지 않아도 재현 가능한 기본 조회 구간이 필요했다.

## Decision
`data_collector`는 `{sql, params, result_shape}`를 반환하는 순수 query-spec builder를 사용하고, `collect_pipeline_context`는 `dq_status`/`exception_ledger` 쿼리 조합 시 기본값으로 UTC 기준 최근 24시간 윈도우를 적용하기로 결정한다.

## Rationale
쿼리 문자열을 실행 로직과 분리해 query-spec으로 고정하면 테스트와 재사용이 쉬워지고, `result_shape`를 함께 명시해 후속 처리의 기대 스키마를 명확히 할 수 있다. 기본 시간 범위를 UTC 24시간으로 통일하면 환경별 로컬 타임존 차이로 인한 해석 불일치를 줄이면서도 운영 영향이 작은 보수적 기본값을 제공한다. 대안으로 호출 지점마다 임의 기간을 강제하거나 로컬 타임존 기본값을 두는 방법을 검토했지만, 전자는 호출 부담이 커지고 후자는 실행 환경에 따라 결과 일관성이 떨어져 채택하지 않았다.

추가 점검 결과, 현재 코드 기준 query-spec 계약 소비 경로는 `collect_pipeline_context()`가 `pipeline_state`/`dq_status`/`exception_ledger` 각각에 대해 `{sql, params, result_shape}` 구조를 유지한 채 반환하는 형태로 일관된다. `detect`/`collect` 노드는 아직 스켈레톤 단계라 SQL 실행까지 연결되지는 않았지만, state read/write 계약 테스트와 data_collector 단위 테스트로 query-spec 구조 가정이 깨지지 않음을 확인했다.

UTC 최근 24시간 기본 윈도우는 운영 기본값으로 유지하되, 아래 트리거가 발생하면 기간 재평가를 수행한다.

- **과다 조회 트리거**: `dq_status` + `exception_ledger` 조회 합계가 단일 incident에서 10,000건을 반복적으로 초과(1일 2회 이상)하거나 collect 단계 처리 지연이 반복될 때. 대응: 기본 윈도우를 12시간으로 축소하는 실험안을 우선 검토하고, 필요 시 파티션/추가 필터를 병행한다.
- **과소 조회 트리거**: 운영자가 원인 분석에 필요한 레코드가 24시간 밖에서 누락됐음을 확인한 사례가 1회라도 발생하거나, 동일 파이프라인에서 최근 7일 대비 유의미한 이슈가 있는데 24시간 조회 결과가 연속 3회 비정상적으로 비어 있을 때. 대응: 기본 윈도우를 48시간으로 확장하는 안을 우선 검토하고, detect/collect에서 run_id 기반 보강 조회를 병행한다.
