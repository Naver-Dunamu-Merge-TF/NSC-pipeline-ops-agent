# ADR-0006: add-langgraph-fallback-shim

## Created At

2026-02-23 03:49 KST

## Status

PendingReview

## Context

- `.specs/ai_agent_spec.md` §2.1은 에이전트 흐름을 LangGraph 상태 그래프로 정의하도록 요구한다.
- DEV-010 범위에서는 전체 노드/엣지 구조를 코드에 연결하고, 최소 1개 경로가 `graph.invoke`로 END까지 도달해야 한다.
- ADR 결정 시점 기준으로 로컬/테스트 환경에는 `langgraph` 패키지가 설치되어 있지 않아, LangGraph 직접 import만 사용하면 그래프 스모크 테스트 자체를 수행할 수 없었다.

## Decision

런타임에서 `langgraph.graph` 디스커버리(`importlib.util.find_spec("langgraph.graph")`)가 가능하면 실제 LangGraph를 사용하고, 디스커버리가 불가능하면(패키지 미설치로 `ModuleNotFoundError`가 발생하는 경우 포함) 동일한 노드/조건 엣지 계약을 따르는 최소 실행용 fallback shim으로 `build_graph()`를 동작시키는 방식으로 결정한다.

## Rationale

- 대안 1: `langgraph` 직접 import를 강제하고 패키지 설치를 전제로 한다.
  - 장점: 런타임 경로가 단일하다.
  - 단점: 현재 저장소의 테스트 실행 환경에서 즉시 실패하며, DEV-010의 로컬 스모크 검증을 막는다.
- 대안 2: `langgraph`가 없으면 테스트를 skip한다.
  - 장점: 구현량이 적다.
  - 단점: 그래프 구조/분기 연결이 실제로 실행 가능한지 검증하지 못해 DoD의 "로컬 invoke 경로"를 만족하기 어렵다.
- 선택 대안: fallback shim을 추가한다.
  - 장점: 환경 의존성 없이 DEV-010의 그래프 연결성과 스모크 실행을 검증할 수 있고, `langgraph`가 설치되면 동일 코드 경로에서 실제 LangGraph로 전환된다.
  - 단점: 임시 shim 유지 비용이 생기며, 향후 LangGraph 정식 의존성 정비 시 제거/축소 여부를 재평가해야 한다.
- 후속 검토 항목(ADR-0006 추적):
  - shim 유지 비용: LangGraph API 변경(노드/엣지/체크포인터 계약 변경) 시 shim 동기화 부담이 누적되므로, 정식 의존성 경로가 CI에서 안정화되면 shim 범위를 부트스트랩 최소 경로로 축소한다.
  - 제거/축소 재평가 조건: 로컬 개발 표준(`.venv` + `requirements-dev.txt`)과 CI L2에서 `langgraph.graph` import + `langgraph.checkpoint.sqlite.SqliteSaver` import 및 그래프 스모크가 연속으로 안정 통과하면 shim 제거 또는 strict failover(미설치 시 즉시 실패)로 전환 여부를 재평가한다.
