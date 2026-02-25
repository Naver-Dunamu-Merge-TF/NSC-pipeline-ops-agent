# ADR-260225-1716: use nonfatal skip for unknown target pipelines

## Created At

2026-02-25 17:16 KST

## Status

Confirmed

## Context

DEV-019의 구현 범위는 watchdog polling 단계에서 TARGET_PIPELINES에 명시된 대상만 순회하며 상태를 수집하고, 수집 결과를 운영 관점에서 안정적으로 보고하는 것이다. 그러나 운영 설정이나 환경 차이로 TARGET_PIPELINES에 현재 지원 목록에 없는 값이 포함될 수 있었고, 이 경우 기본 처리 규칙이 없으면 배치 전체 실패 또는 구현마다 상이한 동작으로 이어질 위험이 있었다. 따라서 watchdog polling의 가용성을 유지하기 위한 unknown TARGET_PIPELINES 입력의 일관된 기본 동작 정의가 필요했다.

## Decision

watchdog polling에서 알 수 없는 TARGET_PIPELINES 항목은 경고 로그(`Unknown target pipeline skipped: <pipeline>`)를 남기고, 해당 항목만 비치명적으로 건너뛰는 `warning+skip` 기본 동작을 적용한다.

## Rationale

대안으로는 즉시 실패(fail-fast), 경고 후 건너뛰기(warning+skip), 무음 건너뛰기(silent-skip)를 검토했다. fail-fast는 잘못된 설정을 빠르게 드러내지만 단일 오입력으로 전체 polling을 중단시켜 운영 가용성을 과도하게 해친다. silent-skip는 가용성은 유지하지만 설정 오류의 원인 가시성이 부족해 운영 탐지 시간이 길어진다. warning+skip는 polling 연속성(availability)을 유지하면서도 경고 로그로 원인 가시성(visibility)을 확보해 운영 트레이드오프를 가장 균형 있게 만족하므로 최종 정책으로 채택한다.
