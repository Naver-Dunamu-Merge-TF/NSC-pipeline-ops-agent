# LangGraph shim 재평가 보고서 (DEV-054)

- 작성 시각 (UTC): 2026-02-23 08:40
- 대상 이슈: `i-81e1` (DEV-054)
- 근거 기준: ADR-0006(`docs/adr/0006-add-langgraph-fallback-shim.md`)

## 1) CI/운영 안정성 지표 (최근 2~4주 요청 대비 가용 데이터)

### 데이터 소스

- GitHub Actions `CI L2` 워크플로 런 이력(`gh run list --workflow "CI L2"`)
- 워크플로 정의: `.github/workflows/ci-l2.yml`
  - `Verify LangGraph runtime imports` 단계에서 `langgraph.graph` import와 `langgraph.checkpoint.sqlite.SqliteSaver` import를 게이트로 강제

### 추출 범위/필터(재현 가능 기준)

- 브랜치 범위: 필터 없음(전체 `headBranch` 포함)
- 기간 필터(UTC): `createdAt >= 2026-02-20T00:00:00Z` and `createdAt < 2026-02-22T00:00:00Z`
- 결론 기준: `status == completed` 런만 집계, 성공=`conclusion == success`, 실패/회귀=`conclusion != success`
- 재현 커맨드:
  - `gh run list --workflow "CI L2" --json databaseId,headBranch,status,conclusion,createdAt,url --limit 100`

### 원시 근거(런 ID/링크)

- 2026-02-20~2026-02-21 기간 `status=completed` 런 9건(모두 `conclusion=success`)
- run_id 22261594456: https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22261594456
- run_id 22261581845: https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22261581845
- run_id 22261453897: https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22261453897
- run_id 22261417434: https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22261417434
- run_id 22260074248: https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22260074248
- run_id 22258995859: https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22258995859
- run_id 22255342893: https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22255342893
- run_id 22229311958: https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22229311958
- run_id 22228728276: https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22228728276

### 관측 결과

- 관측 가능 기간: 2026-02-20 ~ 2026-02-21 (약 2일, 2~4주 요구 대비 짧음)
- `CI L2` 완료 런: 9건
- 성공: 9건
- 실패/회귀: 0건
- 통과율: 100%

### 해석

- 현재까지는 정식 경로(`requirements.txt` 기반 설치 + import 게이트 + L2 pytest/cov)가 안정적으로 통과한다.
- 다만 저장소/워크플로 가동 이력이 짧아, 2~4주 창에서의 신뢰도 높은 추세 판단에는 표본이 부족하다.

## 2) shim 유지 비용 점검 (저장소 근거)

### 코드/테스트/문서 동기화 접점

- 코드: `graph/graph.py`
  - 정식 경로(`_build_langgraph`)와 fallback 경로(`_CompiledGraphShim`)를 함께 유지
- 테스트:
  - `tests/unit/test_graph_build_and_smoke.py` (그래프 구조/스모크)
  - `tests/unit/test_graph_langgraph_dependency_policy.py` (정식 경로 실패 전파 + 미설치 fallback)
- 문서:
  - `.specs/ai_agent_spec.md` §LangGraph 의존성 정책
  - `docs/adr/0006-add-langgraph-fallback-shim.md`
  - `.github/workflows/ci-l2.yml` (정식 경로 import 게이트)

### 최근 4주 변경량(파일 단위 churn)

- `graph/graph.py`: 3회 터치, +269/-5
- `tests/unit/test_graph_build_and_smoke.py`: 1회 터치, +57/-0
- `tests/unit/test_graph_langgraph_dependency_policy.py`: 1회 터치, +56/-0
- `.github/workflows/ci-l2.yml`: 2회 터치, +80/-9
- `.specs/ai_agent_spec.md`: 7회 터치, +1390/-22
- `docs/adr/0006-add-langgraph-fallback-shim.md`: 2회 터치, +36/-2

### 유지 비용 해석

- shim 유지로 인해 코드 경로와 테스트/문서 동기화 포인트가 늘어나는 것은 사실이다.
- 다만 관측 기간 내 CI 회귀(실패 런)가 없어, 현재 시점의 회귀 빈도는 높지 않다.
- 비용 성격은 "즉시 장애 유발형"보다는 "향후 LangGraph API 변경 시 동기화 누락 위험"에 가깝다.

## 3) ADR-0006 조건 충족 여부 및 권고

### 조건 점검

- 조건 A: 로컬 개발 표준(`.venv` + `requirements-dev.txt`)에서 정식 경로 동작
  - 현황: 본 이슈 범위 재검증 기준 충족(아래 커맨드 기준)
  - 검증 근거(재현 가능):
    - 실행 시각(UTC): `2026-02-23T08:44:16Z`
    - 실행 컨텍스트: `/home/salee/dev/NSC-pipeline-ops-agent/.worktrees/i-81e1-dev-054`, `Python 3.13.5`
    - 실행 커맨드: `python3 -m pytest tests/unit/test_graph_build_and_smoke.py tests/unit/test_graph_langgraph_dependency_policy.py -q`
    - 결과 요약: `5 passed in 0.10s` (fail 0)
- 조건 B: CI L2에서 `langgraph.graph` + `SqliteSaver` import 및 그래프 스모크 연속 안정 통과
  - 현황: 부분 충족(가용 런은 100% 통과이나 관측 기간이 2일로 짧음)

### 권고안

- **권고: shim 유지(현상 유지) + 다음 재평가 시점 확정**
  - 이유 1) 현재 데이터는 모두 양호하나, 2~4주 요구 창을 만족하는 표본이 아직 부족함
  - 이유 2) 성급한 제거/축소는 부트스트랩 환경에서의 안전망을 잃을 수 있음
  - 이유 3) 회귀 빈도는 낮아 당장 제거로 얻는 이익보다, 추가 관측 후 결정의 안정성이 큼

### 다음 재평가 트리거

- 최소 14일 이상 추가 누적해 총 2~4주 창 확보
- 동일 기간 `CI L2`에서 정식 경로 게이트 및 L2 테스트 무회귀 유지 여부 재확인
- 위 조건 충족 시 shim 축소(부트스트랩 최소 경로) 또는 strict failover 전환 재판단
