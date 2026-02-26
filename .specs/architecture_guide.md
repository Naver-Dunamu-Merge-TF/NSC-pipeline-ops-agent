# Architecture Guide — NSC Pipeline Ops-Agent

ops-agent 팀 온보딩 및 코드베이스 이해를 위한 아키텍처 가이드.

---

## 0. 프로젝트 개요 및 설계 배경

### 시스템 개요

NSC Pipeline Ops-Agent는 Controls-first Ledger Pipelines (Silver/A/B/C)의 장애를
자동으로 탐지·분석하고, 운영자의 승인 하에 조치를 실행하는 AI 운영 자동화 에이전트다.

이 에이전트의 목표는 두 가지다.

- **인지 부하 감소**: 장애 탐지·분석·제안을 자동화하여 운영자가 cold-start 진단 대신
  검토와 의사결정에 집중할 수 있게 한다.
- **팀 생산성 체계화**: 시니어 수준의 판단력을 에이전트로 표준화하고, 인시던트 경험을
  포스트모텀과 패턴 추적으로 팀 자산에 누적한다. 누가 당직이든 동일 품질의 대응이 가능한
  체계를 만드는 것이 핵심이다.

---

### 개인 역량 의존 체계에서 팀 체계로

#### 문제 1 — 인시던트 대응이 개인 역량에 의존하는 구조

현재 대응 프로세스는 개인 역량에 의존하는 구조다.

런북이 있지만 한계가 있다. 런북은 '어떤 절차를 따르라'는 정적 문서다.
절차를 따라도 해결되지 않는 판단이 있다.

- `bad_records`의 복합 위반(amount + schema)에서 주원인과 부원인을 분리하는 판단
- 'Bronze 소스가 원인이면 Silver backfill은 무의미하다'는 맥락 판단
- 업스트림 팀에 정확히 무엇을 요청해야 하는지 구조화하는 커뮤니케이션

이 세 가지 예시와 같이 업무에는 암묵지가 존재한다.
시니어와 주니어의 대응 품질 편차가 크고, 조직의 개인 의존도가 해소되지 않는다.

#### 문제 2 — 새벽 배치 장애의 진단 인지 부하

새벽 배치가 실패해도 아침 출근 전까지 진단이 시작되지 않는다.

운영자는 출근 즉시 콜드 스타트 상태에서 진단을 시작해야 한다.
어떤 파이프라인이 왜 실패했는지, 어떤 순서로 대응해야 하는지를
분산된 여러 테이블에서 직접 쿼리하고 종합해야 한다.

이 진단 시간은 모두 리드타임으로 전환된다.


#### 이 설계의 접근

- **시니어 판단력의 표준화**: 에이전트가 모든 당직자에게 동일한 수준의 분석을 제공한다.
  '정적 런북'이 아닌 '맥락을 읽는 판단력'을 팀 전체에 균등하게 공급한다.
- **진단 리드타임 제거**: 에이전트가 새벽에 분석을 완료해둔다. 운영자는 출근 시
  '진단'이 아닌 '검토' 부터 시작한다.
  승인 게이트는 최대 12시간 대기하므로 아침 출근 전 타임아웃 없이 ActionPlan이 유지된다.
- **팀 지식 체계화**: 포스트모텀 초안 자동 생성과 인시던트 지문으로
  경험을 팀 자산으로 전환한다.

---

> **설계 제약**: 탐지·게이팅·실행·검증은 결정론적 규칙으로 처리하고, LLM은
> 해석·판단·소통 레이어에만 사용한다(재현 가능성 보장).
> 실행은 인간 승인 게이트 이후에만 활성화되며, 비프로덕션 환경은 `dry_run=True`가
> 기본값이다(결제·원장 데이터 보호).

---

## 1. 전체 구조 한눈에 보기

### 레이어 구조

```
[업스트림 파이프라인]       [ops-agent]             [운영자]
 gold.pipeline_state   →   탐지 · 분석        →    승인 · 피드백
 gold.exception_ledger     제안 · 실행
 silver.dq_status          사후 문서화
 silver.bad_records
```

ops-agent는 업스트림 테이블을 읽기 전용으로 조회한다. 업스트림에 쓰지 않는다.

### 핵심 컴포넌트

| 컴포넌트 | 역할 |
|----------|------|
| graph/ | LangGraph 상태 기계 — 11개 노드로 인시던트 생명주기 관리 |
| runtime/ | 워치독 스케줄러 + 그래프 체크포인트 관리 |
| src/orchestrator/ | 파이프라인 감시 설정, ActionPlan 스키마, 공통 유틸 |
| llmops/ | 프롬프트 레지스트리, LLM 품질 평가 하네스 |
| prompts/ | 버전 관리된 LLM 프롬프트 템플릿 |
| config/ | YAML 기반 파이프라인 스케줄·폴링 규칙 |

---

## 2. 그래프 노드 상세

11개 노드가 `AgentState`(TypedDict, 26개 필드)를 공유하며 순차·조건부로 실행된다.

### 정상 흐름

```
detect → collect → analyze → triage → propose
  → [interrupt: 인간 승인] → execute → verify → postmortem → END
```

### 조건 분기

```
detect:
  이상 없음          → END (heartbeat 기록)
  지연만 감지         → report_only → END
  실패/예외 감지      → collect

collect:
  DQ 태그만 (bad_records 없음) → triage (analyze 스킵)
  bad_records 존재             → analyze

interrupt (승인 게이트):
  거부 / 타임아웃    → report_only → END
  수정 요청          → propose (재제안)
  승인               → execute

verify:
  성공               → postmortem → END
  실패               → rollback → 에스컬레이션
```

### 노드별 역할

| 노드 | 역할 | LLM 사용 |
|------|------|----------|
| `detect` | `pipeline_state` / `exception_ledger` / `dq_status` 폴링, 이상 판정, 지문 생성 | 없음 |
| `collect` | 예외 기록, DQ 태그, `bad_records_summary` 수집 | 없음 |
| `analyze` | bad_records 위반 유형 클러스터 분류, 조치 가이던스 생성 | ops01 |
| `triage` | `TriageReport` 생성 — 근본 원인 + 영향 범위 + ActionPlan 종합 | dq01 |
| `propose` | ActionPlan을 운영자에게 제시, 승인 요청 | 없음 |
| `[interrupt]` | 인간 승인 대기 (12시간 타임아웃, fail-closed) | 없음 |
| `execute` | Databricks API 호출 (backfill, skip 등) | 없음 |
| `verify` | 실행 후 SQL 조회로 성공 검증, 테이블 버전 비교 | 없음 |
| `postmortem` | 인시던트 요약 문서 자동 생성 | pm01 |
| `rollback` | 실행 실패 시 되돌리기 + 에스컬레이션 | 없음 |
| `report_only` | 조치 없이 경고 로그만 기록 | 없음 |

---

## 3. 핵심 메커니즘

### 인간 승인 게이트 (Level 3 자동화)

```
propose 노드가 ActionPlan을 제시
  ↓
interrupt 노드에서 최대 12시간 대기
  ├─ 승인      → execute 진행
  ├─ 수정 요청 → propose로 돌아가 재제안
  └─ 거부 / 타임아웃 → report_only, 실행 없이 종료
```

'실행 없는 자동화는 없다.' 승인 게이트를 우회하는 경로는 존재하지 않는다.

### LLM 사용 범위와 제한

```
규칙만 사용:  detect, collect, propose, execute, verify, rollback, report_only
LLM 사용:    analyze (ops01), triage (dq01), postmortem (pm01)
```

LLM 호출 일일 상한(`LLM_DAILY_CAP`, 기본 30회)이 초과되면
analyze/triage를 스킵하고 `report_only`로 폴백한다.

프롬프트 버전은 `prompts/registry.yaml`에서 관리하며, `llmops/prompt_registry.py`가
실행 시점에 로드한다. 모든 LLM 호출은 LangFuse로 트레이싱된다.

### 인시던트 지문 (Fingerprint)

동일 인시던트에 대한 분석·실행이 중복 실행되는 것을 방지한다.

```
인시던트 = (pipeline, detected_issues 조합)
  ↓
detect 노드가 fingerprint 생성 → AgentState.fingerprint에 저장
  ↓
fingerprint_duplicate=True이면 → detect에서 즉시 종료 (중복 처리 안 함)
```

### 스케줄 감시와 커트오프 게이트

`config/pipeline_monitoring.yaml`에 각 파이프라인의 예상 완료 시각(커트오프)을 정의한다.

```
runtime/watchdog.py (run_once 호출):
  현재 KST 시각 vs 각 파이프라인 커트오프 비교
    ├─ 커트오프 초과 → 해당 파이프라인 대상으로 detect 실행 의뢰
    └─ 커트오프 미달 → heartbeat 기록만 남기고 스킵
```

워치독은 그래프를 직접 실행하지 않는다.
폴링 대상 파이프라인 목록을 결정하고, `runtime/agent_runner.py`에 실행을 위임한다.

### 체크포인트 영속성

에이전트 상태는 SQLite(Databricks Volumes 경로)에 저장된다.

```
agent_runner.py → AgentState를 체크포인트 DB에 저장
  ↓
다음 run_once 호출 시 이전 상태에서 재개 가능
  (인간 승인 대기 중 프로세스가 재시작돼도 상태 유지)
```

### Dry-run 모드

```
환경변수 AGENT_ENV:
  'local' / 'dev' / 'staging' → dry_run=True (Databricks API 호출 없음, 모의 실행)
  'prod'                      → dry_run=False (실제 실행)
```

execute 노드는 dry_run 플래그를 확인하고 실제 호출 여부를 결정한다.
비프로덕션 환경에서 실수로 프로덕션을 건드릴 수 없다.

---

## 4. 코드 구조

```
NSC-pipeline-ops-agent/
├── graph/                      ← LangGraph 상태 기계 (핵심)
│   ├── graph.py                ← 그래프 토폴로지 + LangGraph shim 폴백
│   ├── state.py                ← AgentState TypedDict, ActionPlan, TriageReport
│   └── nodes/                  ← 10개 노드 구현 (+ interrupt는 그래프 레벨)
│       ├── detect.py, collect.py, analyze.py, triage.py
│       ├── propose.py, execute.py, verify.py, postmortem.py
│       └── rollback.py, report_only.py
├── runtime/                    ← 스케줄러와 그래프 실행기
│   ├── watchdog.py             ← 커트오프 기반 폴링 판단 (run_once)
│   └── agent_runner.py        ← 그래프 실행 + 체크포인트 관리
├── src/orchestrator/           ← 파이프라인 도메인 지식
│   ├── pipeline_monitoring_config.py
│   ├── action_plan.py
│   ├── databricks_jobs_config.py
│   ├── validation_targets_config.py
│   └── utils/                  ← config, secrets, incident, time
├── llmops/                     ← LLM 관측 가능성 + 평가
│   ├── prompt_registry.py
│   └── eval_runner.py
├── prompts/                    ← 버전 관리된 LLM 프롬프트 템플릿
│   ├── ops01/                  ← bad_records 분류 (analyze 노드)
│   ├── dq01/                   ← 근본 원인 추론 (triage 노드)
│   ├── pm01/                   ← 포스트모텀 생성 (postmortem 노드)
│   ├── judge/                  ← LLM-as-judge (평가)
│   └── registry.yaml           ← 프롬프트 버전 메타데이터
├── config/
│   └── pipeline_monitoring.yaml  ← 파이프라인 스케줄 + 커트오프
├── ops/entrypoint.py           ← 프로덕션 진입점 → watchdog.run_once()
└── .specs/                     ← 인간 작성 의도 명세 (SSOT)
    ├── ai_agent_spec.md
    └── runtime_config.md
```

**분리 원칙**:
- `graph/nodes/` — 각 노드는 `AgentState → AgentState` 순수 변환. 그래프 토폴로지와 분리
- `src/orchestrator/` — 파이프라인 도메인 지식 (스케줄, 잡 ID, 검증 대상 SQL)
- `llmops/` — LLM 품질 관리 코드. 노드 비즈니스 로직에 섞이지 않음
- `runtime/` — 에이전트 생명주기 관리. 그래프 내부와 분리

---

## 5. 외부 연동 레이어

### 업스트림 파이프라인 (읽기 전용)

| 테이블 | 읽는 노드 | 목적 |
|--------|----------|------|
| `gold.pipeline_state` | detect | 파이프라인 성공/실패 상태, 처리 윈도우 확인 |
| `gold.exception_ledger` | detect, collect | 임계값 초과 예외 이벤트 |
| `silver.dq_status` | detect, collect | DQ 태그 (SOURCE_STALE 등) |
| `silver.bad_records` | collect | 불량 레코드 위반 유형 → analyze 입력 |

### Databricks API (execute 노드에서만)

```
execute 노드 → Databricks Jobs API
  job_id:  databricks_jobs_config.py에서 파이프라인별 매핑
  params:  ActionPlan.parameters (backfill 날짜 범위, run_mode 등)
  dry_run=True이면 API 호출 없이 로깅만
```

### LangFuse (LLM 관측 가능성)

```
llmops/prompt_registry.py → 각 LLM 호출마다 trace 생성
  run_id, node_name, prompt_version, 입출력 전체 기록
    ↓
llmops/eval_runner.py → judge 프롬프트로 응답 품질 자동 평가
```

### 시크릿 관리

```
src/orchestrator/utils/secrets.py:
  Azure Key Vault → 환경변수 순서로 해소
  주요: DATABRICKS_HOST, DATABRICKS_TOKEN, LANGFUSE_HOST
```

---

## 6. 실제 실행 흐름 예시

**시나리오**: 2024-01-16 00:22 KST, Silver 파이프라인 실패

### 워치독 폴링 (run_once)

```
현재 시각 00:22 KST
  pipeline_silver 커트오프 = 00:15 KST → 초과 → detect 대상
  pipeline_b      커트오프 = 00:30 KST → 미달  → 스킵
```

### detect 노드

```
gold.pipeline_state 조회:
  pipeline_silver: status="failure", last_success_ts=어제
    → detected_issues에 실패 기록
    → fingerprint 생성 → fingerprint_duplicate=False → collect 진행
```

### collect 노드

```
gold.exception_ledger 조회 (당일):
  exceptions = [bad_records_rate 초과 2건]

silver.bad_records 샘플 조회:
  bad_records_summary = {
    "CONTRACT_VIOLATION/amount": 7건,
    "CONTRACT_VIOLATION/user_id_null": 3건
  }
```

### analyze 노드 (LLM: ops01)

```
입력: bad_records_summary
출력 → AgentState.dq_analysis:
  "amount 음수 위반 7건: 소스 시스템 부호 반전 의심.
   user_id null 3건: upstream 조인 키 누락 의심."
```

### triage 노드 (LLM: dq01)

```
입력: exceptions + dq_analysis + dq_tags
출력 → AgentState.triage_report (TriageReport):
  summary: "Silver ledger_entries 2024-01-15 데이터 오염"
  root_causes: [{"cause": "amount 부호 오류", "confidence": 0.82}]
  proposed_action: {"action": "BACKFILL", "pipeline": "pipeline_silver",
                    "date_kst": "2024-01-15"}
  expected_outcome: "Silver 재처리 후 B/C 정상 실행 가능"
```

### propose + interrupt (인간 승인 게이트)

```
운영자에게 triage_report + action_plan 제시
12시간 대기:
  ├─ 승인 → human_decision="approved" → execute 진행
  └─ 타임아웃 → human_decision="timeout" → report_only
```

### execute 노드

```
dry_run=False (프로덕션):
  Databricks Jobs API → pipeline_silver backfill 잡 트리거
  execution_result = {"job_run_id": "...", "status": "triggered"}
```

### verify 노드

```
gold.pipeline_state 재조회:
  pipeline_silver: status="success" → 검증 성공
  validation_results = {"pipeline_silver": "pass"}
  final_status = "resolved"
→ postmortem 진행
```

### postmortem 노드 (LLM: pm01)

```
AgentState 전체를 입력으로 포스트모텀 생성:
  postmortem_report = "## 인시던트 요약\n발생: 2024-01-16 00:08 KST\n
    원인: amount 부호 오류 (소스 시스템 배포)\n
    조치: pipeline_silver backfill 2024-01-15\n
    복구: 00:31 KST\n재발 방지: ..."
```

### 장애 시나리오

**verify 실패 시**: `rollback` 노드가 실행한 잡을 취소하고 에스컬레이션.
`final_status="rollback"` 기록 → 다음 폴링에서 지문으로 중복 처리 차단.

**LLM 일일 상한 초과 시**: analyze/triage 스킵 → `report_only`로 전환.
LLM 없이 탐지·수집 결과만 운영자에게 전달.

**LangGraph 미설치 환경**: `graph/graph.py`의 shim이 폴백 그래프를 제공해
`detect → report_only` 최소 흐름을 유지한다.

---

## 부록: AgentState 필드 목록

```python
# 인시던트 식별
incident_id            str            — 고유 인시던트 ID
pipeline               str            — 대상 파이프라인 이름
run_id                 Optional[str]  — 실행 추적 ID
detected_at            str            — 탐지 시각 (ISO 8601)
fingerprint            Optional[str]  — 중복 방지용 인시던트 지문
fingerprint_duplicate  Optional[bool] — True이면 즉시 종료

# 탐지 결과
pipeline_states   dict[str, Any]  — 폴링한 pipeline_state 행 전체
detected_issues   list[Any]       — 탐지된 이상 목록

# 수집 컨텍스트
exceptions           list[Any]        — exception_ledger 행 목록
dq_tags              list[Any]        — dq_status 태그 목록
bad_records_summary  dict[str, Any]   — 위반 유형별 집계

# LLM 분석 결과
dq_analysis        Optional[str]        — analyze 노드 출력 (ops01)
triage_report      Optional[dict]       — TriageReport 직렬화 (dq01)
triage_report_raw  Optional[str]        — TriageReport 원문 (디버깅용)

# 조치 계획 및 승인
action_plan            Optional[ActionPlan]   — propose 노드가 채움
approval_requested_ts  Optional[str]          — 승인 요청 시각
human_decision         Optional[str]          — "approved" | "rejected" | "timeout"
human_decision_by      Optional[str]          — 승인자 식별자
human_decision_ts      Optional[str]          — 승인 시각
modified_params        Optional[dict]         — 운영자가 수정한 파라미터

# 실행 및 검증
execution_result         Optional[dict]  — Databricks API 응답
validation_results       Optional[dict]  — verify 노드 SQL 결과
pre_execute_table_version Optional[dict] — 실행 전 테이블 버전 스냅샷 (롤백용)
final_status             Optional[str]   — "resolved" | "rollback" | "report_only"

# 사후 처리
postmortem_report        Optional[str]  — pm01 생성 문서
postmortem_generated_at  Optional[str]  — 생성 시각
```

## 부록: 환경 변수 SSOT

전체 목록은 `.specs/runtime_config.md` 참조. 주요 변수:

| 변수 | 기본값 | 역할 |
|------|--------|------|
| `AGENT_ENV` | `local` | 환경 구분 (local/dev/staging/prod) |
| `LLM_DAILY_CAP` | `30` | LLM 호출 일일 상한 |
| `TARGET_PIPELINES` | 전체 | 감시 대상 파이프라인 필터 |
| `CHECKPOINT_DB_PATH` | `/Volumes/...` | 체크포인트 SQLite 경로 |
| `LANGFUSE_HOST` | — | LLM 트레이싱 엔드포인트 |
