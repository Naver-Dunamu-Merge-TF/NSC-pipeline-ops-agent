# Serverless UC Volume Checkpoint Transition Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** i-qva6 범위에서 SQLite 체크포인터는 단기 유지하되, Databricks serverless 체크포인트 경로를 `/dbfs/mnt/agent-state/checkpoints/agent.db`에서 `/Volumes/nsc_dbw_dev_7405610275478542/default/agent_state_checkpoints/agent.db`로 전환하고 strict 스모크 기준을 갱신한다.

**Architecture:** 애플리케이션 저장 엔진은 `langgraph-checkpoint-sqlite`를 그대로 유지하고, 경로 정책만 UC Volume 기준으로 교체한다. 검증은 TDD 형태로 `Red(/dbfs 실패 재현) -> Green(/Volumes 성공)` 2단계 증거를 확보하고, 스펙/런북/ADR/리포트를 동일 근거로 동기화한다.

**Tech Stack:** Databricks Jobs API, serverless environment spec v2, SQLite checkpointer (`SqliteSaver`), Sudocode issue/spec graph, Markdown docs (`.specs`, `docs/runbooks`, `docs/reports`, `docs/adr`)

---

## 범위와 전제 (i-qva6 고정)

- 이 계획은 `i-qva6` 맥락에서만 수행한다(다른 이슈 범위 확장 금지).
- 저장소 엔진 교체(Postgres 등) 없이 SQLite 유지가 원칙이다.
- 정책 변경 대상은 "serverless 체크포인트 경로"이며, 로컬 개발 기본값(`checkpoints/agent.db`)은 유지한다.
- 모든 변경은 증거(run id, 실패/성공 로그, 문서 diff)와 함께 남긴다.

## 실행 방식 강제: 서브에이전트 루프 (필수)

아래 루프를 모든 Task에 강제 적용한다.

1. **Implementer subagent**
   - 현재 Task의 파일 수정/명령 실행/증거 수집만 수행.
2. **Spec review subagent**
   - `.specs/ai_agent_spec.md`, `.specs/runtime_config.md`와 구현/증거 일치성 점검.
3. **Code-quality review subagent**
   - 변경 최소성, 오탈자, 깨진 링크, 명령 재현성, 문서 형식 점검.
4. **Fix-and-reverify loop**
   - 리뷰에서 blocker가 하나라도 나오면 즉시 수정 후 동일 검증 명령 재실행.
   - blocker가 0이 될 때까지 반복.

블로커 해소 전에는 다음 Task로 진행하지 않는다.

## 공통 변수 (세션 시작 시 1회)

Run:
```bash
export DATABRICKS_HOST="https://adb-7405610275478542.2.azuredatabricks.net"
export DATABRICKS_TOKEN="${DATABRICKS_TOKEN:?set DATABRICKS_TOKEN}"
export SOURCE_SMOKE_SCRIPT="/Workspace/Users/2dt026@msacademy.msai.kr/.bundle/data-pipeline/dev/files/scripts/i_qva6_dbfs_strict_smoke.py"
export RUNTIME_SMOKE_SCRIPT="/Workspace/Users/2dt026@msacademy.msai.kr/.bundle/data-pipeline/dev/files/scripts/i_qva6_checkpoint_path_smoke.py"
export CHECKPOINT_DBFS="/dbfs/mnt/agent-state/checkpoints/agent.db"
export UC_CATALOG="nsc_dbw_dev_7405610275478542"
export UC_SCHEMA="default"
export UC_VOLUME="agent_state_checkpoints"
export CHECKPOINT_VOLUMES="/Volumes/${UC_CATALOG}/${UC_SCHEMA}/${UC_VOLUME}/agent.db"
```
Expected: Red/Green/ADR 단계에서 재사용할 단일 변수 세트가 준비된다.

## Task 1: Red 기준선 고정 (`/dbfs` 실패 재현)

**Files:**
- Modify: `docs/reports/2026-02-25-adr-260225-1012-dbfs-strict-smoke-revalidation.md`

**Step 1: 기존 실패 기준 확인**

Run:
```bash
rg -n "Errno 5|/dbfs/mnt/agent-state/checkpoints|serverless" docs/reports/2026-02-25-adr-260225-1012-dbfs-strict-smoke-revalidation.md
```
Expected: 기존 `/dbfs` serverless 실패 근거 라인이 출력된다.

**Step 2: Red/Green 공용 런타임 스크립트 준비 (1회)**

Run:
```bash
databricks workspace export "$SOURCE_SMOKE_SCRIPT" /tmp/i_qva6_checkpoint_path_smoke.py --format SOURCE && databricks workspace import "$RUNTIME_SMOKE_SCRIPT" /tmp/i_qva6_checkpoint_path_smoke.py --format SOURCE --overwrite
```
Expected: `RUNTIME_SMOKE_SCRIPT`가 생성/갱신되고, Red/Green 모두 `--checkpoint-db-path` 파라미터만 바꿔 동일 스크립트를 사용한다.

**Step 3: Red 재실행 (serverless, /dbfs 파라미터)**

Run:
```bash
RED_SUBMIT_JSON="$(databricks jobs submit --no-wait --json '{
  "run_name": "i-qva6-red-dbfs-serverless",
  "tasks": [{
    "task_key": "red_dbfs_serverless",
    "environment_key": "smoke_serverless",
    "spark_python_task": {
      "python_file": "'$RUNTIME_SMOKE_SCRIPT'",
      "source": "WORKSPACE",
      "parameters": ["--checkpoint-db-path", "'$CHECKPOINT_DBFS'"]
    }
  }],
  "environments": [{
    "environment_key": "smoke_serverless",
    "spec": {"environment_version": "2"}
  }]
}' -o json)"
printf '%s\n' "$RED_SUBMIT_JSON" > /tmp/i_qva6_red_submit.json
export RED_PARENT_RUN_ID="$(python -c 'import json,sys; print(json.load(sys.stdin)["run_id"])' < /tmp/i_qva6_red_submit.json)"
printf 'RED_PARENT_RUN_ID=%s\n' "$RED_PARENT_RUN_ID"
```
Expected: run id 생성.

**Step 4: Red 실패 판정 수집 (poll + assert)**

Run:
```bash
while true; do
  RED_GET_RUN_JSON="$(databricks jobs get-run "$RED_PARENT_RUN_ID" -o json)"
  RED_LIFECYCLE_STATE="$(python -c 'import json,sys; print(json.load(sys.stdin)["state"]["life_cycle_state"])' <<< "$RED_GET_RUN_JSON")"
  printf 'RED lifecycle=%s\n' "$RED_LIFECYCLE_STATE"
  case "$RED_LIFECYCLE_STATE" in
    TERMINATED|SKIPPED|INTERNAL_ERROR) break ;;
  esac
  sleep 10
done
printf '%s\n' "$RED_GET_RUN_JSON" > /tmp/i_qva6_red_get_run.json
RED_RESULT_STATE="$(python -c 'import json,sys; print(json.load(sys.stdin)["state"].get("result_state", ""))' <<< "$RED_GET_RUN_JSON")"
python -c 'import sys; s=sys.argv[1]; assert s and s != "SUCCESS", f"Expected Red failure, got {s}"; print(f"Red assertion passed: {s}")' "$RED_RESULT_STATE"
export RED_TASK_RUN_ID="$(python -c 'import json,sys; d=json.load(sys.stdin); print(d["tasks"][0]["run_id"])' < /tmp/i_qva6_red_get_run.json)"
printf 'RED_TASK_RUN_ID=%s\n' "$RED_TASK_RUN_ID"
databricks jobs get-run-output "$RED_TASK_RUN_ID" -o json > /tmp/i_qva6_red_run_output.json
python -c 'import json; s=json.dumps(json.load(open("/tmp/i_qva6_red_run_output.json")), ensure_ascii=False); assert ("/dbfs" in s) or ("Errno 5" in s), "Expected boundary signal (/dbfs or Errno 5) in Red run output"; print("Red boundary signal assertion passed")'
```
Expected: terminal lifecycle 도달 후 `FAILED` 계열 상태이며, run output JSON 텍스트에 `/dbfs` 및/또는 `Errno 5` boundary signal이 명시적으로 검증된다.

**Step 5: 리포트에 Red 결과 추가**

- run id, UTC 시각, 핵심 오류 로그 1-3줄을 리포트에 추가.

## Task 2: Green 대상 경로 합의 (`$CHECKPOINT_VOLUMES`)

**Files:**
- Modify: `.specs/runtime_config.md`
- Modify: `.specs/ai_agent_spec.md`

**Step 1: 스펙 내 `/dbfs` 참조 위치 식별**

Run:
```bash
rg -n "/dbfs/mnt/agent-state/checkpoints/agent.db|CHECKPOINT_DB_PATH" .specs/runtime_config.md .specs/ai_agent_spec.md
```
Expected: 교체 대상 라인 목록 확인.

**Step 2: 경로 정책 문구 수정**

- serverless(prod/staging) 권장값을 `$CHECKPOINT_VOLUMES`로 변경.
- SQLite 유지(파일 포맷 동일) 문구를 같은 섹션에 명시.

**Step 3: strict smoke 정의 수정**

- strict smoke의 통과 조건을 `$CHECKPOINT_VOLUMES` 경로로 1회 성공 run 확보로 변경.

**Step 4: 문서 정합성 점검**

Run:
```bash
rg -n "/dbfs/mnt/agent-state/checkpoints/agent.db|${CHECKPOINT_VOLUMES}" .specs/runtime_config.md .specs/ai_agent_spec.md
```
Expected: serverless 기준은 `$CHECKPOINT_VOLUMES`가 우선 표기되고, `/dbfs`는 과거 실패 근거/이행 배경으로만 남는다.

## Task 3: Green 스모크 실행 (`/Volumes` 성공 증거)

**Files:**
- Modify: `docs/reports/2026-02-25-adr-260225-1012-dbfs-strict-smoke-revalidation.md`

**Step 1: UC Volume 생성/해결 가능 상태 확인 (Green 전 필수)**

Run:
```bash
databricks volumes get "${UC_CATALOG}.${UC_SCHEMA}.${UC_VOLUME}" -o json || databricks volumes create "${UC_CATALOG}.${UC_SCHEMA}.${UC_VOLUME}" --volume-type MANAGED -o json
databricks fs ls "/Volumes/${UC_CATALOG}/${UC_SCHEMA}/${UC_VOLUME}" >/dev/null
```
Expected: UC Volume이 존재하고 serverless에서 사용할 `/Volumes/...` 경로가 해석 가능하다.

**Step 2: Green 제출 (serverless, /Volumes 파라미터)**

Run:
```bash
GREEN_SUBMIT_JSON="$(databricks jobs submit --no-wait --json '{
  "run_name": "i-qva6-green-volumes-serverless",
  "tasks": [{
    "task_key": "green_volumes_serverless",
    "environment_key": "smoke_serverless",
    "spark_python_task": {
      "python_file": "'$RUNTIME_SMOKE_SCRIPT'",
      "source": "WORKSPACE",
      "parameters": ["--checkpoint-db-path", "'$CHECKPOINT_VOLUMES'"]
    }
  }],
  "environments": [{
    "environment_key": "smoke_serverless",
    "spec": {"environment_version": "2"}
  }]
}' -o json)"
printf '%s\n' "$GREEN_SUBMIT_JSON" > /tmp/i_qva6_green_submit.json
export GREEN_PARENT_RUN_ID="$(python -c 'import json,sys; print(json.load(sys.stdin)["run_id"])' < /tmp/i_qva6_green_submit.json)"
printf 'GREEN_PARENT_RUN_ID=%s\n' "$GREEN_PARENT_RUN_ID"
```
Expected: run id 생성.

**Step 3: Green 성공 판정 확인 (poll + assert)**

Run:
```bash
while true; do
  GREEN_GET_RUN_JSON="$(databricks jobs get-run "$GREEN_PARENT_RUN_ID" -o json)"
  GREEN_LIFECYCLE_STATE="$(python -c 'import json,sys; print(json.load(sys.stdin)["state"]["life_cycle_state"])' <<< "$GREEN_GET_RUN_JSON")"
  printf 'GREEN lifecycle=%s\n' "$GREEN_LIFECYCLE_STATE"
  case "$GREEN_LIFECYCLE_STATE" in
    TERMINATED|SKIPPED|INTERNAL_ERROR) break ;;
  esac
  sleep 10
done
printf '%s\n' "$GREEN_GET_RUN_JSON" > /tmp/i_qva6_green_get_run.json
GREEN_RESULT_STATE="$(python -c 'import json,sys; print(json.load(sys.stdin)["state"].get("result_state", ""))' <<< "$GREEN_GET_RUN_JSON")"
python -c 'import sys; s=sys.argv[1]; assert s == "SUCCESS", f"Expected Green success, got {s}"; print(f"Green assertion passed: {s}")' "$GREEN_RESULT_STATE"
```
Expected: terminal lifecycle 도달 후 최종 상태 `SUCCESS` 확인.

**Step 4: Green task run id 추출 + 출력 근거 확보**

Run:
```bash
export GREEN_TASK_RUN_ID="$(python -c 'import json,sys; d=json.load(sys.stdin); print(d["tasks"][0]["run_id"])' < /tmp/i_qva6_green_get_run.json)"
printf 'GREEN_TASK_RUN_ID=%s\n' "$GREEN_TASK_RUN_ID"
databricks jobs get-run-output "$GREEN_TASK_RUN_ID" -o json
```
Expected: 체크포인트 쓰기 성공을 뒷받침하는 로그/결과 JSON 라인 확보.

**Step 5: 리포트에 Green 결과 추가**

- Red/Green 비교 표(경로, run id, 결과, 핵심 로그) 1개 추가.

## Task 4: 런북 운영 절차 전환

**Files:**
- Modify: `docs/runbooks/ai-agent-infra-dev.md`

**Step 1: `/dbfs` strict smoke 문구 치환**

Run:
```bash
rg -n "DEV-013 checkpoint strict smoke boundary|CHECKPOINT_DB_PATH|/dbfs|strict" docs/runbooks/ai-agent-infra-dev.md
```
Expected: 교체 대상 섹션 확인.

**Step 2: 운영 절차를 `/Volumes` 기준으로 갱신**

- serverless 체크포인트 기본 경로를 `$CHECKPOINT_VOLUMES`로 명시.
- 장애 시 확인 순서(권한 -> 경로 존재 -> run output) 3단계로 정리.

**Step 3: 명령 재현성 확인**

Run:
```bash
rg -n "${CHECKPOINT_VOLUMES}|/dbfs/mnt/agent-state/checkpoints/agent.db" docs/runbooks/ai-agent-infra-dev.md
```
Expected: runbook 본문 기본값은 `/Volumes/...`만 남고 `/dbfs`는 전환 배경 참고로만 존재.

## Task 5: ADR 작성 (`/dbfs` -> `/Volumes` 정책 변경)

**Files:**
- Create: `docs/adr/260225-1155-transition-serverless-checkpoint-path-to-uc-volumes.md`

**Step 1: ADR ID/파일명 확정**

Run:
```bash
printf '%s\n' "docs/adr/260225-1155-transition-serverless-checkpoint-path-to-uc-volumes.md"
```
Expected: `docs/adr/260225-1155-transition-serverless-checkpoint-path-to-uc-volumes.md` 값으로 고정됨을 확인한다.

**Step 2: ADR 초안 작성**

- Decision: serverless에서 `/dbfs`를 기본 경로로 더 이상 사용하지 않음.
- Consequence: SQLite 유지, 경로만 `/Volumes/...`로 이행.
- Evidence: Task 1(Red) + Task 3(Green) run id 연결.

**Step 3: ADR 링크 정합성 확인**

Run:
```bash
rg -n "260225-1012|/dbfs|/Volumes|i-qva6" docs/adr/260225-1155-transition-serverless-checkpoint-path-to-uc-volumes.md
```
Expected: 기존 ADR-260225-1012와 후속 결정의 관계가 명시된다.

## Task 6: Sudocode 후속 이슈 처리 (의사결정 파생 작업)

**Files:**
- None (파일 직접 수정 금지, MCP 도구로만 state 갱신)

**Step 1: 후속 이슈 필요성 판단**

판단 기준(하나라도 true면 생성):
- UC Volume 권한/프로비저닝 자동화가 아직 수동.
- `/dbfs` 의존 코드/문서가 다른 경로에 잔존.
- 운영 알림/모니터링이 `/Volumes` 실패 시나리오를 다루지 못함.

**Step 2: 필요 시 후속 이슈 생성 + `NEW_ISSUE_ID` 추출 (MCP 호출, 필드 고정)**

Tool call:
```json
{
  "tool": "sudocode-mcp_upsert_issue",
  "input": {
    "title": "Follow-up: harden UC Volume checkpoint transition for serverless",
    "description": "Post-ADR follow-up from i-qva6. Scope: automate UC Volume provisioning/permissions, remove residual /dbfs references, and add /Volumes failure monitoring runbook steps.",
    "priority": 2,
    "status": "open",
    "tags": ["i-qva6", "adr", "serverless", "checkpoint", "uc-volume"]
  }
}
```

Run:
```bash
UPSERT_ISSUE_JSON='<paste sudocode-mcp_upsert_issue JSON response>'
export NEW_ISSUE_ID="$(python -c 'import json,sys; d=json.load(sys.stdin); c=[d.get("issue_id"), d.get("id"), (d.get("issue") or {}).get("issue_id"), ((d.get("data") or {}).get("issue") or {}).get("issue_id"), (d.get("data") or {}).get("issue_id")]; print(next(x for x in c if x))' <<< "$UPSERT_ISSUE_JSON")"
printf 'NEW_ISSUE_ID=%s\n' "$NEW_ISSUE_ID"
```

**Step 3: 이슈 링크 생성 (MCP 호출, 필드 고정)**

Tool call:
```json
{
  "tool": "sudocode-mcp_link",
  "input": {
    "from_id": "$NEW_ISSUE_ID",
    "to_id": "i-qva6",
    "type": "related"
  }
}
```

**Step 4: 구현 피드백 기록 (MCP 호출, 필드 고정)**

Tool call:
```json
{
  "tool": "sudocode-mcp_add_feedback",
  "input": {
    "issue_id": "$NEW_ISSUE_ID",
    "to_id": "i-qva6",
    "type": "comment",
    "content": "Created follow-up issue after ADR path transition decision. ADR file: docs/adr/260225-1155-transition-serverless-checkpoint-path-to-uc-volumes.md"
  }
}
```

Expected: 새 이슈 ID와 링크 관계를 ADR 또는 리포트에 기록.

## Task 7: 선택적 테스트 보강 (정말 필요할 때만)

**Files (Optional):**
- Create: `tests/smoke/test_serverless_checkpoint_path_policy.py`

**Step 1: Red 테스트 작성 (경로 정책 검증)**

예시(assertion만 최소):
- serverless 정책값이 `/dbfs/...`면 실패.
- `/Volumes/.../agent.db`면 통과.

**Step 2: 단일 테스트 실행**

Run:
```bash
pytest tests/smoke/test_serverless_checkpoint_path_policy.py -q
```
Expected: 신규 테스트 통과.

주의:
- 실제 런타임 스모크 증거(Task 1/3)를 대체하지 않는다.
- 코드 변경이 없고 문서/운영 절차만 갱신하는 경우 이 Task는 생략 가능.

## Task 8: 최종 교차검증 및 문서 일치화

**Files:**
- Modify: `docs/reports/2026-02-25-adr-260225-1012-dbfs-strict-smoke-revalidation.md`
- Modify: `docs/runbooks/ai-agent-infra-dev.md`
- Modify: `.specs/ai_agent_spec.md`
- Modify: `.specs/runtime_config.md`
- Create: `docs/adr/260225-1155-transition-serverless-checkpoint-path-to-uc-volumes.md`

**Step 1: 전체 변경 파일 확인**

Run:
```bash
git status --short
```
Expected: 위 파일만(또는 선택적 테스트 파일) 변경으로 표시.

**Step 2: 핵심 키워드 교차검증**

Run:
```bash
rg -n "${CHECKPOINT_VOLUMES}|CHECKPOINT_DB_PATH|serverless|strict smoke|SQLite" docs/reports/2026-02-25-adr-260225-1012-dbfs-strict-smoke-revalidation.md docs/runbooks/ai-agent-infra-dev.md .specs/ai_agent_spec.md .specs/runtime_config.md docs/adr/260225-1155-transition-serverless-checkpoint-path-to-uc-volumes.md
```
Expected: 정책/근거/운영절차 문구가 충돌 없이 일치.

## 완료 기준 (Exit Criteria)

- Red: serverless + `/dbfs/.../agent.db` 재현 실행이 실패로 기록되고 run id/오류 근거와 `/dbfs` 및/또는 `Errno 5` boundary signal 검증 결과가 리포트에 남아 있다.
- Green: serverless + `/Volumes/nsc_dbw_dev_7405610275478542/default/agent_state_checkpoints/agent.db` 실행이 성공으로 기록되고 run id/출력 근거가 리포트에 남아 있다.
- 스펙 2종(`.specs/ai_agent_spec.md`, `.specs/runtime_config.md`)이 serverless 기본 체크포인트 정책을 `/Volumes/...`로 명시한다.
- 런북(`docs/runbooks/ai-agent-infra-dev.md`)이 운영 절차를 `/Volumes` 기준으로 안내한다.
- ADR(`docs/adr/260225-1155-transition-serverless-checkpoint-path-to-uc-volumes.md`)이 정책 변경 사유/대안/영향/증거를 포함한다.
- (필요 시) Sudocode 후속 이슈가 생성되고 ADR과 링크된다.
- 서브에이전트 루프(Implementer -> Spec review -> Code-quality review -> Fix/Reverify)가 각 Task마다 수행되었다는 로그가 남아 있다.

## i-qva6 -> needs_review 핸드오프 체크리스트

- [ ] 변경 파일 목록이 i-qva6 범위를 벗어나지 않는다.
- [ ] Red/Green run id와 핵심 로그 1-3줄이 리포트에 있고, Red는 `/dbfs` 및/또는 `Errno 5` boundary signal 증거를 포함한다.
- [ ] `/dbfs`는 실패 근거/이행 배경으로만 남고, 운영 기본값은 `/Volumes/...`로 통일됐다.
- [ ] `docs/adr/260225-1155-transition-serverless-checkpoint-path-to-uc-volumes.md` 파일명/본문/연결 링크가 유효하다.
- [ ] 후속 Sudocode 이슈 필요성 판단 결과(생성 또는 불필요 사유)가 문서화됐다.
- [ ] blocker 0 상태에서만 `needs_review`로 전환한다.
