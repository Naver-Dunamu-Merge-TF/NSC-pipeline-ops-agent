# ADR-0023: default-stdout-jsonl-for-langfuse-smoke

## Created At

2026-02-25 01:30 KST

## Status

Confirmed

## Context

LangFuse UI 스모크 실행 증거를 운영 로그에서 즉시 수집해야 하고, 기본 동작이 환경 간에 동일해야 하며, 필요 시 기존 파일 기반 수집 흐름도 유지해야 했다.

## Decision

LangFuse UI 스모크 증거의 기본 수집 방식은 stdout JSON 라인 출력으로 하고, 환경 변수가 설정된 경우에만 동일 페이로드를 지정 파일에 append 하도록 결정한다.

## Rationale

기본 파일 기록 방안은 로그 파이프라인과 분리되어 컨테이너/CI 환경에서 수집 누락 위험이 커 기각했다. stdout과 파일 동시 기본 출력 방안은 중복 기록과 운영 비용 증가, 소비자 중복 처리 부담 때문에 기각했다. 기본 stdout + 선택적 파일 append 조합은 관측 가능성과 하위 호환 요구를 함께 충족하며 설정 부담을 최소화한다.
