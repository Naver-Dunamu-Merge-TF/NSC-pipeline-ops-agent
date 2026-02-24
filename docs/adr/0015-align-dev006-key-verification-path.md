# ADR-0015: DEV-006 경로 기준 정렬

## Created At

2026-02-24 19:18 KST

## Status

Confirmed

## Context

DEV-006 이슈의 DoD에는 `utils/config.py`와 `utils/secrets.py`가 참조되었지만, 저장소의 실제 소스 기준 경로는 `src/orchestrator/utils/config.py`이며 `secrets.py` 파일은 존재하지 않았다. 이 불일치는 키 이름 검증 대상과 문서 근거를 혼동시켜 검증 결과의 추적 가능성을 떨어뜨릴 수 있어, 실제 코드 기준으로 참조 대상을 명확히 고정할 필요가 있었다.

## Decision

DEV-006에서는 키 이름 검증과 관련 문서 참조를 저장소의 실제 코드 경로인 `src/orchestrator/utils/config.py` 기준으로 정렬하고 존재하지 않는 `utils/secrets.py` 참조는 제외하기로 결정한다.

## Rationale

실제 존재하는 코드 경로를 단일 기준으로 삼으면 검증 범위와 근거 문서가 일치해 리뷰와 재검증이 단순해진다. DoD 문구를 그대로 유지하는 대안은 즉시 작업은 줄일 수 있지만 잘못된 파일 참조를 계속 전파해 후속 이슈에서 동일한 혼선을 반복할 가능성이 높아 기각했다. `secrets.py`를 새로 추가해 DoD를 맞추는 대안도 있었으나 이번 결정의 목적은 누락 파일 보완이 아니라 기존 검증 기준 정합성 확보이므로 범위를 벗어나 기각했다.
