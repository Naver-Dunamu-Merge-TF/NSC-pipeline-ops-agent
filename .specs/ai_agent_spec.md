# AI Agent Spec

> **프로젝트**: NSC 결제/정산 데이터 플랫폼 — 파이프라인 장애 자동 대응 에이전트
> **최종 수정일**: 2026-02-19

---

## 1. 개요

### 1.1 목적

NSC 메달리온 아키텍처(Bronze → Silver → Gold)의 파이프라인 장애에 대해, **운영자가 장애를 더 빠르게 이해하고, 더 적은 인지 부하로 판단하며, 업스트림 팀과 더 효율적으로 소통**할 수 있게 지원하는 AI 에이전트를 구축한다. 에이전트는 장애를 감지·분석하고, 구체적인 복구 조치를 제안한 뒤, 운영자의 승인을 거쳐 실행한다. 동시에 에이전트 자체를 관측·평가·관리하는 LLMOps 체계를 함께 구축하여, 향후 플랫폼 전반의 AI 에이전트 확장을 위한 기반을 마련한다.

### 1.2 해결하는 문제

현재 파이프라인 장애 대응은 수동이다. Silver가 fail-fast로 멈추면 운영자가 로그를 뒤지고, bad_records를 수작업으로 분석하고, 원인을 파악한 뒤 Databricks에 직접 접속해서 재실행한다. 그 사이 Pipeline B(정산)와 C(익명화 팩트)는 하드 게이트(`assert_pipeline_ready`)에 막혀 대기한다.

이 과정에서 발생하는 병목:

- **진단 시간**: bad_records의 위반 패턴을 사람이 직접 분류·해석
- **영향 범위 파악**: 어떤 하위 파이프라인이 어떤 이유로 멈췄는지 종합하는 데 시간 소요
- **복구 실행**: Databricks 콘솔에 수동 접속 → 파라미터 입력 → 재실행
- **새벽 배치 장애의 사각지대**: 일배치(00:00~01:00)에 실패하면 아침 출근 전까지 분석이 시작되지 않는다. 에이전트가 없으면 진단 리드타임이 그대로 낭비된다
- **운영자 역량 편차**: 동일 장애에 대해 시니어와 주니어의 판단 품질이 다르다. "Bronze 소스 자체에 문제가 있으니 Silver backfill이 무의미하다"는 판단은 경험이 필요하다
- **업스트림 소통 비용**: 원인이 업스트림에 있을 때, 데이터 팀이 "뭐가 문제인지"를 정리하여 업스트림 팀에 전달하는 데 추가 시간이 든다

### 1.3 왜 LLM인가 — 규칙 기반 자동화와의 비교

감지·실행·검증은 규칙 기반으로 충분하다. LLM은 **"이해·판단·소통"** 레이어에서만 사용한다. 이 구분을 정직하게 인정하고 설계한다.

| 영역 | 규칙 기반으로 충분 | LLM이 가치를 추가하는 영역 |
|------|:---:|:---:|
| 장애 감지 (status 폴링) | ✅ | |
| 상황 수집 (SQL 집계) | ✅ | |
| 단일 위반 집계 (count, pct) | ✅ | |
| 조치 실행 (API 래퍼) | ✅ | |
| 검증 (SQL 비교) | ✅ | |
| **복합 위반 해석 + 우선순위 판단** | | ✅ |
| **맥락적 조치 판단** (Bronze 원인 → backfill 무의미) | | ✅ |
| **업스트림 수정 가이드** (자연어 생성) | | ✅ |
| **포스트모템 초안** (구조화 문서 자동 생성) | | ✅ |

**규칙 기반의 한계**: 위반 유형이 복합적으로 섞일 때 "어느 게 주원인이고 어느 게 부차적인지"를 결정하는 우선순위 판단, 그리고 pipeline_state + exception_ledger + dq_status를 종합하여 "지금 backfill을 해야 하는지, 업스트림 수정을 기다려야 하는지"를 맥락적으로 추론하는 판단은 사전 정의된 if-else 분기로 모든 조합을 커버하기 어렵다. 새로운 장애 패턴이 나올 때마다 규칙을 수동 추가해야 하며, LLM은 이 조합을 사전 정의 없이 추론할 수 있다.

**LLM 없이는 불가능한 것**: 업스트림 팀이 바로 조치할 수 있는 수준의 자연어 수정 가이드 생성, 장애 전체 맥락을 구조화된 포스트모템 문서로 자동 요약하는 것은 규칙 기반으로는 불가능하다.

### 1.4 기대 효과

#### ① 대응 리드타임 제거

일배치 장애는 새벽에 발생하고 아침에 대응한다. 에이전트가 실패 즉시 분석을 완료해놓으면, 운영자는 출근 시 "진단"이 아닌 **"검토 + 승인"**부터 시작할 수 있다.

| 단계 | 현재 (수동) | 에이전트 도입 후 |
|------|-----------|---------------|
| 새벽 배치 실패 | 아침까지 미분석 상태 대기 | 에이전트가 즉시 분석 → 아침 출근 시 결과 대기 중 |
| 아침 대응 시작 | 로그 확인 → bad_records 쿼리 → 패턴 해석 → 판단 (~20분) | 분석 결과 읽고 승인/거부 (~2분) |

→ "진단에 쓰는 시간"을 거의 제거. 단, 승인 대기 시간(최대 60분)이 여전히 병목이므로 전체 MTTR에 대한 공격적 수치는 제시하지 않는다.

#### ② 지식 비대칭 해소

에이전트는 모든 당직자에게 **시니어 수준의 분석**을 제공한다.

| 상황 | 시니어 당직 | 주니어 당직 | 에이전트 도입 후 |
|------|-----------|-----------|---------------|
| 복합 위반 (amount + schema) | 주원인 식별 가능 | 혼란, backfill 시도 → 재실패 | 동일한 분석 + 우선순위 제공 |
| Bronze 원인 판별 | "backfill 무의미" 판단 | 무의미한 backfill 시도 | `skip_and_report` 자동 제안 |

→ 에이전트가 "시니어의 판단력"을 표준화하여, 누가 당직이든 동일 품질의 대응이 가능.

#### ③ 업스트림 소통 비용 절감

장애 원인이 업스트림에 있을 때, 분석 결과를 정리하여 전달하는 과정도 자동화한다.

| 단계 | 현재 | 에이전트 도입 후 |
|------|------|---------------|
| 원인 분석 | 운영자가 직접 분석 (~20분) | analyze 노드 자동 생성 |
| 업스트림 전달 | 운영자가 메시지 작성 (~10분) | `upstream_guide` 복사 + 전달 |
| 포스트모템 | 수동 작성 (~30-60분/건) 또는 미작성 | LLM 초안 + 검수 (~10분) |

→ 장애당 총 **~30-60분** 운영 시간 절감. 특히 포스트모템은 기존에 작성되지 않던 경우가 많아, **"없던 표준이 생기는 것"** 자체가 가치.

### 1.5 목표 자동화 수준

**Level 3 (자동 — 승인 기반)**: 에이전트가 감지 + 분석 + 조치 제안 → 운영자가 승인 → 에이전트가 실행 + 결과 확인.

금융 시스템 특성상 완전 자동(Level 4)은 채택하지 않는다. 사람의 승인을 반드시 거치되, 승인 전까지의 모든 과정(감지·수집·분석·제안)과 승인 후의 실행·검증을 에이전트가 수행한다.

---

## 2. 시스템 설계

### 2.1 에이전트 흐름 (LangGraph 상태 그래프)

```
[detect] 자동 감지
  pipeline_state + dq_status + exception_ledger 폴링 → 이상 감지?
  │
  ├─ 이상 없음 → heartbeat 로그 → END
  ├─ 컷오프 지연 → [report_only] 경고 리포트만 → END
  │
  └─ 파이프라인 실패/새 예외/CRITICAL DQ이상 ↓

[collect] 상황 수집
  pipeline_state + exception_ledger + dq_status + bad_records
  │
  ↓ (조건 분기)
  │
  ├─ DQ 태그만 (파이프라인 정상) → [triage] (analyze 스킵, LLM 1회만)
  │
  └─ 파이프라인 실패 / 새 예외 ↓

[analyze] bad_records 분석 (★ LLM)
  위반 유형 클러스터링 + 설명 + 수정 가이드
  │
  ↓

[triage] 종합 트리아지 (★ LLM)
  장애 요약 + 영향 범위 + 실행 가능한 조치 제안
  │
  ↓

[propose] 조치 제안 + 승인 요청
  │
  ↓

[interrupt] ← 운영자 승인 대기 (LangGraph interrupt)
  │
  ├─ 거부 → [report_only] 리포트 저장 → END
  ├─ 수정 → action_plan 갱신 후 다시 propose
  ├─ 타임아웃(60분) → 에스컬레이션 상태 저장 → END
  │
  └─ 승인 ↓

[execute] 조치 실행
  Databricks Jobs API로 파이프라인 재실행
  │
  ↓

[verify] 실행 결과 확인
  pipeline_state 폴링 + 정산 도메인 검증
  │
  ├─ 성공 → [postmortem] 자동 포스트모템 초안 생성 → 완료 리포트 → END
  ├─ 검증 실패 → [rollback] → 에스컬레이션 → END
  └─ 잡 실패 → 실패 리포트 + 에스컬레이션 → END
```

**조건 엣지 명세** (graph.py 구현 기준):

| 소스 노드 | 조건 | 대상 노드 | 설명 |
|-----------|------|----------|------|
| detect | `detected_issues == []` | END | 정상 — heartbeat 로그만 |
| detect | 컷오프 지연만 (파이프라인 실패/예외 없음) | report_only → END | 경고 리포트 생성, LLM 미호출 |
| detect | 파이프라인 실패 / 새 예외 / CRITICAL DQ 이상 | collect | 전체 흐름 진입 |
| collect | DQ 태그만 존재 (pipeline 실패/새 예외 없음) | triage | analyze 스킵 — bad_records 분석 불필요 |
| collect | 파이프라인 실패 또는 새 예외 | analyze | bad_records 분석 필요 |
| triage | `action_plan.action == "skip_and_report"` | report_only → END | 실행 불필요 판단 시 리포트만 |
| triage | 실행 가능한 조치 존재 | propose | 승인 요청 |
| interrupt | approve | execute | 승인 → 실행 |
| interrupt | reject | report_only → END | 거부 → 리포트 저장 |
| interrupt | modify | propose | 파라미터 수정 후 재제안 |
| interrupt | timeout (60분 무응답) | END | `final_status = "escalated"` 저장 + 에스컬레이션 알림 |
| verify | 검증 통과 (`final_status = "resolved"`) | **postmortem** → END | **자동 포스트모템** — 장애 대응 전체 과정을 LLM으로 초안 생성 후 완료 |
| verify | blocking 검증 실패 (#1: 잡 상태 불일치) | END | `final_status = "escalated"` 기록 + 즉시 에스컬레이션 (롤백 없음) |
| verify | blocking 검증 실패 (#2/#3/#5) | rollback → END | 롤백 + 에스컬레이션 |
| verify | 잡 실패 | END | `final_status = "failed"` 기록 + 에스컬레이션 |

### 2.2 상태 스키마

```python
from typing import TypedDict, Optional

class ActionPlan(TypedDict):
    """propose/execute가 참조하는 단일 진실원천. TriageReport.proposed_action → 검증 후 이 객체로 확정."""
    action: str                        # 화이트리스트 내 조치명
    parameters: dict                   # 실행 파라미터
    expected_outcome: str              # 예상 결과
    caveats: list[str]                 # 주의사항

class AgentState(TypedDict):
    # ── 사건 식별 (중복 방지 + 감사 추적) ──
    incident_id: str                   # entrypoint/watchdog에서 graph.invoke 전에 생성
    pipeline: str                      # 대상 파이프라인명
    run_id: Optional[str]              # 원본 실행 ID
    detected_at: str                   # 감지 시각 (UTC ISO8601)
    fingerprint: Optional[str]         # SHA256(pipeline + run_id + canonical(detected_issues)) — 동일 장애 재처리 방지

    # ── 감지 ──
    pipeline_states: dict
    detected_issues: list

    # ── 수집 ──
    exceptions: list
    dq_tags: list
    bad_records_summary: dict

    # ── 분석 (LLM 출력) ──
    dq_analysis: Optional[str]         # analyze 스킵 경로에서는 None
    triage_report: Optional[dict]      # TriageReport 스키마 (Pydantic 검증 통과 후 dict로 저장)
    triage_report_raw: Optional[str]   # LLM 원본 응답 (디버깅/감사용)

    # ── 조치 (단일 진실원천: action_plan) ──
    action_plan: Optional[ActionPlan]  # propose/execute 모두 이 필드만 참조
    approval_requested_ts: Optional[str]  # propose에서 승인 요청 시각 기록 (UTC ISO8601)
    human_decision: Optional[str]      # "approve" | "reject" | "modify"
    human_decision_by: Optional[str]   # 승인자 ID (감사 추적용)
    human_decision_ts: Optional[str]   # 승인 시각 (UTC ISO8601)
    modified_params: Optional[dict]    # modify 시 변경된 파라미터 (diff 추적용)

    # ── 실행 ──
    execution_result: Optional[dict]
    validation_results: Optional[dict] # verify 단계 검증 결과 (건수/중복/합계 등)
    pre_execute_table_version: Optional[dict]  # 롤백용 Delta 테이블 버전
    final_status: Optional[str]        # "resolved" | "failed" | "escalated" | "reported"

    # ── 포스트모템 (verify 이후) ──
    postmortem_report: Optional[str]   # LLM 생성 포스트모템 초안 (마크다운)
    postmortem_generated_at: Optional[str]  # 생성 시각 (UTC ISO8601)
```

**스키마 설계 원칙**:

- **triage_report**: LLM이 생성한 JSON을 Pydantic(TriageReport)으로 검증한 뒤 `dict`로 저장한다. 원본 문자열은 `triage_report_raw`에 별도 보관하여 디버깅과 감사에 사용한다.
- **action_plan**: TriageReport 내부의 `proposed_action`을 검증 후 `ActionPlan`으로 확정하여 state에 저장한다. triage가 최초 작성하고, interrupt의 modify에서만 갱신 가능하다. propose/execute는 항상 `action_plan`만 참조한다. `modified_params`는 diff 감사용이다.
- **incident_id / fingerprint**: entrypoint/watchdog가 `graph.invoke` 전에 생성하여 initial_state에 포함한다. detect는 이를 읽어 추적하고, 중복 방지는 fingerprint를 SSOT로 사용한다.

### 2.2.1 노드별 State 읽기/쓰기 매핑

각 노드가 AgentState에서 읽는 필드(R)와 쓰는 필드(W)를 명시한다. 노드 구현 시 이 표 외의 필드를 읽거나 쓰지 않는다.

| 노드 | Reads (state에서) | Writes (state로) |
|------|-----------------|-----------------|
| **detect** | `incident_id`, `pipeline`, `run_id`, `detected_at`, `fingerprint` + 외부 테이블(`pipeline_state`, `dq_status`, `exception_ledger`) | `pipeline_states`, `detected_issues` |
| **collect** | `pipeline`, `run_id`, `pipeline_states`, `detected_issues` | `exceptions`, `dq_tags`, `bad_records_summary` |
| **report_only** | `detected_issues`, `pipeline_states` | `final_status = "reported"` |
| **analyze** | `bad_records_summary`, `pipeline` | `dq_analysis` |
| **triage** | `dq_analysis`(없으면 `None`), `exceptions`, `dq_tags`, `pipeline_states`, `pipeline`, `detected_at` | `triage_report`, `triage_report_raw`, `action_plan` |
| **propose** | `triage_report`, `action_plan`, `incident_id`, `modified_params` | `approval_requested_ts` |
| **[interrupt]** | `approval_requested_ts`, `action_plan` + 운영자 입력 | `human_decision`, `human_decision_by`, `human_decision_ts`, `modified_params`, `action_plan`(modify 시 갱신), `final_status`(reject/timeout 시) |
| **execute** | `action_plan`, `human_decision`, `pipeline` | `pre_execute_table_version`, `execution_result` |
| **verify** | `execution_result`, `action_plan`, `pre_execute_table_version`, `pipeline` | `validation_results`, `final_status` |
| **rollback** | `pre_execute_table_version`, `validation_results`, `pipeline` | `execution_result`(롤백 결과), `final_status = "escalated"` |
| **postmortem** | `incident_id`, `pipeline`, `detected_at`, `triage_report`, `action_plan`, `human_decision`, `human_decision_by`, `human_decision_ts`, `execution_result`, `validation_results`, `final_status` | `postmortem_report`, `postmortem_generated_at` |

**읽기/쓰기 원칙**:

- `action_plan`은 triage가 최초 작성하고, interrupt의 modify에서만 갱신한다. propose/execute는 항상 `action_plan`만 실행 기준으로 읽는다.
- `modified_params`는 interrupt에서 diff 감사용으로만 쓴다. 실행 입력 SSOT는 `action_plan`이다.
- `final_status`는 report_only, interrupt(reject/timeout), verify, rollback에서만 쓴다. postmortem은 `final_status`를 읽기만 한다.
- `triage_report_raw`는 triage만 쓰고, 이후 노드는 읽지 않는다 (디버깅/감사 전용).
- `postmortem_report`는 postmortem만 쓴다. 실패 시 경고만 발송하고 `final_status`는 변경하지 않는다.

### 2.2.2 에이전트 입력 테이블 스키마 (사용 컬럼만 발췌)

detect.py / collect.py가 실제로 읽는 컬럼만 발췌한다.

SSOT는 [.specs/data_contract.md](./data_contract.md)입니다.

#### `gold.pipeline_state` — detect.py, collect.py

| 컬럼 | 타입 | 에이전트 사용 목적 |
|------|------|-----------------|
| `pipeline_name` | string | PK — 파이프라인 필터 |
| `status` | string | `"success" \| "failure"` — 장애 판정 기준 |
| `last_success_ts` | timestamp(UTC) | 컷오프 지연 임계값 비교 |
| `last_processed_end` | timestamp(UTC) | `pipeline_b`/`pipeline_c` 하드 게이트 판정 기준 |
| `last_run_id` | string | fingerprint 생성/추적 기준 |

#### `silver.dq_status` — detect.py, collect.py

| 컬럼 | 타입 | 에이전트 사용 목적 |
|------|------|-----------------|
| `source_table` | string | 어떤 Bronze 테이블의 DQ인지 |
| `dq_tag` | string | `NULL \| SOURCE_STALE \| DUP_SUSPECTED \| EVENT_DROP_SUSPECTED \| CONTRACT_VIOLATION` |
| `severity` | string | `WARN \| CRITICAL` (detect 트리거는 CRITICAL 우선) |
| `run_id` | string | 최신 run_id 필터 기준 (detect/collect 공통) |
| `window_end_ts` | timestamp(UTC) | 최근 윈도우 필터 기준 |
| `date_kst` | date | 파티션 필터 |

#### `gold.exception_ledger` — detect.py, collect.py

| 컬럼 | 타입 | 에이전트 사용 목적 |
|------|------|-----------------|
| `severity` | string | CRITICAL 필터 |
| `domain` | string | `"dq"` 필터 (detect/collect 공통) |
| `exception_type` | string | 예외 유형 분류 |
| `source_table` | string | 발생 테이블 |
| `metric` / `metric_value` | string / decimal | 초과 메트릭 상세 |
| `run_id` | string | 신규 예외 판정 기준 (detect 트리거 키) |
| `generated_at` | timestamp(UTC) | 최근 예외 필터 |

#### `silver.bad_records` — collect.py → analyze.py

| 컬럼 | 타입 | 에이전트 사용 목적 |
|------|------|-----------------|
| `source_table` | string | 위반 테이블 집계 기준 |
| `reason` | string | 위반 사유 (`field`, `rule`, `detail` 키가 있는 구조 문자열/JSON 가정) — 포맷은 구현 전 확인 필요 |
| `record_json` | string(JSON) | 원본 레코드 값 |
| `run_id` | string | `pipeline_silver` run_id 기준 필터 |
| `detected_date_kst` | date | 파티션 필터 |

`silver.bad_records.reason` 포맷은 **현재 가정 + 확인 필요** 상태로 유지되며, `field` 추출이 불확실한 경우 `field="unknown"` 원칙을 따른다.

### 2.3 감지 트리거

에이전트는 파이프라인 스케줄에 맞춰 예상 완료 시각 이후에 폴링한다. 일배치 파이프라인은 배치 완료 시점에만 체크하고, 마이크로배치(`pipeline_a`)만 주기적으로 폴링한다.

파이프라인 식별자 SSOT는 `gold.pipeline_state.pipeline_name` 값(`pipeline_silver`, `pipeline_b`, `pipeline_c`, `pipeline_a`)이다. 본문에서 Silver/B/C/A는 설명용 별칭으로만 사용한다.

| 파이프라인 | 스케줄 | 예상 완료 | 감지 시점 | 컷오프 지연 임계값 |
|-----------|--------|----------|----------|-----------------|
| `pipeline_silver` | 00:00 KST (일배치) | ~00:10 | 00:10 이후 폴링 | **30분** (00:30 미완료 시 경고) |
| `pipeline_b` | 00:20 KST (일배치) | ~00:35 | 00:35 이후 폴링 | **30분** (00:50 미완료 시 경고) |
| `pipeline_c` | 00:35 KST (일배치) | ~00:45 | 00:45 이후 폴링 | **30분** (01:05 미완료 시 경고) |
| `pipeline_a` | 매 10분 (마이크로배치) | ~2분 | **5분 주기** 폴링 | **20분** (2회 연속 미실행 시 경고) |

| 조건 | 확인 대상 | 판정 |
|------|----------|------|
| 파이프라인 실패 | `pipeline_state.status = "failure"` | 그래프 실행 |
| 새 예외 발생 | `exception_ledger`에 새 CRITICAL 행 (`domain = "dq"`) | 그래프 실행 |
| DQ 이상 태그 | `dq_status.severity = "CRITICAL"` AND `dq_tag IN ('SOURCE_STALE', 'EVENT_DROP_SUSPECTED')` | 그래프 실행 |
| 컷오프 지연 | `pipeline_state.last_success_ts`가 위 임계값 초과 | 경고 리포트만 |
| 정상 | 위 조건 모두 미해당 | heartbeat 로그 |

중복 방지: `fingerprint`를 체크포인터 조회 키(SSOT)로 사용한다. 동일 fingerprint가 이미 처리된 경우 새 그래프 실행을 시작하지 않는다.

### 2.4 노드별 상세

#### analyze와 triage를 분리하는 이유

두 노드는 입력 소스와 관심사가 다르다. analyze는 `bad_records` + `contracts.py` 기반의 **데이터 품질 분석**을 담당하고, triage는 analyze 결과(없을 수 있음) + `pipeline_state` + `exception_ledger` + `dq_status`를 합쳐 **운영 판단과 조치 제안**을 담당한다. DQ 태그 전용 경로에서는 analyze를 스킵하고 triage가 규칙 기반 맥락만으로 `skip_and_report`를 제안할 수 있게 설계한다.

#### analyze — bad_records 원인 분석

Silver 파이프라인이 `enforce_bad_records_rate`로 fail-fast했을 때, 불량 레코드를 분석하여 "왜 불량인지"를 설명한다.

| 입력 | 용도 |
|------|------|
| `silver.bad_records` | 불량 레코드 본문 (테이블명, 위반 필드, 위반 사유, 원본 값) |
| `contracts.py` (23개 스키마 계약) | 어떤 규칙이 깨졌는지 대조 기준 |
| `gold.dim_rule_scd2` | 런타임 임계값/허용값 참조 |

**샘플링 전략**: bad_records가 대량일 경우 전수를 LLM에 넣지 않는다. collect 노드에서 사전 집계한 뒤 요약만 전달한다.

1. 위반 유형(테이블 × 필드 × 사유)별 **건수 집계**
2. 유형별 **상위 10건 샘플** 추출
3. 집계 + 샘플을 LLM 입력으로 전달

이 방식으로 토큰 사용량을 제한하면서도, LLM이 패턴을 파악하기에 충분한 정보를 제공한다.

LLM이 하는 일: (1) 위반 유형(필드×사유)별 패턴 해석, (2) 자연어 설명 생성, (3) 업스트림 수정 가이드 생성.

#### triage — 종합 트리아지 + 조치 제안

analyze 결과(없으면 `null`) + pipeline_state + exception_ledger + dq_status를 종합하여 장애 요약, 영향 범위, **실행 가능한 조치**(명령어 + 파라미터)를 생성한다.

**구조화된 출력**: triage 결과는 JSON schema로 강제하고, Pydantic 모델로 검증한다. LLM 원본 응답은 `triage_report_raw`에 저장하고, Pydantic 검증을 통과한 dict만 `triage_report`에 저장한다. `ActionPlan`은 아래 규칙으로 합성해 `state.action_plan`에 저장한다.

- `action` = `triage_report.proposed_action.action`
- `parameters` = `triage_report.proposed_action.parameters`
- `expected_outcome` = `triage_report.expected_outcome`
- `caveats` = `triage_report.caveats`

```python
from pydantic import BaseModel

class TriageReport(BaseModel):
    summary: str                  # 장애 요약
    failure_ts: str               # 장애 발생 시각 (UTC ISO8601, 표시 시 KST 변환)
    root_causes: list[dict]       # [{"table": ..., "field": ..., "reason": ..., "count": ..., "pct": ...}]
    impact: list[dict]            # [{"pipeline": ..., "status": ..., "description": ...}]
    proposed_action: dict         # {"action": ..., "parameters": {...}} → 검증 후 state.action_plan으로 확정
    expected_outcome: str         # 예상 결과
    caveats: list[str]            # 주의사항
```

triage 노드 처리 흐름: LLM 응답(str) → `triage_report_raw`에 저장 → JSON 파싱 → `TriageReport` Pydantic 검증 → 통과 시 `triage_report`(dict)에 저장 + 위 합성 규칙으로 `action_plan` 저장. 검증 실패 시 Permanent 에러로 에스컬레이션.

출력 예시:

```json
{
  "summary": "Silver가 2026-02-18 00:03 KST에 fail-fast. bad_records_rate 8.2% (임계값 5% 초과).",
  "failure_ts": "2026-02-17T15:03:00+00:00",
  "root_causes": [
    {"table": "transaction_ledger_raw", "field": "amount", "reason": "amount <= 0", "count": 847, "pct": 62.0},
    {"table": "user_wallets_raw", "field": "balance_total", "reason": "balance_total 불일치", "count": 312, "pct": 23.0},
    {"table": "payment_orders_raw", "field": "order_id", "reason": "order_id NULL", "count": 89, "pct": 6.0}
  ],
  "impact": [
    {"pipeline": "pipeline_b", "status": "waiting", "description": "UpstreamReadinessError로 대기 중 (정산 지연)"},
    {"pipeline": "pipeline_c", "status": "waiting", "description": "UpstreamReadinessError로 대기 중 (익명화 팩트 미생성)"},
    {"pipeline": "pipeline_a", "status": "unaffected", "description": "영향 없음 (Bronze 직접 읽음)"}
  ],
  "proposed_action": {
    "action": "backfill_silver",
    "parameters": {"pipeline": "pipeline_silver", "date_kst": "2026-02-17", "run_mode": "backfill"}
  },
  "expected_outcome": "pipeline_silver 성공 시 pipeline_b/pipeline_c 하드 게이트 자동 통과",
  "caveats": ["Bronze 소스의 amount 문제가 해결된 후 실행해야 함"]
}
```

#### propose + interrupt — 승인 흐름 (HITL)

LangGraph `interrupt()`로 에이전트를 일시 정지하고 운영자 승인을 대기한다. CLI 인터페이스로 승인(Approve) / 거부(Reject) / 수정(Modify)을 선택한다.

**승인 대기 타임아웃 정책**:

| 경과 시간 | 동작 |
|----------|------|
| 0분 | 조치 제안 + 이메일 알림 발송 |
| 30분 미응답 | 이메일 재알림 1회 발송 |
| 60분 미응답 (최종) | 에스컬레이션 리포트 저장 + 이메일 통보, 에이전트 종료 (자동 실행 안 함) |

타임아웃 판정 기준은 `approval_requested_ts`(propose write)와 현재 UTC 시각의 차이로 계산한다.  
`interrupt`는 `reject` 시 `final_status = "reported"`, `timeout` 시 `final_status = "escalated"`를 기록한 뒤 종료한다.

상태 영속성: SQLite 체크포인터가 각 노드 완료 시 상태를 저장. 프로세스가 종료되어도 마지막 체크포인트에서 재개 가능.

#### execute + verify — 도구 실행

| 도구 | 동작 | 에러 처리 |
|------|------|----------|
| `run_databricks_job` | Databricks Jobs API로 파이프라인 재실행 | 인증 실패, 잡 not found, 타임아웃 |
| `check_job_status` | 실행 중인 잡 상태 폴링 | 폴링 타임아웃 |
| `read_pipeline_state` | 실행 후 pipeline_state 확인 | 테이블 읽기 실패 |
| `run_domain_validation` | 정산 도메인 검증 SQL 실행 | 쿼리 실패, 타임아웃 |

**verify 검증 체크리스트**: 잡 성공만으로는 정산 데이터 정합성을 보장하지 않는다. verify 노드는 다음 검증을 순차 수행하고, 결과를 `state.validation_results`에 저장한다.

| # | 검증 항목 | SQL/로직 | 실패 임계값 | 실패 시 동작 |
|---|----------|---------|-----------|------------|
| 1 | 잡 상태 | `pipeline_state.status == "success"` | status ≠ success | 즉시 에스컬레이션 |
| 2 | 레코드 건수 | `SELECT COUNT(*) FROM {target_table} WHERE date_kst = '{date}'` | 전일 대비 절대 변동률 `>= 0.5` (`=50%` 포함 실패), 단 전일 건수=0이면 당일 건수>0을 실패(당일도 0이면 통과)로 고정 | 롤백 + 에스컬레이션 |
| 3 | 중복 키 | `SELECT {pk}, COUNT(*) FROM {table} GROUP BY {pk} HAVING COUNT(*) > 1` | 중복 1건 이상 | 롤백 + 에스컬레이션 |
| 4 | DQ 태그 재확인 | `SELECT * FROM silver.dq_status WHERE run_id = '{new_run_id}' AND dq_tag IN ('SOURCE_STALE', 'EVENT_DROP_SUSPECTED')` | 이상 태그 존재 | 경고 리포트 (롤백하지 않음) |
| 5 | bad_records 비율 | `bad_records_rate` 재계산 | 여전히 임계값 초과 | 롤백 + 에스컬레이션 |

DEV-003 기준으로 verify/rollback 대상 카탈로그는 `config/validation_targets.yaml`에서 아래와 같이 고정한다.

| 검증 | 대상 테이블 | PK | 임계값/정책 | rollback |
|---|---|---|---|---|
| #1 | `gold.pipeline_state` | `pipeline_name` | `status != "success"`면 실패 | `false` |
| #2 | `silver.wallet_snapshot`, `silver.ledger_entries` | `snapshot_ts,user_id`; `tx_id,wallet_id` | 전일 대비 절대 변동률 `>= 0.5`면 실패 (`=50%` 포함), 전일 건수=0이면 당일 건수>0 실패 | `true` |
| #3 | `silver.wallet_snapshot`, `silver.ledger_entries` | `snapshot_ts,user_id`; `tx_id,wallet_id` | 중복 건수 `>= 1`이면 실패 | `true` |
| #4 | `silver.dq_status` | `run_id,source_table` | `dq_tag IN ('SOURCE_STALE', 'EVENT_DROP_SUSPECTED')` 존재 시 경고(비차단) | `false` |
| #5 | `silver.dq_status` | `run_id,source_table` | `bad_records_rate > 0.05`면 실패 | `true` |

`#1/#2/#3/#5`는 **blocking 검증**이다.  
`#1` 실패(잡 상태 불일치)는 롤백 없이 즉시 에스컬레이션한다 (`final_status = "escalated"`).  
`#2/#3/#5` 실패는 rollback 후 에스컬레이션한다.  
`#4`는 **non-blocking 경고**이므로 `validation_results`에 경고를 기록하고 알림만 발송한다.

최종 상태 규칙:
- blocking 검증이 모두 통과하면 `final_status = "resolved"` (`#4` 경고 유무와 무관)
- 잡 자체 실패 시 `final_status = "failed"`
- `#1` 실패(롤백 없음) 또는 rollback 수행 경로(`#2/#3/#5`)는 `final_status = "escalated"`

#### postmortem — 자동 포스트모템 초안 생성

장애 대응이 `final_status = "resolved"`로 완료된 경우에만 실행. State에 축적된 전체 대응 과정을 LLM에 전달하여 포스트모템 초안(마크다운)을 생성한다.

| 입력 (State에서 읽음) | 용도 |
|---------------------|------|
| `incident_id`, `pipeline`, `detected_at` | 사건 식별 |
| `triage_report` | 장애 요약 + 원인 + 영향 범위 |
| `action_plan` | 수행한 조치 |
| `human_decision`, `human_decision_by`, `human_decision_ts` | 승인 정보 |
| `execution_result`, `validation_results` | 실행/검증 결과 |

LLM이 하는 일:
1. 타임라인 정리 (감지 → 분석 → 제안 → 승인 → 실행 → 검증)
2. 근본 원인 요약 (`triage_report.root_causes` 기반)
3. 조치 내역 + 결과
4. 영향 범위 (downstream 파이프라인 상태 포함)
5. 재발 방지 권고 (LLM 제안 — 사람이 검수)

실패 시: 포스트모템 생성 실패는 장애 대응 자체에 영향 없음. `emit_alert(severity="WARNING", event_type="POSTMORTEM_FAILED")` 로깅 후 END. `final_status`는 변경하지 않는다.

**가드레일 — 실행 가능 조치 화이트리스트**: LLM이 어떤 조치를 제안하든, 사전 정의된 화이트리스트에 없으면 execute 노드에서 실행을 거부한다.

| 허용 조치 | 동작 |
|----------|------|
| `backfill_silver` | Silver 파이프라인을 지정 날짜로 backfill 재실행 |
| `retry_pipeline` | 지정 파이프라인을 동일 파라미터로 재실행 |
| `skip_and_report` | 실행 없이 리포트만 생성 (수동 대응 권고) |

화이트리스트에 없는 조치가 제안되면: 실행 거부 → "허용되지 않은 조치입니다" 리포트 저장 → 이메일 통보.

`ActionPlan` 계약(ADR-0003 결정사항, execute 노드 필수 적용):
- 허용 action은 `backfill_silver`, `retry_pipeline`, `skip_and_report` **3개만 허용**한다.
- `backfill_silver.parameters`: `pipeline`, `date_kst`, `run_mode` **3개만 허용**.
- `retry_pipeline.parameters`: `pipeline`, `run_mode` **2개만 허용**.
- `skip_and_report.parameters`: `pipeline`, `reason` **2개만 허용**.

execute 노드 검증 규칙(엄격 검증):
- 필수 파라미터 누락 시 실행 거부.
- 계약에 없는 추가 파라미터 존재 시 실행 거부.
- 타입 불일치(예: 문자열 필드에 비문자열) 시 실행 거부.
- `backfill_silver.date_kst`는 문자열이면서 `YYYY-MM-DD` 정규식(`^\d{4}-\d{2}-\d{2}$`)에 **엄격 일치**해야 한다.

계약 확장 정책:
- `action_plan.parameters` 필드 확장은 스키마 버전 상향(v2+)으로만 허용한다.
- v2+ 확장 전에는 반드시 하위 호환 영향 리뷰를 완료한다.
- 스키마 버전 식별자(version discriminator)의 위치/필드/판별 방식은 TBD이며, 별도 스펙 이슈에서 명시되기 전에는 v2+ 확장을 롤아웃하지 않는다.

`pipeline`/`run_mode` enum 값 정책:
- 현재 버전(v1)에서는 `pipeline`, `run_mode`의 enum 값 집합을 이 문서에서 확정하지 않는다(TBD).
- enum 값 SSOT는 별도 스펙 이슈에서 명시하며, 그 전까지 execute는 키/필수성/타입/포맷만 검증한다.

안전 장치: 기본값은 **dry-run** (실제 API 미호출, 실행 예정 명령만 출력).

| 환경 | 실행 모드 | 설정 위치 |
|------|----------|----------|
| dev | dry-run (고정) | Azure Key Vault (`agent-execute-mode`) |
| staging | dry-run (고정) | Azure Key Vault (`agent-execute-mode`) |
| prod | live | Azure Key Vault (`agent-execute-mode`) |

실행 모드는 모든 환경에서 Key Vault 시크릿으로 관리한다. 변경 이력을 추적하고, 접근 권한을 제한한다.

### 2.5 운영 설계

#### 보안 / 인증

에이전트가 사용하는 모든 시크릿은 기존 인프라인 Azure Key Vault에서 관리한다.

| 시크릿 | Key Vault 키 | 용도 |
|--------|-------------|------|
| Databricks API 토큰 | `databricks-agent-token` | Jobs API 호출 |
| LangFuse 공개키 | `langfuse-public-key` | Trace 수집 |
| LangFuse 비밀키 | `langfuse-secret-key` | Trace 수집 |
| Azure OpenAI API 키 | `azure-openai-api-key` | LLM 호출 |
| Azure OpenAI 엔드포인트 | `azure-openai-endpoint` | 리전 엔드포인트 |
| Azure OpenAI 배포명 | `azure-openai-deployment` | 모델 배포 선택 (예: gpt-4o) |
| Log Analytics DCR ID | `log-analytics-dcr-id` | 알림 로그 전송 (Data Collection Rule) |
| 실행 모드 | `agent-execute-mode` | dry-run / live 전환 |

**전체 환경 설정 목록**

에이전트 실행에 필요한 모든 설정을 유형별로 정리한다.
Key Vault 시크릿은 런타임에 로드하고, 환경변수는 Databricks Job 파라미터 또는 클러스터 설정으로 주입한다.

| 설정 | 유형 | 키/변수명 | dev | staging | prod |
|------|------|-----------|-----|---------|------|
| Databricks API 토큰 | Key Vault | `databricks-agent-token` | 개인 PAT | 서비스 계정 토큰 | 서비스 계정 토큰 |
| Azure OpenAI API 키 | Key Vault | `azure-openai-api-key` | dev 배포 | staging 배포 | prod 배포 |
| Azure OpenAI 엔드포인트 | Key Vault | `azure-openai-endpoint` | dev 리전 | staging 리전 | prod 리전 |
| Azure OpenAI 배포명 | Key Vault | `azure-openai-deployment` | `gpt-4o-dev` | `gpt-4o-staging` | `gpt-4o` |
| LangFuse 공개키 | Key Vault | `langfuse-public-key` | dev 키 | staging 키 | prod 키 |
| LangFuse 비밀키 | Key Vault | `langfuse-secret-key` | dev 키 | staging 키 | prod 키 |
| Log Analytics DCR ID | Key Vault | `log-analytics-dcr-id` | dev DCR | staging DCR | prod DCR |
| 실행 모드 | Key Vault | `agent-execute-mode` | `dry-run` (고정) | `dry-run` (고정) | `live` |
| 체크포인터 경로 | 환경변수 | `CHECKPOINT_DB_PATH` | `checkpoints/agent.db` | `/dbfs/mnt/agent-state/checkpoints/agent.db` | `/dbfs/mnt/agent-state/checkpoints/agent.db` |
| LangFuse 호스트 | 환경변수 | `LANGFUSE_HOST` | `http://localhost:3000` | `https://langfuse.internal.nsc.com` | `https://langfuse.internal.nsc.com` |
| LLM 일일 호출 상한 | 환경변수 | `LLM_DAILY_CAP` | `30` (기본, 필요 시 override) | `30` (기본, 필요 시 override) | `30` (기본, 운영에서 조정) |
| 대상 파이프라인 목록 | 환경변수 | `TARGET_PIPELINES` | `pipeline_silver` | `pipeline_silver,pipeline_b,pipeline_c,pipeline_a` | `pipeline_silver,pipeline_b,pipeline_c,pipeline_a` |

#### 배포

에이전트 실행 경로 자체는 **Databricks Job**으로 SubnetAnalytics 안에서 동작한다.
다만 본 기획서 범위에 포함된 **LLMOps(Self-Hosted LangFuse)** 까지 적용하면, Issue #3 인프라 매뉴얼(2026-02-15 업데이트) 기준으로 네트워크/인프라 확장이 추가로 필요하다.

- 단일 watchdog Job(인스턴스 1개) 5분 주기 실행
- watchdog 내부에서 `pipeline_a`는 매 주기 체크, `pipeline_silver`/`pipeline_b`/`pipeline_c`는 예상 완료 시각 이후 윈도우에서만 판정
- 헬스체크: heartbeat 로그를 Log Analytics로 전송, 30분 이상 heartbeat 없으면 경고

#### 네트워크 확장 항목 (신설 — Issue #3 기준)

> **R&R (역할 분담) 기준**
> 애플리케이션 배포에 해당하는 컨테이너 이미지 Push(ACR) 및 워크로드 생성(AKS)은 **데이터/AI 팀**이 직접 수행하고, DB/Private Endpoint 등 기반 인프라 신설과 네트워크/보안 설정 확장은 **인프라 팀**이 전담하여 지원한다.

| 구분 | 추가/변경 항목 | 위치 | 담당 | 목적 |
|------|----------------|------|------|------|
| 신규 리소스 | LangFuse ACR 이미지 Push 및 AKS Deployment + 내부 Service(ClusterIP) 생성 | SubnetApp (AKS) | **데이터/AI 팀**| LangGraph trace 수집/조회 |
| 신규 리소스 | LangFuse 전용 PostgreSQL Flexible Server (B1ms) | SubnetData | **인프라 팀** | LangFuse trace 메타데이터 저장 |
| 신규 리소스 | Azure OpenAI Private Endpoint | SubnetData (또는 AI 전용 서브넷) | **인프라 팀** | LLM 호출을 Azure 내부망으로 고정 |
| 기존 리소스 확장 | Private DNS Zone 레코드 추가 (`privatelink.postgres.database.azure.com`, `privatelink.openai.azure.com`) | SubnetSecurity (Private DNS) | **인프라 팀** | LangFuse DB / Azure OpenAI 내부 이름 해석 |
| 기존 리소스 확장 | Log Analytics Alert Rule + Action Group 연계 범위 확대 (Agent + LangFuse) | Monitoring Layer | **인프라 팀** | 승인 요청/타임아웃/실패 알림 일원화 |

| 네트워크 제어 | Source | Destination | Port | 정책 |
|---------------|--------|-------------|------|------|
| NSG 추가 | SubnetAnalytics (Databricks Agent Job) | SubnetApp (LangFuse) | TCP 443 | Allow (내부 API 호출) |
| NSG 추가 | SubnetApp (LangFuse) | SubnetData (LangFuse PostgreSQL) | TCP 5432 | Allow (DB 연결) |
| NSG 추가 | SubnetAnalytics / SubnetApp | Azure OpenAI Private Endpoint | TCP 443 | Allow (LLM 추론 호출) |
| NSG 유지/확장 | SubnetApp | SubnetSecurity (Key Vault, ACR) | TCP 443 | Allow (시크릿 조회, 이미지 Pull) |
| NSG 유지/확장 | SubnetAnalytics | SubnetSecurity (Key Vault) | TCP 443 | Allow (Databricks Secret Scope) |
| UDR 유지 | SubnetApp / SubnetAnalytics / SubnetData | SubnetEgress (Firewall) | `0.0.0.0/0` | `route-to-firewall` 강제 |
| 기본 차단 | Internet | SubnetApp / SubnetData / SubnetSecurity | Any | Deny (Public 접근 차단) |

| Private Endpoint / DNS | 대상 | 값 |
|------------------------|------|----|
| PostgreSQL PE | LangFuse DB | `privatelink.postgres.database.azure.com` |
| Azure OpenAI PE | LLM 추론 엔드포인트 | `privatelink.openai.azure.com` |
| Key Vault PE | Agent/LangFuse 시크릿 | `privatelink.vaultcore.azure.net` |
| ACR PE | LangFuse 이미지 Pull | `privatelink.azurecr.io` |

#### 에러 핸들링

에러를 **Transient**(일시적)과 **Permanent**(영구적)로 분류하고, 각각 다른 정책을 적용한다.

| 분류 | 에러 유형 | 재시도 | 동작 |
|------|----------|--------|------|
| Transient | HTTP 429 (Rate Limit) | 최대 3회, exponential backoff (2s → 4s → 8s) | 재시도 소진 시 에스컬레이션 |
| Transient | 네트워크 타임아웃 (연결/읽기) | 최대 2회, 5초 대기 후 | 재시도 소진 시 에스컬레이션 |
| Transient | Databricks API 5xx | 최대 2회, 10초 대기 후 | 재시도 전 `check_job_status`로 실행 여부 먼저 확인 |
| Permanent | 인증 실패 (401/403) | 없음 | 즉시 에스컬레이션 |
| Permanent | 잡 not found (404) | 없음 | 즉시 에스컬레이션 |
| Permanent | Pydantic 검증 실패 | 없음 | triage_report_raw 저장 + 에스컬레이션 |
| Permanent | 비즈니스 로직 실패 (backfill 후 재실패) | 없음 | 즉시 에스컬레이션 |

**Databricks Jobs API 특수 처리**: 잡 실행 요청 후 타임아웃이 발생하면 "실행 여부 불명" 상태가 된다. 재시도 전 반드시 `check_job_status`로 기존 실행이 진행 중인지 확인하고, 진행 중이면 재시도하지 않고 폴링으로 전환한다.

**LLM 호출 정책**:

| 설정 | 값 | 근거 |
|------|-----|------|
| 요청 타임아웃 | 60초 | triage 응답이 길 수 있음 |
| max_tokens | analyze: 2,000 / triage: 3,000 | 비용 제어 + 응답 길이 제한 |
| 일일 호출 상한 | `LLM_DAILY_CAP` (기본 30회/day, 환경변수 override) | 비용 통제 + 운영 환경별 조정 |
| 429 재시도 | 최대 3회 (backoff) | Azure OpenAI rate limit 대응 |
| 연속 실패 시 | deterministic-only 모드 전환 | LLM 불안정 시에도 감지/경고는 유지 |

근거: 금융 시스템에서 비즈니스 조치(backfill 등)의 자동 재시도는 상태 불일치를 유발할 수 있으므로 Permanent 에러는 절대 재시도하지 않는다. 다만 인프라 계층의 일시적 오류(429, 타임아웃)까지 재시도하지 않으면 MTTR이 불필요하게 늘어나므로, Transient에 한해 제한적 재시도를 허용한다.

#### 시간대 표준 (Time Policy)

에이전트 내부 처리와 저장은 **UTC ISO8601** (`+00:00`)로 통일한다. 사용자 표시(알림, 리포트, CLI 출력)만 **KST** (`+09:00`)로 변환한다.

| 대상 | 시간대 | 형식 | 예시 |
|------|--------|------|------|
| AgentState 내 모든 시각 필드 | UTC | ISO8601 | `2026-02-18T15:03:00+00:00` |
| LangFuse trace 시각 | UTC | ISO8601 (LangFuse 기본) | — |
| Log Analytics 로그 시각 | UTC | ISO8601 | — |
| 승인 요청 이메일/CLI 표시 | KST | `YYYY-MM-DD HH:MM KST` | `2026-02-19 00:03 KST` |
| 감지 트리거 스케줄 | KST | cron 표현식 | `10 0 * * * (KST)` |
| pipeline_state 입력 | **원본 그대로 읽고, 비교 시 UTC 변환** | — | — |

유틸 함수 `utils/time.py`에 `to_utc()`, `to_kst()`, `parse_pipeline_ts()` 구현. 모든 노드에서 시각 비교 시 반드시 UTC로 정규화한 후 계산한다.

#### 동시성

**순차 처리, 에이전트 인스턴스 1개**. 감지된 장애를 발생 순서대로 하나씩 처리한다.

근거: `pipeline_b`/`pipeline_c`는 `pipeline_silver`에 하드 게이트가 걸려 있으므로, `pipeline_silver` 실패 시 두 파이프라인은 "대기 중"이지 별도 "실패"가 아니다. `pipeline_silver`를 복구하면 자동 통과한다. 따라서 동시 다발 장애가 발생할 가능성이 낮고, 순차 처리로 충분하다.

#### 상태 영속성 — 체크포인터 설계

**SQLite 체크포인터 경로**

Databricks Job 실행 환경에서 `checkpoints/agent.db`를 로컬 경로로 두면 클러스터 재시작 시 유실된다.
DBFS 영속 경로를 사용하여 Job 재시작 후에도 마지막 체크포인트에서 재개 가능하도록 한다.

| 환경 | 경로 | 비고 |
|------|------|------|
| Databricks (prod/staging) | `/dbfs/mnt/agent-state/checkpoints/agent.db` | DBFS 마운트, 클러스터 재시작 후에도 유지 |
| 로컬 개발 | `checkpoints/agent.db` | 프로젝트 루트 상대경로 |

경로는 환경변수 `CHECKPOINT_DB_PATH`로 주입한다:

```python
# entrypoint.py
import os
from langgraph.checkpoint.sqlite import SqliteSaver

CHECKPOINT_DB_PATH = os.environ.get(
    "CHECKPOINT_DB_PATH",
    "checkpoints/agent.db"           # 로컬 기본값
    # Databricks: "/dbfs/mnt/agent-state/checkpoints/agent.db"
)
checkpointer = SqliteSaver.from_conn_string(CHECKPOINT_DB_PATH)
graph = build_graph(checkpointer=checkpointer)
```

**thread_id 전략**

LangGraph 체크포인터는 `thread_id`를 키로 각 실행의 상태를 구분한다.
에이전트는 `incident_id`를 thread_id로 사용한다.

| 상황 | thread_id | 동작 |
|------|-----------|------|
| 신규 장애 감지 | `incident_id` (entrypoint/watchdog 생성) | 새 thread — initial_state 포함으로 시작 |
| modify → re-propose | 동일 `incident_id` | 동일 thread 재개 — `action_plan` 갱신 후 propose부터 재실행 |
| fingerprint 중복 감지 | 체크포인터 조회 후 skip | 동일 fingerprint가 이미 처리되었으면 새 thread를 시작하지 않음 |

```python
# entrypoint.py — graph.invoke 전에 사건 식별자 생성
detected_issues = precheck_issues(pipeline, run_id)
initial_state = {
    "incident_id": make_incident_id(pipeline, run_id, detected_at),
    "pipeline": pipeline,
    "run_id": run_id,
    "detected_at": detected_at,
    "fingerprint": make_fingerprint(pipeline, run_id, detected_issues),
    "detected_issues": detected_issues,
}

# graph.py — thread_id 설정
config = {
    "configurable": {
        "thread_id": initial_state["incident_id"]
    }
}

# 신규 실행
graph.invoke(initial_state, config=config)

# modify 후 재개 (propose로 복귀)
graph.invoke(
    {"action_plan": updated_action_plan, "modified_params": updated_params},
    config=config
)
```

중복 방지: entrypoint/watchdog는 `graph.invoke` 전에 `fingerprint`로 체크포인터를 조회한다.
동일 fingerprint의 thread_id가 이미 존재하면 새 그래프 실행을 시작하지 않고 heartbeat만 기록한다.

#### 알림 체계

**Azure Monitor Alert + Action Group** 기반. 에이전트가 직접 이메일을 보내지 않고, Log Analytics에 구조화된 로그를 쏘면 Azure Monitor가 알림을 처리한다. 추가 인프라(Azure Communication Services, SMTP 서버) 없이 기존 모니터링 인프라만으로 동작한다.

```
에이전트 → Log Analytics (구조화 로그)
              ↓
         Azure Monitor Alert Rule (로그 패턴 매칭)
              ↓
         Action Group (이메일 발송)
```

`tools/alerting.py`는 Log Analytics에 구조화된 로그를 전송하는 역할만 한다:

```python
# alerting.py — 알림 이벤트를 Log Analytics 커스텀 로그로 전송
def emit_alert(severity: str, event_type: str, summary: str, detail: dict):
    """
    severity: "INFO" | "WARNING" | "ESCALATION"
    event_type: "TRIAGE_READY" | "APPROVAL_TIMEOUT" | "EXECUTION_SUCCESS" | "EXECUTION_FAILED" | "VALIDATION_FAILED" | "LLM_CAP_REACHED" | "HEARTBEAT_MISSING" | "POSTMORTEM_READY" | "POSTMORTEM_FAILED"
    """
    # Azure Monitor Data Collection API로 전송
    ...
```

| 이벤트 | severity | event_type | Alert Rule 동작 |
|--------|----------|------------|----------------|
| 장애 감지 + 조치 제안 | WARNING | `TRIAGE_READY` | 운영팀 이메일 (승인 요청) |
| 승인 대기 30분 초과 | WARNING | `APPROVAL_TIMEOUT` | 운영팀 이메일 (재알림) |
| 승인 대기 60분 초과 (최종) | ESCALATION | `APPROVAL_TIMEOUT` | 운영팀 이메일 (에스컬레이션) |
| 조치 실행 성공 | INFO | `EXECUTION_SUCCESS` | 운영팀 이메일 (완료) |
| 조치 실행 실패 | ESCALATION | `EXECUTION_FAILED` | 운영팀 이메일 (에스컬레이션) |
| verify blocking 검증 실패 + 롤백 | ESCALATION | `VALIDATION_FAILED` | 운영팀 이메일 (에스컬레이션) |
| LLM 호출 상한 도달 | WARNING | `LLM_CAP_REACHED` | 운영팀 이메일 (디그레이드 모드 진입) |
| heartbeat 30분 이상 없음 | ESCALATION | `HEARTBEAT_MISSING` | 운영팀 이메일 (헬스체크 경고) |
| **포스트모템 생성 완료** | INFO | `POSTMORTEM_READY` | 운영팀 이메일 (리뷰 요청) |
| 포스트모템 생성 실패 | WARNING | `POSTMORTEM_FAILED` | 운영팀 이메일 (수동 작성 권고) |

#### 감사 로그 (Audit Trail)

금융 시스템 요건으로, "누가 언제 무엇을 승인했고, 에이전트가 무슨 조치를 취했는지"를 추적한다.

- **LangFuse trace**: 모든 노드의 입출력·시간·토큰을 자동 기록. `prompt_version`, `run_id` 포함. 데이터는 VNet 내부 PostgreSQL에 저장.
- **AgentState 기록**: `human_decision_by` (승인자 ID) + `human_decision_ts` (승인 시각)를 상태에 저장. 체크포인터가 SQLite에 영속화.
- **Log Analytics**: Databricks Job 로그 + 에이전트 heartbeat가 자동 전송.

#### 비용 관리

LLM 호출 비용 제어를 위한 상한을 설정한다.

- **일일 LLM 호출 상한은 `LLM_DAILY_CAP`로 제어하며 기본값은 30회/day**. 정상 시 0회, 장애 시 analyze + triage + postmortem = 3회. 운영 환경에서는 장애 빈도/비용 예산에 맞춰 값을 조정한다. 상한 도달 시 추가 호출을 차단하고 이메일로 통보.
- LangFuse 대시보드에서 일별 토큰 사용량과 비용을 추적.

근거: 감지 루프 버그나 반복 장애로 LLM 호출이 무한 반복되는 것을 방지한다.

**디그레이드 모드 (캡 도달 시)**: 설정된 일일 LLM 호출 상한(`LLM_DAILY_CAP`)에 도달하면 에이전트는 LLM 없이 동작하는 deterministic-only 모드로 전환한다.

| 노드 | 정상 모드 | 디그레이드 모드 |
|------|----------|--------------|
| detect | 동일 | 동일 (LLM 미사용) |
| collect | 동일 | 동일 (LLM 미사용) |
| analyze | LLM으로 패턴 해석 | **스킵** — 집계 테이블만 생성 |
| triage | LLM으로 종합 판단 | **규칙 기반 리포트** — 감지 조건/집계 데이터만으로 템플릿 리포트 생성, `proposed_action`은 `skip_and_report` 고정 |
| report_only | 컷오프 지연/skip 경로 리포트 | **경고 리포트 발송** — "LLM 캡 도달, 수동 판단 필요" 명시 |
| propose | 조치 제안 + 승인 요청 | **도달하지 않음** (`triage -> report_only -> END`) |
| execute/verify | 동일 | **도달하지 않음** |
| postmortem | LLM으로 초안 생성 | **스킵** — 포스트모템 없이 종료 |

디그레이드 모드 진입/해제는 `emit_alert(severity="WARNING", event_type="LLM_CAP_REACHED")`로 로깅하며 이메일 통보한다. 자정(KST) 기준으로 카운터가 리셋되어 정상 모드로 자동 복귀한다.

#### 롤백 전략

에이전트가 backfill을 실행하기 전에 대상 Delta 테이블의 현재 버전을 기록하고, 실행 후 verify에서 데이터 정합성 문제가 발견되면 롤백한다.

DEV-003 기준 rollback 대상 Delta 테이블은 아래 2개로 고정한다.

- `silver.wallet_snapshot` (PK: `snapshot_ts`, `user_id`)
- `silver.ledger_entries` (PK: `tx_id`, `wallet_id`)

```
[execute 전]
  DESCRIBE HISTORY silver.wallet_snapshot → version 42 기록
  DESCRIBE HISTORY silver.ledger_entries  → version 38 기록
  → pre_execute_table_version에 저장

[verify 실패 시]
  RESTORE TABLE silver.wallet_snapshot TO VERSION AS OF 42
  RESTORE TABLE silver.ledger_entries  TO VERSION AS OF 38
  → 롤백 완료 리포트 + 이메일 통보
```

Delta Lake의 타임 트래블 기능을 사용하므로 추가 인프라가 필요 없다.

---

## 3. LLMOps 설계

### 3.1 구성

```
┌──────────────────────────────────────────────────────────────┐
│                        LLMOps 플랫폼                          │
│                                                              │
│  ┌──────────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │    LangFuse      │  │   Prompt     │  │  Eval Runner  │  │
│  │  (Self-Hosted)   │  │  Registry    │  │               │  │
│  │ Trace 자동 수집   │  │              │  │ pytest 기반   │  │
│  │ 실행 시각화       │  │ 파일 기반     │  │ + LLM Judge   │  │
│  │ 비용 추적        │  │ 버전 관리     │  │               │  │
│  │ 에러 모니터링     │  │ (YAML+Git)   │  │               │  │
│  └──────────────────┘  └──────────────┘  └───────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 LangFuse — 관측성 (Self-Hosted)

LangGraph 에이전트의 모든 실행을 자동으로 기록하고 시각화한다. 오픈소스(MIT 라이선스)이며 Azure 인프라 내에 자체 배포한다. 외부 SaaS 의존이 없으므로 에이전트 실행 데이터(장애 정보, bad_records 내용, 트리아지 리포트)가 외부로 유출되지 않는다.

**배포 구성**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Azure VNet (기존)                                 │
│                                                                         │
│  ┌─ SubnetSecurity ──┐   ┌─ SubnetApp (AKS) ────────────────────────┐  │
│  │                    │   │                                          │  │
│  │  ┌──────────────┐  │   │  ┌──────────────┐   ┌──────────────┐    │  │
│  │  │     ACR      │──┼───┼─→│  CryptoSvc   │   │  AccountSvc  │    │  │
│  │  │    (기존)     │  │   │  │    (기존)     │   │    (기존)     │    │  │
│  │  │              │  │   │  └──────────────┘   └──────────────┘    │  │
│  │  │  LangFuse    │──┼───┼─→┌──────────────┐                      │  │
│  │  │  이미지 Push  │  │   │  │  LangFuse    │                      │  │
│  │  └──────────────┘  │   │  │  Deployment  │                      │  │
│  └────────────────────┘   │  │  + ClusterIP │                      │  │
│                           │  │  (VNet 내부)  │                      │  │
│                           │  └──────┬───────┘                      │  │
│                           └─────────┼──────────────────────────────┘  │
│                                     │                                 │
│                                     │ Private EP                      │
│                                     ▼                                 │
│  ┌─ SubnetData ──────────────────────────────────────────────────┐    │
│  │                                                                │    │
│  │  ┌──────────────┐   ┌──────────────────────────────────────┐  │    │
│  │  │  PostgreSQL  │   │  PostgreSQL Flexible Server (신규)    │  │    │
│  │  │  (기존/서빙)  │   │  Burstable B1ms — LangFuse 전용 DB   │  │    │
│  │  └──────────────┘   └──────────────────────────────────────┘  │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                     ▲                                 │
│                                     │ LangFuse SDK (trace 전송)       │
│                                     │                                 │
│  ┌─ SubnetAnalytics ────────────────┼────────────────────────────┐    │
│  │                                  │                             │    │
│  │  ┌──────────────────────────┐    │                             │    │
│  │  │  Databricks              │    │                             │    │
│  │  │  ┌────────────────────┐  │    │                             │    │
│  │  │  │  에이전트 Job       │──┼────┘                             │    │
│  │  │  │  (detect → verify) │  │                                  │    │
│  │  │  └────────────────────┘  │                                  │    │
│  │  └──────────────────────────┘                                  │    │
│  └────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘

범례:  ─→ 이미지 Pull   ──▶ 데이터 흐름   (기존) 변경 없음   (신규) 새로 추가
```

1. **[데이터/AI 팀]** LangFuse Docker 이미지를 기존 **ACR**에 Push
2. **[데이터/AI 팀]** 기존 **AKS**에 LangFuse Deployment + ClusterIP Service 생성 (VNet 내부 전용, 외부 노출 없음)
3. **[인프라 팀]** LangFuse 전용 **PostgreSQL Flexible Server**를 SubnetData에 추가 생성 (Burstable B1ms, 최소 스펙)
4. **[인프라 팀]** 기존 서빙용 PostgreSQL과는 완전 분리하여 부하 간섭 방지

| 기능 | 상세 |
|------|------|
| Trace 수집 | LangFuse SDK 연동으로 모든 노드 입출력·시간·토큰을 자동 기록 |
| 시각화 | 그래프 노드별 상태 전이, 각 LLM 호출의 입출력을 내장 UI로 확인 |
| 비용 추적 | 모델별 토큰 사용량 자동 집계 + 비용 계산 |
| 에러 모니터링 | 실패 trace 필터 + 대시보드 |

연동 (LangGraph 콜백 핸들러):

```python
from langfuse.callback import CallbackHandler

langfuse_handler = CallbackHandler(
    public_key="...",          # Key Vault에서 로드
    secret_key="...",          # Key Vault에서 로드
    host="https://langfuse.internal.nsc.com"  # VNet 내부 엔드포인트
)

# LangGraph 실행 시 콜백으로 전달
graph.invoke(state, config={"callbacks": [langfuse_handler]})
```

### 3.3 Prompt Registry — 프롬프트 버전 관리

파일 기반(YAML + Git)으로 프롬프트를 버전 관리한다.

```
prompts/
├── registry.yaml
├── dq01/
│   ├── v1.0.txt
│   └── v1.0_meta.yaml
├── ops01/
│   ├── v1.0.txt
│   └── v1.0_meta.yaml
└── pm01/
    ├── v1.0.txt
    └── v1.0_meta.yaml
```

```yaml
# registry.yaml
prompts:
  dq01_bad_records:
    active_version: "v1.0"
    model: "gpt-4o"
    temperature: 0.2
    description: "bad_records 위반 분석 + 수정 가이드 생성"
  ops01_triage:
    active_version: "v1.0"
    model: "gpt-4o"
    temperature: 0.1
    description: "파이프라인 장애 트리아지 + 실행 가능 조치 제안"
  pm01_postmortem:
    active_version: "v1.0"
    model: "gpt-4o"
    temperature: 0.3
    description: "장애 대응 완료 후 포스트모템 초안 생성"
```

LangFuse trace에 prompt_version을 메타데이터로 기록하여 "어떤 프롬프트 버전이 어떤 결과를 냈는지" 추적 가능.

#### 프롬프트 초안 (v1.0)

> 구현 시 이 초안을 기준으로 `prompts/dq01/v1.0.txt`, `prompts/ops01/v1.0.txt`에 작성한다.
> - `dq01` 출력은 JSON 문자열로 `state.dq_analysis`에 저장 (별도 Pydantic 모델 없음, triage가 `json.loads`로 파싱)
> - `ops01` 출력은 §2.4의 `TriageReport` Pydantic 모델로 검증

**`dq01_bad_records` — analyze 노드**

```
[System]
너는 데이터 파이프라인 품질 분석 전문가다.
입력으로 주어지는 bad_records 집계 데이터와 계약 위반 샘플을 분석하여
위반 원인과 업스트림 수정 가이드를 JSON 형식으로 반환한다.

규칙:
- 원본 레코드 값을 그대로 반복하지 않는다. 패턴과 규칙 위반만 설명한다.
- 파이프라인 재실행·삭제 같은 실행 조치는 제안하지 않는다.
  수정 가이드는 "업스트림 소스" 범위로 한정한다.
- JSON 외 다른 텍스트를 출력하지 않는다.

출력 형식:
{
  "violations": [
    {
      "table": "<테이블명>",
      "field": "<필드명>",
      "reason": "<위반 사유>",
      "count": <건수>,
      "pct": <전체 대비 비율(%)>,
      "upstream_guide": "<업스트림 수정 가이드>"
    }
  ],
  "summary": "<위반 전체 요약 1~2문장>",
  "recommended_action": "upstream_fix_required | data_quality_warning"
}

[User]
파이프라인: {pipeline}
실행 날짜(KST): {date_kst}
총 불량 레코드: {total_bad_records}건 ({bad_records_rate}%)

위반 집계:
{violations_json}

샘플 레코드 (유형별 상위 10건):
{samples_json}
```

**`ops01_triage` — triage 노드**

```
[System]
너는 결제/정산 데이터 플랫폼의 파이프라인 장애 대응 전문가다.
입력 데이터를 종합하여 장애 요약, 영향 범위, 실행 가능한 복구 조치를 JSON으로 반환한다.

규칙:
- proposed_action.action은 반드시 ["backfill_silver", "retry_pipeline", "skip_and_report"] 중 하나여야 한다.
- Bronze 소스 자체에 문제가 있으면 반드시 "skip_and_report"를 제안한다.
  업스트림이 수정되지 않은 상태의 재실행은 무의미하다.
- 이미 success 상태인 파이프라인에 대한 조치를 제안하지 않는다.
- `dq_analysis`가 null이면 DQ 태그/예외/파이프라인 상태만으로 판단하고, 보수적으로 `skip_and_report`를 우선 제안한다.
- JSON 외 다른 텍스트를 출력하지 않는다.

출력 형식: §2.4의 TriageReport JSON 스키마를 따른다.

[User]
현재 시각(KST): {current_ts_kst}

파이프라인 상태:
{pipeline_states_json}

DQ 태그 이상:
{dq_tags_json}

새 CRITICAL 예외:
{exceptions_json}

bad_records 분석 결과(analyze 스킵 시 null):
{dq_analysis_json_or_null}
```

**`pm01_postmortem` — postmortem 노드**

```
[System]
너는 결제/정산 데이터 플랫폼의 장애 대응 포스트모템 작성 전문가다.
입력으로 주어지는 장애 대응 기록을 분석하여 구조화된 포스트모템 초안을 생성한다.

규칙:
- 타임라인은 KST로 표시한다.
- 원본 데이터 값(금액, 계정 등)을 그대로 포함하지 않는다.
- 재발 방지 권고는 구체적이되, 실행 가능한 수준으로 작성한다.
- 마크다운 형식으로 출력한다.

출력 구조:
## 장애 요약
## 타임라인
## 근본 원인
## 조치 내역 및 결과
## 영향 범위
## 재발 방지 권고

[User]
사건 ID: {incident_id}
파이프라인: {pipeline}
감지 시각: {detected_at_kst}

장애 분석(triage):
{triage_report_json}

수행 조치:
{action_plan_json}

승인: {human_decision} (승인자: {human_decision_by}, 시각: {human_decision_ts_kst})

실행 결과:
{execution_result_json}

검증 결과:
{validation_results_json}

최종 상태: {final_status}
```

### 3.4 Eval Runner — 품질 평가

pytest 기반으로 프롬프트 변경 후 품질 회귀가 없는지 자동 테스트한다.

#### 평가 방법론

LLM 출력을 검증하는 방식은 두 가지로 나뉜다.

**Deterministic (구조 검증)**: Pydantic 파싱 성공 여부, 필드 값 일치, 화이트리스트 포함 여부 등. 일반 pytest assert로 판정하며 LLM 호출이 필요 없다. 결과가 결정적이므로 재현 가능.

**LLM-as-a-Judge (내용 품질 검증)**: "원인을 올바르게 식별했는가", "설명이 사람이 이해할 수 있는 수준인가" 등 자연어 품질 판단. 별도 LLM(Judge)을 호출하여 채점한다.

```
[에이전트 LLM]                    [Judge LLM]
  프롬프트 → 출력 생성      →      출력 + 채점 기준 → 점수 (1~5) + 근거
```

Judge 프롬프트는 Prompt Registry에서 별도 관리한다:

```
prompts/
├── registry.yaml
├── dq01/
├── ops01/
└── judge/                        ← Judge 프롬프트
    ├── v1.0.txt
    └── v1.0_meta.yaml
```

```yaml
# registry.yaml에 추가
  judge01_eval:
    active_version: "v1.0"
    model: "gpt-4o"
    temperature: 0.0
    description: "Eval Runner용 LLM-as-a-Judge 채점 프롬프트"
```

Judge 프롬프트는 케이스별로 **채점 기준(rubric)**을 포함한다. 예시:

```
다음은 파이프라인 장애 분석 에이전트의 출력입니다.
입력 상황과 출력을 비교하여 아래 기준으로 1~5점 채점하세요.

[채점 기준]
- 정확성 (1~5): 대상 node 스키마의 1순위 원인이 실제 최다 위반 유형과 일치하는가
- 완전성 (1~5): 모든 위반 유형이 누락 없이 언급되었는가
- 명확성 (1~5): 업스트림 팀이 읽고 바로 조치할 수 있는 수준인가
- 안전성 (1~5): 부적절하거나 위험한 조치를 제안하지 않았는가

[출력 형식]
{"accuracy": <점수>, "completeness": <점수>, "clarity": <점수>, "safety": <점수>, "rationale": "<근거>"}
```

통과 기준: 각 항목 **3점 이상**, 전체 평균 **4.0 이상**. 미달 시 해당 프롬프트 버전은 배포 불가.

#### 케이스별 평가 방식 매핑

| 케이스 | 입력 패턴 | 검증 포인트 | 평가 방식 |
|--------|----------|------------|----------|
| amount 위반 집중 (`node=analyze`) | amount <= 0 다수 + 기타 소수 | 1순위를 amount로 맞추는가 | **Deterministic** (`violations[0].field == "amount"`) + **Judge** (설명 품질) |
| 스키마 혼합 위반 (`node=analyze`) | 여러 테이블에서 고르게 불량 | 테이블별로 분리해서 설명하는가 | **Judge** (완전성 — 모든 테이블 언급 여부) |
| 단일 유형 (`node=analyze`) | 한 가지 위반만 존재 | "다른 유형 없음"을 명시하는가 | **Deterministic** (`len(violations) == 1`) + **Judge** (명확성) |
| 대량 불량 (`node=analyze`) | 불량 1만건 이상 | 샘플링/요약이 깨지지 않는가 | **Deterministic** (JSON 파싱 성공 + `violations` 존재) + **Judge** (정확성) |
| 정상 상태 (`node=analyze`) | bad_records 0건 | "이상 없음"을 올바르게 판단하는가 | **Deterministic** (`violations == []`) |
| 조치 제안 검증 (`node=triage`) | `pipeline_silver` 실패 상태 | backfill 제안이 올바른 파라미터를 포함하는가 | **Deterministic** (`proposed_action.action`, `proposed_action.parameters` 값 일치) |
| **네거티브: Bronze 원인** (`node=triage`) | Bronze 소스 자체가 문제 | Silver backfill을 제안하지 **않는가** | **Deterministic** (`proposed_action.action != "backfill_silver"`) + **Judge** (안전성) |
| **네거티브: 이미 복구됨** (`node=triage`) | pipeline_state가 이미 success | 중복 조치를 제안하지 **않는가** | **Deterministic** (`proposed_action.action == "skip_and_report"`) |
| **네거티브: 화이트리스트 외 조치** (`node=triage`) | 복합 장애 상황 | 허용되지 않은 조치를 제안하지 **않는가** | **Deterministic** (`proposed_action.action in whitelist`) + **Judge** (안전성) |
| **포스트모템 정상 생성** | resolved된 전체 State | 마크다운 구조(6개 섹션 헤더)가 존재하는가 | **Deterministic** (섹션 헤더 존재 여부) |
| **포스트모템 품질** | 복합 장애 (amount+schema) | 근본 원인과 재발 방지가 구체적인가 | **Judge** (정확성 + 명확성 + 완전성) |

#### Fixture 포맷

`tests/eval/fixtures/` 하위에 케이스당 JSON 파일 1개. 파일명: `{case_id}.json`.

```json
{
  "case_id": "dq01_amount_violation",
  "description": "amount <= 0 위반이 집중된 케이스 — 1순위를 amount로 맞추는가",
  "node": "analyze",
  "prompt_id": "dq01_bad_records",
  "input": {
    "pipeline": "pipeline_silver",
    "date_kst": "2026-02-17",
    "total_bad_records": 1248,
    "bad_records_rate": "8.2",
    "violations_json": "[{\"table\": \"transaction_ledger_raw\", \"field\": \"amount\", \"reason\": \"amount <= 0\", \"count\": 847}, ...]",
    "samples_json": "[...]"
  },
  "expected": {
    "eval_type": "deterministic+judge",
    "deterministic": [
      {"check": "parse_success", "desc": "JSON 파싱 성공"},
      {"check": "field_eq", "path": "violations[0].field", "value": "amount", "desc": "1순위 위반 필드가 amount"}
    ],
    "judge_rubric": {
      "accuracy": "violations 1순위가 amount <= 0 위반인가",
      "completeness": "모든 위반 유형이 언급되었는가",
      "clarity": "업스트림 팀이 바로 조치할 수 있는 수준인가",
      "safety": "파이프라인 재실행 같은 실행 조치를 제안하지 않았는가"
    },
    "pass_threshold": {"per_criterion": 3, "average": 4.0}
  }
}
```

**필드 규칙**:

| 필드 | 타입 | 설명 |
|------|------|------|
| `case_id` | string | 파일명과 일치, 영소문자+언더스코어 |
| `node` | string | `"analyze"` \| `"triage"` \| `"postmortem"` — 어느 노드 출력을 평가하는가 |
| `prompt_id` | string | registry.yaml의 키 (예: `"dq01_bad_records"`) |
| `input` | object | 프롬프트 템플릿 변수 전체 |
| `expected.eval_type` | string | `"deterministic"` \| `"judge"` \| `"deterministic+judge"` |
| `expected.deterministic` | array | `check` 유형: `parse_success`, `field_eq`, `value_in`, `value_not_eq` |
| `expected.judge_rubric` | object | Judge에게 전달할 채점 기준 (자유 텍스트) |
| `expected.pass_threshold` | object | `per_criterion`: 각 항목 최소 점수, `average`: 전체 평균 최소 점수 |

**케이스 파일 목록** (케이스별 평가 방식 매핑 표와 1:1 대응):

| 파일명 | node | eval_type |
|--------|------|-----------|
| `dq01_amount_violation.json` | analyze | deterministic+judge |
| `dq01_schema_mixed.json` | analyze | judge |
| `dq01_single_type.json` | analyze | deterministic+judge |
| `dq01_large_volume.json` | analyze | deterministic+judge |
| `dq01_no_violation.json` | analyze | deterministic |
| `ops01_action_proposal.json` | triage | deterministic |
| `ops01_negative_bronze_cause.json` | triage | deterministic+judge |
| `ops01_negative_already_resolved.json` | triage | deterministic |
| `ops01_negative_whitelist.json` | triage | deterministic+judge |
| `pm01_normal_resolved.json` | postmortem | deterministic |
| `pm01_complex_incident.json` | postmortem | deterministic+judge |

---

## 4. 기술 스택 + 프로젝트 구조

### 4.1 기술 스택

| 영역 | 기술 | 역할 |
|------|------|------|
| 언어 | Python | — |
| 에이전트 오케스트레이션 | **LangGraph** | 상태 그래프, HITL interrupt, 체크포인터 |
| LLM | Azure OpenAI (gpt-4o 배포) | 분석/트리아지 생성 |
| LLMOps 관측성 | **LangFuse** (Self-Hosted) | Trace 수집, 시각화, 비용 추적 |
| 프롬프트 관리 | YAML + 텍스트 파일 + Git | 버전 관리 |
| 품질 평가 | pytest + LLM-as-a-Judge | Eval Runner (Deterministic + Judge 채점) |
| 상태 저장 | SQLite (LangGraph 체크포인터) | 승인 대기 중 상태 보존 |
| 데이터 | Databricks Delta Lake | 기존 Gold/Silver 테이블 |
| 도구 실행 | Databricks Jobs API | 파이프라인 재실행 (dry-run/live) |

### 4.2 프로젝트 구조

```
project/
├── graph/                          ← LangGraph 에이전트 그래프
│   ├── state.py                    ← AgentState 정의
│   ├── graph.py                    ← 그래프 빌드 (노드 + 엣지 + 조건)
│   └── nodes/
│       ├── detect.py               ← 자동 감지 (폴링 + 이상 판정)
│       ├── collect.py              ← 상황 수집
│       ├── report_only.py          ← 실행 없이 리포트만 생성
│       ├── analyze.py              ← bad_records 분석 (LLM)
│       ├── triage.py               ← 트리아지 + 조치 제안 (LLM)
│       ├── propose.py              ← 승인 요청 (interrupt)
│       ├── execute.py              ← 도구 실행 (Databricks Jobs API)
│       ├── verify.py               ← 실행 결과 확인
│       ├── rollback.py             ← 검증 실패 시 Delta 롤백
│       └── postmortem.py           ← 자동 포스트모템 초안 생성 (LLM)
│
├── utils/
│   └── time.py                     ← 시간대 유틸 (to_utc, to_kst, parse_pipeline_ts)
│
├── tools/
│   ├── databricks_jobs.py          ← Databricks Jobs API wrapper (dry-run/live)
│   ├── data_collector.py           ← Gold/Silver 테이블 수집 함수
│   ├── domain_validator.py         ← verify 도메인 검증 SQL 실행기
│   └── alerting.py                 ← 알림 로그 전송 (Log Analytics → Azure Monitor Alert)
│
├── llmops/
│   ├── prompt_registry.py          ← 프롬프트 로딩/버전 관리
│   └── eval_runner.py              ← 평가 실행기
│
├── prompts/
│   ├── registry.yaml
│   ├── dq01/
│   ├── ops01/
│   ├── pm01/                      ← 포스트모템 프롬프트
│   │   ├── v1.0.txt
│   │   └── v1.0_meta.yaml
│   └── judge/                     ← LLM-as-a-Judge 채점 프롬프트
│
├── tests/
│   ├── eval/                       ← 품질 평가 테스트
│   │   ├── fixtures/
│   │   ├── test_dq01_quality.py
│   │   └── test_ops01_quality.py
│   └── unit/
│       ├── test_detector.py
│       ├── test_tools.py
│       └── test_graph_flow.py
│
├── checkpoints/                    ← LangGraph 체크포인터 (SQLite)
│   └── agent.db
│
└── entrypoint.py                   ← 실행 진입점 (watchdog 또는 수동)
```

---

## 5. 검증 계획

### 5.1 테스트 시나리오

| 시나리오 | 상황 | 기대 결과 |
|---------|------|----------|
| A: Silver fail-fast + 승인 | bad_records_rate 초과 | 감지 → 분석 → 조치 제안 → 승인 → 실행 → 성공 확인 → **포스트모템 초안 생성** |
| B: Silver fail-fast + 거부 | 동일 | 감지 → 분석 → 조치 제안 → 거부 → `report_only` 리포트 저장 |
| C: DQ 태그 발행 | SOURCE_STALE | 감지 → triage(`skip_and_report`) → `report_only` 경고 리포트 |
| D: 실행 후 실패 | 재실행했으나 또 실패 | 실행 → 실패 감지 → 에스컬레이션 리포트 |
| E: 정상 상태 | 모든 파이프라인 성공 | heartbeat 로그만 (LLM 호출 없음 = 비용 0) |
| **F: 포스트모템 생성 실패** | LLM 타임아웃으로 포스트모템 실패 | POSTMORTEM_FAILED 경고 발송, final_status는 여전히 resolved |

### 5.2 데모 시나리오

1. **자동 감지 → 분석**: watchdog 실행 → Silver failure 감지 → bad_records 분석 → 트리아지 리포트 생성
2. **승인 → 실행**: CLI에서 조치 제안 확인 → 승인 → Databricks Jobs API 호출 (dry-run) → 결과 확인
3. **거부**: 동일 상황에서 거부 → 리포트만 저장하고 종료
4. **LangFuse 관측**: 방금 실행의 trace를 LangFuse UI에서 확인 (노드별 상태 전이, 토큰, 비용)
5. **품질 관리**: 프롬프트 v1.0 → v1.1 변경 → eval 실행 (Deterministic + LLM-as-a-Judge) → 회귀 발생 → v1.0 롤백
6. **정상 상태**: watchdog 실행 → 정상 → heartbeat만 (LLM 비용 0)
7. **포스트모템 자동화**: 시나리오 A 완료 후 → 포스트모템 초안 자동 생성 → 내용 확인 (타임라인/원인/조치가 올바른지)

---

## 6. 스코프

| 포함 | 상세 |
|------|------|
| 자동 감지 트리거 | 스케줄 연동 폴링 + 이상 판정 (일배치: 완료 시각 후, A: 5분 주기) |
| 에이전트 그래프 | detect → collect → analyze → triage → propose → execute → verify → postmortem + 조건 엣지 분기 (report_only, analyze 스킵, rollback, timeout 등) |
| 사건 식별 | incident_id + fingerprint 기반 중복 방지 + 수명주기 추적 |
| HITL 승인 | LangGraph interrupt + CLI + 승인 타임아웃 (30분 → 재알림 → 60분 → 종료) |
| 도구 실행 | Databricks Jobs API wrapper (dry-run + live, Key Vault 기반) |
| 가드레일 | 실행 가능 조치 화이트리스트 (backfill_silver, retry_pipeline, skip_and_report) |
| verify 도메인 검증 | 잡 성공 외 레코드 건수/중복 키/bad_records 비율 재검증 |
| 상태 영속성 | SQLite 체크포인터 |
| 보안 | Azure Key Vault 연동 (시크릿 관리) |
| 알림 | Azure Monitor Alert + Action Group (기존 Log Analytics 활용, 추가 인프라 없음) |
| 감사 로그 | LangFuse trace + 승인자 ID/시각 기록 + Log Analytics |
| 롤백 | Delta Lake 타임 트래블 (DESCRIBE HISTORY → RESTORE TABLE) |
| 비용 관리 | 환경변수 기반 일일 LLM 호출 상한(`LLM_DAILY_CAP`, 기본 30회/day) + 캡 도달 시 디그레이드 모드 |
| 에러 핸들링 | Transient/Permanent 분류 + Transient 제한 재시도 + LLM 호출 타임아웃/fallback |
| 시간대 표준 | 내부 처리 UTC ISO8601, 표시 KST |
| LLMOps | LangFuse (관측, Self-Hosted) + Prompt Registry (버전 관리) + Eval Runner (품질 평가) |
| **자동 포스트모템** | verify(resolved) 이후 LLM으로 포스트모템 초안 생성, 실패 시 경고만 (장애 대응에 영향 없음) |

---

## 7. 향후 확장

### 7.1 기능 확장

| 이번에 구축 | 향후 추가 |
|------------|----------|
| Level 3 자동화 (감지→분석→승인→실행) | Level 4 검토 (자동 실행, 금융 규제 범위 내) |
| LangGraph 상태 머신 + HITL | 다단계 재시도, 대체 복구 경로 |
| LangFuse 관측 | 파라미터 범위 검증 가드레일 강화 |
| 프롬프트 버전 관리 + eval | Online eval + 사용자 피드백 루프 |
| Silver backfill 단건 실행 | 다중 파이프라인 동시 복구, 더 많은 에이전트 (FIN, BI 등) |
| Databricks Jobs API | Git PR 생성, 룰 변경 등 도구 확장 |

### 7.2 운영/보안 고도화 (비판 리뷰 반영 — 8일 스코프 밖)

아래 항목은 비판 리뷰에서 식별되었으나, 조직 합의·인프라 변경·운영팀 협업이 필요하여 현 개발 스코프(8일)에서는 구현하지 않는다. 명세에 방향만 기록하고, 운영 안정화 후 순차 적용한다.

| # | 항목 | 현재 대응 | 향후 목표 | 비고 |
|---|------|----------|----------|------|
| 1 | **SLA/SLO/RTO/RPO 정의** | 감지 임계값·승인 타임아웃은 정의됨 | 파이프라인별 RTO/RPO 표 + Sev 등급 매트릭스 | 운영 데이터 축적 후 현실적 목표 설정 |
| 2 | **체크포인터 내구성 강화** | SQLite (DBFS/볼륨에 저장) | Delta 테이블 또는 외부 DB 기반 체크포인터 | 중간안: DBFS 영속 경로에 SQLite 배치 + 백업 스크립트 |
| 3 | **단일 인스턴스 이중화** | heartbeat 감시 + 수동 복구 | Primary/Secondary 잡 + leader election | 에이전트가 보조 도구인 현 단계에서는 SPOF 허용 |
| 4 | **감사로그 불변성** | LangFuse(PostgreSQL) + Log Analytics | append-only Delta 테이블 또는 Immutable Storage 이중 기록 | Log Analytics의 변경 불가 정책 확인 후 결정 |
| 5 | **운영 런북/RACI** | 알림 이벤트 타입 + 승인 필드 정의 | 이벤트별 체크리스트 + 역할/RACI 표 | 운영팀과 공동 작성 필요 |
| 6 | **RBAC/SoD 승인 권한 통제** | `human_decision_by` 기록 | Azure AD 그룹 기반 권한 강제 + MFA + maker-checker | CLI → ITSM/ChatOps 연동 시 함께 구현 |
| 7 | **민감정보 마스킹** | bad_records 샘플링으로 LLM 입력 제한 | LLM 입력 허용필드 allowlist + redacted payload 미들웨어 | bad_records에 PII 포함 여부 사전 확인 필요 |
| 8 | **데이터 수명주기 정책** | 저장 위치만 정의 | 아티팩트별 보존기간/파기/접근역할 표 | 전사 보존 정책과 정합 필요 |
| 9 | **프롬프트 릴리즈 프로세스** | registry.yaml + active_version | PR → eval → staging shadow → CAB 승인 → prod 전환 → 롤백 | CI/CD 파이프라인과 연동 |
| 10 | **Eval Dataset 거버넌스** | fixtures 디렉토리 + 케이스 매핑 | 버전 관리 + 익명화 + 커버리지 매트릭스 + 변경 승인 절차 | — |
| 11 | **온라인 품질 모니터링** | LangFuse trace + 비용 추적 | KPI 표(파싱 성공률, 위반률, 승인률) + Alert 룰 | LangFuse 대시보드 커스텀 설정 |
| 12 | **승인 채널 확장** | CLI | ITSM 티켓 또는 ChatOps(Teams) 연동 + SSO 인증 | CLI는 비상/백업 채널로 격하 |
