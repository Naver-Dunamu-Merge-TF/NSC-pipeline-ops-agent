# ADR-260225-1716: use nonfatal skip for unknown target pipelines

## Created At

2026-02-25 17:16 KST

## Status

PendingReview

## Context

DEV-019의 구현 범위는 watchdog polling 단계에서 TARGET_PIPELINES에 명시된 대상만 순회하며 상태를 수집하고, 수집 결과를 운영 관점에서 안정적으로 보고하는 것이다. 그러나 운영 설정이나 환경 차이로 TARGET_PIPELINES에 현재 지원 목록에 없는 값이 포함될 수 있었고, 이 경우 기본 처리 규칙이 없으면 배치 전체 실패 또는 구현마다 상이한 동작으로 이어질 위험이 있었다. 따라서 watchdog polling의 가용성을 유지하기 위한 unknown TARGET_PIPELINES 입력의 일관된 기본 동작 정의가 필요했다.

## Decision

watchdog polling에서 알 수 없는 TARGET_PIPELINES 항목은 별도 경고 로그 없이 해당 항목만 비치명적으로 건너뛰는 기본 동작을 적용하기로 결정한다.

## Rationale

대안으로는 즉시 실패(fail-fast), 경고 후 건너뛰기(warning+skip), 무음 건너뛰기(silent-skip)를 검토했다. fail-fast는 잘못된 설정을 빠르게 드러내는 장점이 있지만 DEV-019의 저영향 범위에서 단일 오입력으로 전체 polling을 중단시켜 운영 가용성을 과도하게 해친다. warning+skip는 원인 가시성 측면에서는 유리하지만 현재 구현 동작과 일치하지 않는다. silent-skip는 미지원 항목만 제외하고 나머지 대상을 계속 수집해 polling 연속성을 유지하며, 실제 runtime/watchdog.py의 동작을 가장 정확히 반영하므로 구현 정합성 기준에서 채택했다.
