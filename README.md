# NSC Pipeline Ops AI Agent

파이프라인 장애를 야간에 자동 분석하고, 운영자 승인을 받아 조치하는 LangGraph 기반 AI 운영 에이전트.

Last updated: 2026-02-26

## 프로젝트 개요

이 에이전트는 NSC 메달리온 아키텍처(`pipeline_silver`, `pipeline_a`, `pipeline_b`, `pipeline_c`)의 배치 파이프라인을 5분 주기로 감시하다가 장애를 감지하면, 데이터를 수집해 LLM으로 분석하고, 운영자 승인을 받아 Databricks Job을 실행한 뒤 결과를 검증한다.

세 가지를 다룬다:
- **자동 감지**: 파이프라인 상태/예외/DQ 이상을 rule-based로 판정 — 정상 경로에서 LLM 호출 0회
- **LLM 분석**: bad_records 패턴 해석, upstream 원인 특정, 대응 방향 제안 — 사람 수준의 판단을 표준화
- **검증**: 화이트리스트 3종 액션만 허용, 반드시 사람 승인 후 실행, Delta 버전 스냅샷 기반 롤백 보장

## 왜 이 에이전트가 필요한가

#### 문제 1 — 인시던트 대응 품질의 개인 의존

런북은 절차를 따르지만 판단을 전달하지 않는다. 복합 bad_records 위반에서 주원인을 분리하거나,
'Bronze 소스 문제면 Silver backfill은 무의미하다'는 맥락 판단은 런북에 없다.
시니어와 주니어의 대응 품질 편차가 팀의 구조적 리스크가 된다.

#### 문제 2 — 새벽 장애 → 아침 콜드 스타트

장애는 새벽에 발생하고 진단은 아침 출근 후 시작된다.
운영자는 분산된 테이블을 쿼리해 문맥을 재구성하는 것부터 해야 한다.
이 진단 시간이 전부 복구 리드타임이 된다.


#### 이 설계의 접근

- 시니어 판단력의 표준화: 에이전트가 모든 당직자에게 동일한 수준의 분석을 제공한다.
  '정적 런북'이 아닌 '맥락을 읽는 판단력'을 팀 전체에 균등하게 공급한다.
- 진단 리드타임 제거: 에이전트가 새벽에 분석을 완료해둔다. 운영자는 출근 시
  '진단'이 아닌 '검토' 부터 시작한다.
  승인 게이트는 최대 12시간 대기하므로 아침 출근 전 타임아웃 없이 ActionPlan이 유지된다.
- 팀 지식 체계화: 포스트모텀 초안 자동 생성과 인시던트 지문으로
  경험을 팀 자산으로 전환한다.

## 에이전트 흐름

```text
[detect]
  ├─ 정상 ──────────────────────────────────────────────► END (heartbeat)
  ├─ 컷오프 지연 ─────────────────────────────► [report_only] ─► END
  └─ 실패 / 새 CRITICAL 예외 / CRITICAL DQ
        └─► [collect]
               └─► (bad_records 있음) ─► [analyze] ─┐
               └─► (DQ 태그만)         ────────────► [triage]
                                                       └─► [propose] ─► [interrupt]
                                                                          ├─ approve ─► [execute]
                                                                          │                └─► [verify]
                                                                          │                      ├─ resolved ─► [postmortem] ─► END
                                                                          │                      └─ 실패 ─────► [rollback] ──► END
                                                                          ├─ reject ──► [report_only] ─► END
                                                                          └─ timeout ─────────────────────────────────────► END (escalated)
```

### 시나리오별 동작

| 시나리오 | 트리거 조건 | 실행 경로 | final_status |
|---|---|---|---|
| A — 파이프라인 실패 | `pipeline_silver` 또는 `pipeline_b/c` status = failure | detect → collect → analyze → triage → propose → interrupt → execute → verify | resolved / escalated |
| B — bad_records 급등 | `bad_records_rate > 5%` (verify #5 실패) | … → execute → verify → rollback | escalated |
| C — CRITICAL DQ | `dq_tag IN ('SOURCE_STALE', 'EVENT_DROP_SUSPECTED')` | detect → collect → triage(analyze 스킵) → propose → interrupt → execute → verify | resolved |
| D — 새 CRITICAL 예외 | `gold.exception_ledger`에 신규 CRITICAL domain=dq 행 | detect → collect → analyze → triage → propose → interrupt → execute → verify | resolved / escalated |
| E — 정상 | 모든 파이프라인 정상, 이상 없음 | detect → END | — (heartbeat만) |
| F — 컷오프 지연 | 예상 완료 시각 초과, 실패는 아님 | detect → report_only → END | reported |

### 파이프라인별 폴링 스케줄

| 파이프라인 | 감지 시작 (KST) | 컷오프 임계값 | 비고 |
|---|---|---|---|
| `pipeline_silver` | 00:10 (일배치) | 30분 초과 → report_only | Silver 완료 후 B/C 순차 실행 가능 |
| `pipeline_b` | 00:35 (일배치) | 30분 초과 → report_only | Silver 준비 상태 필요 |
| `pipeline_c` | 00:45 (일배치) | 30분 초과 → report_only | Silver 준비 상태 필요 |
| `pipeline_a` | 상시 (5분 주기) | 연속 2회 miss → report_only | 마이크로배치 guardrail |

## 주요 컴포넌트

| 파일 | 역할 |
|---|---|
| [graph/graph.py](graph/graph.py) | LangGraph 상태 머신 정의, 조건 엣지 + shim fallback |
| [graph/state.py](graph/state.py) | `AgentState` TypedDict, `TriageReport` Pydantic, `ActionPlan` TypedDict |
| [graph/nodes/detect.py](graph/nodes/detect.py) | 트리거 rule 판정, fingerprint 중복 방지 |
| [graph/nodes/collect.py](graph/nodes/collect.py) | 예외/DQ 태그/bad_records 수집 및 정규화 |
| [graph/nodes/analyze.py](graph/nodes/analyze.py) | LLM: bad_records 패턴 해석 → `dq_analysis` |
| [graph/nodes/triage.py](graph/nodes/triage.py) | LLM: 대응 방향 합성 → `TriageReport` 검증 → `action_plan` SSOT |
| [graph/nodes/propose.py](graph/nodes/propose.py) | 승인 요청 기록, `TRIAGE_READY` 알림 발송 |
| [graph/nodes/execute.py](graph/nodes/execute.py) | approve 확인 후 Databricks Job 호출, 사전 버전 스냅샷 |
| [graph/nodes/verify.py](graph/nodes/verify.py) | 5체크 검증 (job 상태 / 건수 / 중복 / DQ 태그 / bad_records_rate) |
| [graph/nodes/rollback.py](graph/nodes/rollback.py) | `RESTORE TABLE TO VERSION` — blocking 실패 시 원복 |
| [graph/nodes/postmortem.py](graph/nodes/postmortem.py) | LLM: resolved incident 포스트모템 초안 생성 |
| [graph/nodes/report_only.py](graph/nodes/report_only.py) | 실행 없이 리포트 JSON 기록 후 종료 |
| [tools/data_collector.py](tools/data_collector.py) | `gold.pipeline_state` / `silver.dq_status` / `gold.exception_ledger` 쿼리 빌더 |
| [tools/bad_records_summarizer.py](tools/bad_records_summarizer.py) | 유형별 집계 + 상위 10건 샘플링, hard cap 적용 |
| [tools/llm_client.py](tools/llm_client.py) | Azure OpenAI 래퍼: timeout 60s, 429 retry(2→4→8s), daily cap 관리 |
| [runtime/watchdog.py](runtime/watchdog.py) | 5분 주기 폴링 스케줄러, 일배치/마이크로배치 구분 |
| [runtime/agent_runner.py](runtime/agent_runner.py) | graph invoke / incident_id 기반 resume 인터페이스 |
| [ops/entrypoint.py](ops/entrypoint.py) | Databricks Job 진입점 |
| [src/orchestrator/utils/config.py](src/orchestrator/utils/config.py) | 런타임 설정 Pydantic 모델 (TARGET_PIPELINES 등) |
| [src/orchestrator/utils/incident.py](src/orchestrator/utils/incident.py) | `make_incident_id()`, `make_fingerprint()` — 중복 방지 |
| [llmops/prompt_registry.py](llmops/prompt_registry.py) | 프롬프트 버전 로딩 (`dq01` / `ops01` / `pm01`) |

## 개발 로드맵

에이전트는 6개 게이트로 나뉜다. 각 게이트는 독립적으로 검증 가능하다.

| 게이트 | 목표 | 상태 |
|---|---|---|
| G1 | Spec & 실행 환경 인터페이스가 개발 가능 상태로 고정된다 (DEV-001~008) | 진행 중 |
| G2 | 감지/수집/리포트 경로가 LLM 없이도 결정적으로 동작한다 (DEV-009~021) | 진행 중 |
| G3 | LLM 분석/트리아지가 스키마-강제 + 안전한 제안 형태로 생성된다 (DEV-022~026) | 대기 |
| G4 | HITL 승인(Interrupt/CLI/Timeout)과 알림이 운영 플로우로 고정된다 (DEV-027~032) | 대기 |
| G5 | 실행/검증/롤백/포스트모템까지 안전한 End-to-End가 완성된다 (DEV-033~039) | 대기 |
| G6 | LLMOps(관측/버전/평가) + 배포 구성이 운영 가능한 상태로 끝난다 (DEV-040~053) | 대기 |

상세 이슈는 [.roadmap/ai_agent_roadmap.md](.roadmap/ai_agent_roadmap.md)를 참조한다.

## 설정 및 실행

### 주요 런타임 설정

| 환경변수 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `TARGET_PIPELINES` | Y | — | 감시할 파이프라인 목록 (`pipeline_silver,pipeline_b,pipeline_c,pipeline_a`) |
| `CHECKPOINT_DB_PATH` | N | `checkpoints/agent.db` | SQLite 체크포인터 경로 (로컬) 또는 UC Volumes 경로 (prod) |
| `LLM_DAILY_CAP` | N | `30` | 하루 LLM 호출 상한. 초과 시 `skip_and_report` fallback |
| `LANGFUSE_HOST` | N | — | Self-hosted LangFuse 엔드포인트 (G6에서 활성화) |

Azure Key Vault에서 주입되는 시크릿:

| Key Vault 키 | 환경 | 설명 |
|---|---|---|
| `azure-openai-api-key` | dev/staging/prod | Azure OpenAI API 키 |
| `azure-openai-endpoint` | dev/staging/prod | Azure OpenAI 엔드포인트 |
| `databricks-agent-token` | dev/staging/prod | Databricks API 토큰 |
| `agent-execute-mode` | staging/prod | `dry-run` 또는 `live` (dev는 항상 dry-run) |

### dry-run vs live

dev/staging은 `agent-execute-mode = dry-run`으로 고정된다. dry-run 모드에서는 Databricks Job API를 호출하지 않고 실행 결과를 시뮬레이션한다. prod에서만 Key Vault의 `agent-execute-mode = live`로 실제 실행이 허용된다.

## 개발 및 검증 (Quickstart)

로컬 환경 준비:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

단위 테스트:

```bash
pytest tests/unit/ -v -x
```

특정 노드 테스트:

```bash
pytest tests/unit/test_detect.py -v
pytest tests/unit/test_collect.py -v
```

로컬 그래프 스모크 (정상 시나리오 E):

```bash
python -c "
from graph.graph import build_graph
from graph.state import AgentState
graph = build_graph()
result = graph.invoke({'pipeline': 'pipeline_silver', 'incident_id': 'inc-test'})
print(result['final_status'])
"
```

CI 게이트 (`.github/workflows/ci.yml`):
- Unit coverage: `--cov-fail-under=80`

검증 증적 저장 경로:
- `.agents/logs/verification/`

## 안전성 원칙

이 에이전트의 제안은 자동이지만 실행은 반드시 사람이 승인해야 한다.

핵심 제약:
- 화이트리스트 3종만 허용: `backfill_silver` / `retry_pipeline` / `skip_and_report` 외 action은 코드 수준에서 거부
- HITL 없이 execute 불가: `human_decision ≠ 'approve'` 이면 execute 노드 진입 차단
- 타임아웃 = 에스컬레이션: 12시간 미승인 시 `final_status = 'escalated'` — 자동 실행 없음
- dev/staging = dry-run 강제: `agent-execute-mode` 키가 Key Vault에 없으면 dry-run으로 fallback

## 참고 문서 (SSOT)

- [.specs/ai_agent_spec.md](.specs/ai_agent_spec.md) — 전체 에이전트 기획서 (§2 상태 스키마, §2.3 트리거, §2.5 에러 처리 정책)
- [.roadmap/ai_agent_roadmap.md](.roadmap/ai_agent_roadmap.md) — G1~G6 로드맵 및 DEV-### 이슈 목록
- [docs/adr/](docs/adr/) — 아키텍처 결정 기록 (ADR-0004 루트 배치, ADR-0008 쿼리 윈도우, ADR-0009 bad_records 상한 등)
- [AGENTS.md](AGENTS.md) — 에이전트 개발 워크플로우 및 납품 기준
