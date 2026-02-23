# ADR-0011: reaffirm-langgraph-shim-until-formal-path-window

## Created At

2026-02-23 22:25 KST

## Status

PendingReview

## Context

ADR-0010은 2~4주 안정성 창(정식 경로 import 게이트 + L2 테스트 연속 안정 통과) 충족 전까지 LangGraph fallback shim을 유지하도록 결정했고, 이후 누적 지표로 shim 축소 또는 strict failover 전환 가능성을 재평가하도록 요구했다.
i-98nn에서 GitHub Actions `CI L2` 최근 2주/4주 창을 재집계한 결과 completed 런은 각각 9건, 성공 9건, 실패 0건으로 통과율은 100%였다. 그러나 실제 관측 커버리지는 2026-02-20~2026-02-21의 2일에 한정되며, 런 상세 스텝 기준 `Run L2 verification`은 9/9 성공이지만 `Verify LangGraph runtime imports` 스텝은 9개 런 중 확인된 건이 0건이어서 "정식 경로(import gate + L2 test)" 창 기준을 충족했다고 보기 어렵다.
위 근거는 `docs/reports/2026-W09-langgraph-shim-reassessment.md`에 집계 기준, 재현 커맨드, run_id 링크와 함께 기록한다.

## Decision

2~4주 안정성 창에서 정식 경로(import gate + L2 test) 증거가 충족될 때까지 LangGraph fallback shim을 유지하고 shim 축소/strict failover 전환은 보류하기로 결정한다.

## Rationale

대안 1은 shim을 즉시 부트스트랩 최소 경로로 축소하는 방안이었으나, import gate 스텝이 포함된 CI 표본이 없어 정식 경로의 연속 안정성을 입증하지 못해 채택하지 않았다.
대안 2는 미설치 환경 strict failover로 즉시 전환하는 방안이었으나, 부트스트랩 안전망 제거 시 운영 실패 복원력이 낮아질 수 있고 안정성 창 미충족 상태에서의 전환 리스크가 커 기각했다.
대안 3인 현상 유지는 단기 단순화 이점은 작지만, 현재 가용 지표에서 회귀는 없고 부족한 근거를 명시적으로 보존한 채 다음 관측 창에서 재판단할 수 있어 의사결정 품질과 운영 안전성의 균형이 가장 높다.
