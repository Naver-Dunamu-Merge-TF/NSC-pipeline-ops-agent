# ADR-0001: fix-databricks-job-mapping-schema

## Status

Accepted

## Context

`DEV-008` 구현 시점에 Databricks Job 매핑의 구체 스키마(평면 키 vs 중첩 키, 액션 집합 확장 범위)가 명시적으로 고정되어 있지 않았다. 실행기가 파이프라인/액션 조합으로 Job ID를 조회해야 하므로, 운영자가 값을 수정할 때 실수 가능성이 낮고 검증이 단순한 형태가 필요했다. 또한 현재 요구 범위는 "올바른 Job 호출"이므로 과도한 확장 설계를 피해야 했다.

## Decision

Databricks Job 매핑은 `jobs.<pipeline>.<action>` 중첩 구조로 고정하고 현재 액션은 `refresh` 단일 키로 제한하기로 결정한다.

## Rationale

대안 1인 평면 키(`pipeline.action: job_id`)는 파일 길이가 짧아지는 장점이 있지만, 파이프라인 단위 가독성이 떨어지고 중복 키 검증 시 오류 위치 파악이 불편하다. 대안 2인 다중 액션 선제 도입(`refresh`, `backfill`, `retry` 등)은 미래 확장에는 유리하지만 현재 요구에 없는 필드 검증과 문서 부담을 늘린다. 최종 선택인 중첩 + 단일 액션은 현재 DoD를 충족하는 최소 구조이며, 이후 액션 추가 시 스키마 확장 경로가 명확하고 되돌리기 쉬운 트레이드오프를 제공한다.
