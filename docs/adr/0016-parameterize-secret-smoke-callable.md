# ADR-0016: Parameterize Secret Smoke Callable

## Created At

2026-02-24 19:50 KST

## Status

Confirmed

## Context

i-1mok 범위는 ADR-0015 규약을 운영 smoke 절차에 반영하는 과정에서 발생한 실행 경로 선택 결정을 정리하는 것이다. dev Databricks 비밀값 smoke 검증은 문서/런북 절차에서 `get_secret` 호출 가능 여부를 빠르게 확인하는 운영 점검 성격을 가지며, 이 ADR은 core secret-resolution 규칙(환경 변수 우선, SecretScopeNormalization 정규화, workspace/env 기준 scope precedence, `secret_class` 분류)을 변경하지 않는다. 이번 결정 대상은 해당 규약을 유지한 상태에서 smoke 명령의 엔트리포인트를 어떤 방식으로 해석할지로 한정된다.

## Decision

dev Databricks secret 운영 smoke 절차의 엔트리포인트 지정 방식은 `get_secret` import 경로를 하드코딩하지 않고 운영자가 제공하는 환경 변수 `GET_SECRET_CALLABLE=module.path:get_secret`를 해석하는 것으로 결정한다.

## Rationale

선택한 방식은 smoke 검증의 목적(호출 가능성 확인)에 집중하면서 코드/문서 결합도를 낮추고, 환경별 차이를 운영 입력으로 흡수할 수 있어 runbook 변경 빈도를 줄인다. 또한 기존 검증 흐름을 유지한 채 설정값만 바꿔 동일 절차를 재사용할 수 있어 저영향(low-impact) 의사결정에 부합한다.

고려한 대안 1은 `get_secret` import 경로를 단일 모듈로 하드코딩하는 방식이었으나, 경로 변경 시 smoke 실패가 기능 이상과 경로 드리프트를 구분하지 못해 운영 신뢰도가 떨어지므로 기각했다. 대안 2는 가능한 엔트리포인트를 코드 내 목록으로 두고 순차 탐색하는 방식이었으나, smoke 검증 범위를 넘어선 복잡성을 추가하고 실패 원인 가시성을 낮추므로 기각했다. 대안 3은 매 실행 시 runbook 본문에서 경로를 직접 수정하도록 하는 방식이었으나, 수동 편집으로 인한 오류 가능성과 절차 일관성 저하가 커서 기각했다.
