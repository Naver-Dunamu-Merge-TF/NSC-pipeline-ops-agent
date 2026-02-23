# LangGraph shim 재평가 보고서 (i-98nn)

- 작성 시각 (UTC): 2026-02-23 13:20
- 대상 이슈: `i-98nn`
- 선행 근거: ADR-0006, ADR-0010, `docs/reports/2026-W08-langgraph-shim-reassessment.md`

## 1) 2~4주 창 기준 CI L2 재집계

### 데이터 소스

- GitHub Actions `CI L2` 런 이력: `gh run list --workflow "CI L2"`
- 런 상세 스텝 확인: `gh run view <run_id> --json jobs`
- 워크플로 정의(현재 저장소): `.github/workflows/ci-l2.yml`

### 재현 커맨드

- `gh run list --workflow "CI L2" --json databaseId,headBranch,status,conclusion,createdAt,updatedAt,url --limit 300`
- `python3` 집계 스크립트로 14일/28일 창 완료 런(pass/fail) 계산
- `python3` + `gh run view <run_id> --json jobs`로 스텝명(`Verify LangGraph runtime imports`, `Run L2 verification`) 존재/성공 여부 확인

### 집계 결과 (UTC)

| 구간 | 창 기준 | completed 표본수 | success | failure/회귀 | 통과율 |
|---|---|---:|---:|---:|---:|
| 2주 창 | 2026-02-09 ~ 2026-02-23 | 9 | 9 | 0 | 100.0% |
| 4주 창 | 2026-01-26 ~ 2026-02-23 | 9 | 9 | 0 | 100.0% |

- 실제 관측 커버리지: 2026-02-20 ~ 2026-02-21 (2일)
- completed 전체 표본: 9건

### 정식 경로(import gate + L2 test) 스텝 근거

- `Run L2 verification` 스텝: 9/9 런에서 존재 + success
- `Verify LangGraph runtime imports` 스텝: 0/9 런에서 확인됨(해당 런들의 job step 목록에 미포함)

해석:

- L2 테스트 자체는 회귀 없이 통과했지만, ADR-0006/0010이 요구한 "정식 경로(import gate + L2 test)"를 CI 런 이력만으로 동일 기간에 입증할 표본은 부족하다.
- 특히 import gate 스텝이 확인되는 completed 런 표본이 0건이므로, 안정성 창 충족 판정은 보수적으로 미충족으로 둔다.

## 2) shim 축소/strict failover 전환 재평가

### 옵션별 판단

- 옵션 A: shim 축소(부트스트랩 최소 경로)
  - 판단: **보류**
  - 근거: import gate 스텝이 포함된 CI 표본이 없어 "정식 경로 안정"을 충족했다고 보기 어렵다.
- 옵션 B: strict failover 전환(미설치 즉시 실패)
  - 판단: **보류**
  - 근거: 부트스트랩 안전망 제거 전 필요한 안정성 창 근거가 부족하다.
- 옵션 C: shim 유지(현상 유지)
  - 판단: **채택**
  - 근거: 현재 가용 증거에서 회귀는 없지만, 안정성 창 트리거 충족 증거가 부족해 보수적 운영이 타당하다.

## 3) 최종 판정

- ADR-0010 재평가 트리거(2~4주 안정성 창) 판정: **미충족**
- 결정: **LangGraph fallback shim 유지**, shim 축소/strict failover 전환은 다음 재평가까지 보류

## 4) 원시 런 근거 (completed)

- 22228728276 — https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22228728276
- 22229311958 — https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22229311958
- 22255342893 — https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22255342893
- 22258995859 — https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22258995859
- 22260074248 — https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22260074248
- 22261417434 — https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22261417434
- 22261453897 — https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22261453897
- 22261581845 — https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22261581845
- 22261594456 — https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/actions/runs/22261594456
