# ADR-0004: place-ai-agent-skeleton-at-repo-root

## Status

Accepted (temporary for DEV-009 skeleton scope)

## Context

`.specs/ai_agent_spec.md` §4.2는 `graph/`, `tools/`, `utils/`, `llmops/`, `prompts/`를 `project/` 루트 구조로 제시한다. 반면 현재 저장소의 기존 운영 코드(`src/sudocode_orchestrator`)는 `src/` 패키지 레이아웃을 사용하고 있어, 신규 스켈레톤 위치를 어디에 둘지 해석 여지가 있었다. 이번 이슈 범위는 스켈레톤 생성과 import 가능성 검증에 한정되므로, 기존 오케스트레이터 코드 구조를 건드리지 않는 배치 기준이 필요했다.

## Decision

DEV-009 스코프에서는 AI 에이전트 스켈레톤 디렉터리를 스펙 §4.2의 project/ 최상위 구조에 맞춰 저장소 루트(`graph/`, `tools/`, `utils/`, `llmops/`, `prompts/`)에 생성한다. 이 결정은 스켈레톤/계약 검증 범위에 한정되며, 런타임 패키징 표준(`src/` 통합 여부 포함)을 확정하지 않는다.

## Rationale

대안 1은 신규 스켈레톤을 `src/` 하위로 배치하는 방식이었으나, 스펙의 구조 예시와 직접 대응이 약해져 초기 온보딩 시 혼선을 만들 수 있어 기각했다. 대안 2는 루트 배치를 하되 기존 테스트 경로만 유지하는 방식이었으나, 이 경우 신규 모듈 import 확인이 불완전해진다. 최종안은 루트 배치를 선택하고, 신규 테스트에서 루트 경로를 명시적으로 `sys.path`에 추가해 import 로딩을 검증하는 방식이다. 이 접근은 기존 `src/sudocode_orchestrator` 동작을 건드리지 않으면서도 스펙 구조와 테스트 검증 요구를 동시에 만족한다.

## Consequences / Follow-ups

- 테스트 경로/패키징 기준 혼합 상태와 후속 통일 필요
- 루트 일반명 패키지 네임스페이스 충돌 가능성과 재평가 필요
- 본 ADR이 위치 확정이 아닌 초기 스켈레톤 배치 결정임을 명시하고 후속 ADR 가능성
