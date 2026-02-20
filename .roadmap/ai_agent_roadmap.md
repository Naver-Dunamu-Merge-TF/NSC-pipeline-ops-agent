<!-- AI 워크플로 실행 원칙 -->
> **[CRITICAL RULE] 1 Task = 1 PR**
> - 에이전트는 한 번의 세션에서 **단 하나의 DEV 태스크**만 수행하고 즉시 PR을 생성해야 합니다.
> - 범위를 넘어서는 오버엔지니어링이나 다른 태스크의 파일을 수정하는 것을 엄격히 금지합니다.
> - `.specs/`나 핵심 설정을 변경하는 태스크는 `approval: manual`로 지정되어 사람이 직접 리뷰해야 합니다.

## G1: Spec & 실행 환경 인터페이스가 “개발 가능 상태”로 고정된다

### Epic: [EPIC-01] Spec SSOT 정합성을 고정한다

#### DEV-001: 에이전트 입력 테이블 사용 컬럼을 SSOT로 고정하면 구현 중 스키마 혼선이 사라진다

##### priority

P0

##### verify

L1

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

-

##### status

backlog

##### DoD

* [ ] `.specs/data_contract.md`에 `gold.pipeline_state`, `silver.dq_status`, `gold.exception_ledger`, `silver.bad_records`의 **에이전트 사용 컬럼만** 정리되어 있다
* [ ] `gold.pipeline_state.status` 컬럼이 SSOT 문서에 포함되고(기획서의 ⚠️ 불일치 해소), “SSOT는 data_contract.md”로 명시돼 있다
* [ ] `silver.bad_records.reason` 포맷이 **현재 가정 + 확인 필요**로 명시되고, field 추출이 불확실할 때의 fallback(예: field=`"unknown"`) 원칙이 문서에 있다
* [ ] 기획서(본 문서)에서 `data_contract.md`로의 참조 링크가 연결돼 있다
* [ ] 문서 변경 후 기존 CI(테스트/린트/포맷)가 모두 통과한다

#### DEV-002: 파이프라인별 감지 스케줄/임계값을 설정으로 고정하면 detect가 동일 규칙으로 판단한다

##### priority

P0

##### verify

L1

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

-

##### status

backlog

##### DoD

* [ ] `config/pipeline_monitoring.yaml`(또는 동등 파일)에 `pipeline_silver/pipeline_b/pipeline_c/pipeline_a`의 감지 윈도우/폴링 주기/컷오프 임계값이 §2.3과 동일하게 기록돼 있다
* [ ] “임계값 **초과** 시 컷오프 지연” 같은 경계 정의(=와 >)가 설정 파일 주석/문서에 명확하다
* [ ] 설정 스키마 검증(필수 키 누락/타입 오류)이 동작한다(예: Pydantic/Schema)
* [ ] 설정 로딩 단위 테스트(정상 로드 + 필수 키 누락 실패)가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-02] verify/rollback 대상 카탈로그를 고정한다

#### DEV-003: verify/rollback 대상 정의를 설정으로 고정하면 검증과 롤백 구현이 즉시 가능하다

##### priority

P0

##### verify

L1

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

-

##### status

backlog

##### DoD

* [ ] `config/validation_targets.yaml`(또는 동등 파일)에 verify #1~#5의 **대상 테이블/PK/임계값/정책(rollback 여부)**가 기획서 표와 동일하게 정의돼 있다
* [ ] “전일 대비 ±50%”의 경계(=50%는 통과/실패 중 무엇인지)가 명확히 정의돼 있다
* [ ] rollback 대상 Delta 테이블 목록이 설정에 포함돼 있다
* [ ] 설정 스키마 검증(필수 키, pk 배열 타입 등) 테스트가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-03] 런타임 설정/시크릿 계약을 고정한다

#### DEV-004: 런타임 설정을 Pydantic으로 검증하면 누락/오타가 실행 초기에 실패한다

##### priority

P0

##### verify

L1

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

-

##### status

backlog

##### DoD

* [ ] `utils/config.py`에 런타임 설정 모델이 정의돼 있고, `TARGET_PIPELINES`, `CHECKPOINT_DB_PATH`, `LLM_DAILY_CAP`, `LANGFUSE_HOST` 등을 로드/검증한다
* [ ] `TARGET_PIPELINES`가 `pipeline_silver,pipeline_b,...` 문자열에서 공백 제거 포함해 list로 안정적으로 파싱된다
* [ ] `CHECKPOINT_DB_PATH` 기본값이 기획서 기본값(로컬 `checkpoints/agent.db`)과 정합하다
* [ ] 누락 시 “어떤 키가 누락됐는지”를 포함한 오류로 fail-fast한다
* [ ] 단위 테스트(정상/누락/형식 오류)가 존재한다
* [ ] 기존 CI가 모두 통과한다

#### DEV-005: Key Vault 시크릿을 동일 인터페이스로 로드하면 dev/staging/prod에서 설정 주입 방식이 통일된다

##### priority

P0

##### verify

L2

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-004

##### status

backlog

##### DoD

* [ ] `utils/secrets.py`에 `get_secret(key: str) -> str`(또는 동등) 인터페이스가 있고, Key Vault 키(예: `azure-openai-api-key`, `databricks-agent-token`)를 로드할 수 있다
* [ ] 로컬/테스트에서는 stub(환경변수 또는 테스트 더블)로 동작해 단위 테스트가 가능하다
* [ ] dev Databricks 환경에서 **최소 1개 시크릿**(예: `azure-openai-endpoint`)을 실제로 읽는 스모크가 통과한다
* [ ] 실패 시 Transient/Permanent 분류가 가능하도록 예외 타입/에러 메시지 규약이 있다
* [ ] 기존 CI가 모두 통과한다

#### DEV-006: 환경별 설정 매트릭스를 문서로 고정하면 배포 시 사람이 헷갈리지 않는다

##### priority

P1

##### verify

L1

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-004

##### status

backlog

##### DoD

* [ ] `.specs/runtime_config.md`에 Key Vault 키/환경변수 목록과 dev/staging/prod 값(또는 성격)이 기획서 표와 동일하게 정리돼 있다
* [ ] “dev/staging은 dry-run 고정, prod는 live” 정책이 문서에 명시돼 있다
* [ ] 문서가 코드(`utils/config.py`, `utils/secrets.py`)와 키 이름 수준에서 불일치가 없다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-04] Databricks 실행 액션 계약을 고정한다

#### DEV-007: ActionPlan을 화이트리스트+파라미터로 검증하면 execute가 허용된 조치만 수행한다

##### priority

P0

##### verify

L1

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

-

##### status

backlog

##### DoD

* [ ] `tools/action_plan.py`(또는 동등)에 화이트리스트 3종(`backfill_silver`, `retry_pipeline`, `skip_and_report`) 검증이 구현돼 있다
* [ ] 액션별 필수 파라미터 스키마가 정의돼 있다(예: `backfill_silver`: `pipeline`, `date_kst`, `run_mode`)
* [ ] 유효하지 않은 action/파라미터(누락/타입 오류/금지 파라미터)가 명확한 오류로 거부된다
* [ ] 경계값 테스트(필수 파라미터 누락, action 오타, date 포맷 오류)가 존재한다
* [ ] 기존 CI가 모두 통과한다

#### DEV-008: Databricks Job 식별자 매핑을 설정으로 고정하면 실행기가 올바른 Job을 호출한다

##### priority

P0

##### verify

L1

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

-

##### status

backlog

##### DoD

* [ ] `config/databricks_jobs.yaml`(또는 동등)에 파이프라인/액션 → Databricks Job ID 매핑이 정의돼 있다(환경별 값은 추후 주입 가능)
* [ ] 설정 로딩/검증 테스트(숫자 타입, 중복 키, 누락)가 존재한다
* [ ] 문서(`.specs/runtime_config.md`)에 “어디에 Job ID를 넣는지”가 명시돼 있다
* [ ] 기존 CI가 모두 통과한다

---

## G2: 감지/수집/리포트 경로가 LLM 없이도 결정적으로 동작한다

### Epic: [EPIC-05] 프로젝트 스켈레톤 + LangGraph 골격을 구축한다

#### DEV-009: 프로젝트 구조와 AgentState가 코드에 정의되면 노드 구현을 병렬로 시작할 수 있다

##### priority

P0

##### verify

L1

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-001, DEV-002

##### status

backlog

##### DoD

* [ ] §4.2 구조대로 `graph/`, `tools/`, `utils/`, `llmops/`, `prompts/`, `tests/` 기본 뼈대가 생성돼 있다
* [ ] `graph/state.py`에 `AgentState`, `ActionPlan`, `TriageReport(Pydantic)`가 기획서 스키마(§2.2, §2.4)와 동일하게 정의돼 있다
* [ ] `graph/nodes/*` 파일이 생성돼 있고, 각 노드는 “읽기/쓰기 필드 원칙(§2.2.1)”을 어기지 않는 시그니처/스텁을 가진다
* [ ] `import`/패키지 로딩이 깨지지 않는다(기본 import 테스트 존재)
* [ ] 기존 CI가 모두 통과한다

#### DEV-010: 모든 노드/엣지가 연결된 LangGraph가 실행되면 END까지 상태가 흐른다

##### priority

P0

##### verify

L1

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-001, DEV-002, DEV-009

##### status

backlog

##### DoD

* [ ] `graph/graph.py`에 detect→collect→(analyze?)→triage→propose→interrupt→execute→verify→(rollback?)→postmortem의 전체 노드/엣지 구조가 §2.1 흐름과 동일하게 정의돼 있다
* [ ] `report_only`, analyze 스킵, rollback, timeout 등 조건 엣지가 그래프 구조에 포함돼 있다(노드는 스텁이어도 됨)
* [ ] 최소 1개 경로(정상 → END)가 로컬에서 graph.invoke로 끝까지 실행된다
* [ ] 그래프 빌드/실행 스모크 테스트가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-06] Time Policy 유틸을 구현한다

#### DEV-011: UTC/KST 변환 유틸을 제공하면 시간 비교와 표기가 일관된다

##### priority

P0

##### verify

L1

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

-

##### status

backlog

##### DoD

* [ ] `utils/time.py`에 `to_utc()`, `to_kst()`, `parse_pipeline_ts()`가 구현돼 있다(§2.5 Time Policy)
* [ ] KST 표시 포맷이 문서 예시(`YYYY-MM-DD HH:MM KST`)와 정합하다
* [ ] 경계 테스트(자정/날짜 변경, timezone-aware/naive 입력)가 존재한다
* [ ] 잘못된 입력 포맷에서 명확한 예외가 난다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-07] 체크포인터 + incident_id/fingerprint 중복방지 뼈대를 완성한다

#### DEV-012: incident_id/fingerprint를 생성하면 동일 장애 재처리가 차단된다

##### priority

P0

##### verify

L1

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-004, DEV-005, DEV-006, DEV-009, DEV-010

##### status

backlog

##### DoD

* [ ] `utils/incident.py`(또는 동등)에 `make_incident_id()`, `make_fingerprint()`가 구현돼 있다(§2.2 스키마/§2.3 중복 방지)
* [ ] `detected_issues`가 순서가 달라도 동일 fingerprint가 나오도록 canonicalization이 구현돼 있다
* [ ] 경계 테스트(run_id=None, detected_issues=[], 이슈 순서 변경)가 존재한다
* [ ] 기존 CI가 모두 통과한다

#### DEV-013: Sqlite 체크포인터와 thread_id 전략을 적용하면 프로세스 재시작 후 그래프가 재개된다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-004, DEV-005, DEV-006, DEV-009, DEV-010, DEV-011, DEV-012

##### status

backlog

##### DoD

* [ ] `CHECKPOINT_DB_PATH`로 `SqliteSaver` 체크포인터가 초기화된다(로컬 기본값/Databricks 경로 모두 지원)
* [ ] `incident_id`를 `thread_id`로 사용해 graph 실행이 시작된다(§체크포인터 설계)
* [ ] `runtime/agent_runner.py`(또는 동등)에 **신규 실행**(invoke)과 **재개**(resume) 인터페이스가 정의돼 있다(후속 CLI/승인에서 재사용 가능)
* [ ] (수명주기 추적) incident를 최소 메타(incident_id, pipeline, detected_at, fingerprint, status)를 남기는 **인덱스/레지스트리**(SQLite 내 별도 테이블 또는 동등)가 존재한다
* [ ] 로컬에서 “중단 후 재실행(프로세스 종료 후 재시작)” 시 체크포인트를 읽어 **같은 incident_id로 재개 가능한 것**이 스모크로 확인된다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-08] 데이터 수집기(collect용 SQL 집계/샘플링)를 구현한다

#### DEV-014: 입력 테이블을 조회하는 data_collector가 구현되면 detect/collect가 실제 데이터를 읽는다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-001, DEV-002, DEV-009

##### status

backlog

##### DoD

* [ ] `tools/data_collector.py`에 `gold.pipeline_state`, `silver.dq_status`, `gold.exception_ledger` 조회 함수가 구현돼 있다(§2.2.2)
* [ ] SQL이 윈도우/파이프라인/run_id 필터를 적용해 과도한 스캔을 피한다
* [ ] 반환 포맷(dict/list)이 `AgentState`에 바로 넣을 수 있는 형태로 정리돼 있다
* [ ] 단위 테스트(“생성 SQL/파라미터” 검증 수준)가 존재한다
* [ ] dev Databricks에서 최소 1회 스모크 실행이 성공한다
* [ ] 기존 CI가 모두 통과한다

#### DEV-015: bad_records를 집계+샘플링하면 analyze 입력이 폭주하지 않는다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-001, DEV-002, DEV-009

##### status

backlog

##### DoD

* [ ] `tools/bad_records_summarizer.py`(또는 동등)에 “유형별 집계 + 유형별 상위 10건 샘플”이 구현돼 있다(§2.4 샘플링 전략)
* [ ] 결과 `bad_records_summary`의 크기가 상한(유형 개수/샘플 개수/필드 길이 제한) 내로 제한된다
* [ ] 경계 테스트(0건, 1건, 1만건 이상 가정)가 존재한다
* [ ] 샘플에 `record_json`이 포함되더라도 길이 제한/축약이 적용돼 로그/메모리 폭주가 없다
* [ ] dev Databricks에서 최소 1회 스모크 실행이 성공한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-09] detect 트리거 엔진을 구현한다

#### DEV-016: detect가 트리거 규칙으로 이상을 판정하면 정상 시 LLM 0회로 종료된다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-002, DEV-009, DEV-010, DEV-011, DEV-012, DEV-013, DEV-014, DEV-015

##### status

backlog

##### DoD

* [ ] `graph/nodes/detect.py`가 §2.3 트리거(실패/새 예외/CRITICAL DQ/컷오프 지연/정상)를 동일하게 판정한다
* [ ] “컷오프 지연”은 report_only 경로로 라우팅된다(그래프 분기 동작)
* [ ] “정상”은 heartbeat만 남기고 END로 종료된다(LLM 호출 0회 경로 보장)
* [ ] fingerprint 중복인 경우 신규 incident 실행이 시작되지 않거나 즉시 스킵된다(정책이 코드로 고정)
* [ ] 경계 테스트(임계값 정확히 같음/초과, WARN vs CRITICAL)가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-10] collect + report_only(결정적 리포트) 경로를 완성한다

#### DEV-017: collect가 exceptions/dq_tags/bad_records_summary를 채우면 후속 노드가 동일 입력으로 동작한다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-009, DEV-010, DEV-011, DEV-014, DEV-015, DEV-016

##### status

backlog

##### DoD

* [ ] `graph/nodes/collect.py`가 예외/태그/요약을 수집해 state(`exceptions`, `dq_tags`, `bad_records_summary`)를 채운다
* [ ] “DQ 태그만(파이프라인 정상)” 케이스에서 analyze 스킵 경로가 유지된다(그래프 분기)
* [ ] 수집 실패 시 Transient/Permanent 처리 원칙에 따라 에스컬레이션 또는 재시도 가능하도록 예외가 정리돼 있다
* [ ] 단위 테스트(수집 결과 shape + DQ 태그 전용 경로 입력)가 존재한다
* [ ] 기존 CI가 모두 통과한다

#### DEV-018: report_only가 리포트를 저장하면 경고/거부 경로가 완결된다

##### priority

P1

##### verify

L1

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-009, DEV-010, DEV-011, DEV-014, DEV-015

##### status

backlog

##### DoD

* [ ] `graph/nodes/report_only.py`가 `final_status="reported"`를 설정한다
* [ ] report payload(incident_id, pipeline, detected_issues, 주요 상태)를 **결정적으로** 구성해 저장/출력한다(저장 매체는 최소 1개: 파일/로그/체크포인트 내 아티팩트)
* [ ] 시간 표시는 KST 변환을 사용한다(DEV-011 활용)
* [ ] 경계 테스트(issues 비어있음, pipeline_states 없음)가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-11] watchdog/entrypoint 실행 진입점을 구현한다

#### DEV-019: watchdog가 5분 주기 실행으로 대상 파이프라인을 폴링하면 자동 감지가 운영에서 돈다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-004, DEV-005, DEV-006, DEV-013, DEV-016, DEV-017, DEV-018

##### status

backlog

##### DoD

* [ ] `entrypoint.py`가 Databricks Job에서 실행 가능한 형태로 `watchdog.run_once()`(또는 동등)를 호출한다
* [ ] `TARGET_PIPELINES` 기반으로 대상 파이프라인이 선택된다
* [ ] 일배치 파이프라인은 “예상 완료 이후 윈도우”에서만 판정하고, `pipeline_a`는 5분 주기 폴링 규칙을 따른다(§2.3)
* [ ] 정상 상태에서 heartbeat 로그/이벤트가 남는다(최소 콘솔 로그라도 일관되게)
* [ ] 단위 테스트(폴링 윈도우 계산, 대상 파이프라인 파싱)가 존재한다
* [ ] dev Databricks에서 1회 실행 스모크가 성공한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-12] 결정적 경로에 대한 단위 테스트 베이스를 만든다

#### DEV-020: deterministic 감지 분기 테스트가 통과하면 정상/지연/실패 회귀가 차단된다

##### priority

P0

##### verify

L1

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-011, DEV-012, DEV-016, DEV-017, DEV-018

##### status

backlog

##### DoD

* [ ] 시나리오 E(정상)에서 END로 종료되고 LLM이 호출되지 않는 테스트가 있다
* [ ] 시나리오(지연/실패/CRITICAL DQ/새 예외)별로 detect 판정이 기대와 일치하는 테스트가 있다
* [ ] fingerprint가 이슈 순서에 무관하게 동일하게 생성되는 테스트가 있다
* [ ] 경계값(임계값 정확히 같음/초과)이 테스트로 고정돼 있다
* [ ] 기존 CI가 모두 통과한다

#### DEV-021: graph flow 테스트가 노드 전이를 고정하면 엣지 변경 회귀가 CI에서 잡힌다

##### priority

P0

##### verify

L1

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-010, DEV-016, DEV-017, DEV-018

##### status

backlog

##### DoD

* [ ] 최소 2개 경로(정상 종료 / report_only 경로)가 그래프 전이 테스트로 고정돼 있다
* [ ] 조건 엣지(컷오프 지연, analyze 스킵, rollback 분기)가 깨지면 CI에서 실패한다
* [ ] 기존 CI가 모두 통과한다

---

## G3: LLM 분석/트리아지가 “스키마-강제 + 안전한 제안” 형태로 생성된다

### Epic: [EPIC-13] Prompt Registry(파일 기반 버전관리)를 구축한다

#### DEV-022: Prompt Registry로 프롬프트 버전을 로드하면 노드가 버전 기반으로 프롬프트를 사용한다

##### priority

P0

##### verify

L1

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-009, DEV-010

##### status

backlog

##### DoD

* [ ] `prompts/registry.yaml`이 생성되고 `dq01_bad_records`, `ops01_triage`, `pm01_postmortem` 엔트리가 §3.3 예시와 정합하다
* [ ] `llmops/prompt_registry.py`가 active_version의 프롬프트 텍스트+메타(model/temperature)를 로드한다
* [ ] `prompts/{dq01,ops01,pm01}/v1.0.txt`와 `v1.0_meta.yaml`가 존재하고, JSON-only/안전 규칙이 포함돼 있다
* [ ] 레지스트리 로딩 실패(키 없음/버전 없음)가 명확한 에러로 fail-fast한다
* [ ] 단위 테스트(정상 로드 + 누락 실패)가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-14] LLM 호출 래퍼 + 비용/장애 가드레일을 구현한다

#### DEV-023: Azure OpenAI 클라이언트가 timeout/retry/cap를 적용하면 LLM 장애에도 에이전트가 디그레이드한다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-004, DEV-005, DEV-006, DEV-012, DEV-013

##### status

backlog

##### DoD

* [ ] `tools/llm_client.py`(또는 동등)에 60초 타임아웃, 429 재시도(2s→4s→8s, 최대 3회)가 구현돼 있다(§2.5)
* [ ] Permanent(401/403/404, 파싱/검증 실패 등)는 재시도하지 않는다
* [ ] `LLM_DAILY_CAP`을 초과하면 “디그레이드 모드”로 전환할 수 있는 신호(예: 예외/리턴 코드)가 제공된다
* [ ] 캡 카운트가 실행 간에도 유지되도록(예: 체크포인터 SQLite 내 별도 테이블) 최소한의 영속 저장이 있다
* [ ] 단위 테스트(429 재시도, Permanent 무재시도, 캡 도달)가 존재한다
* [ ] dev 환경에서 1회 LLM 호출 스모크(또는 완전 모킹)가 가능하다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-15] analyze 노드(bad_records 분석)를 구현한다

#### DEV-024: analyze가 bad_records_summary를 JSON 분석으로 바꾸면 불량 패턴과 수정 가이드가 생성된다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-017, DEV-018, DEV-022, DEV-023

##### status

backlog

##### DoD

* [ ] `graph/nodes/analyze.py`가 `bad_records_summary`를 입력으로 `dq01_bad_records`를 호출해 `state.dq_analysis`에 JSON 문자열을 저장한다
* [ ] 샘플링/요약 입력만 사용하고, 전수 bad_records를 LLM 입력으로 넣지 않는다(폭주 방지)
* [ ] 출력이 JSON 파싱 불가일 때의 처리(디그레이드 또는 에스컬레이션)가 정책으로 고정돼 있다
* [ ] 경계 테스트(불량 0건, 다유형, 대량 가정)가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-16] triage 노드(스키마 강제 + action_plan SSOT)를 구현한다

#### DEV-025: triage가 TriageReport를 검증하고 action_plan을 합성하면 propose/execute가 SSOT만 참조한다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-007, DEV-008, DEV-017, DEV-022, DEV-023, DEV-024

##### status

backlog

##### DoD

* [ ] `graph/nodes/triage.py`가 `ops01_triage`를 호출하고 `triage_report_raw`(원문)와 `triage_report`(검증 통과 dict)를 분리 저장한다
* [ ] `TriageReport` Pydantic 검증을 통과해야만 `triage_report`가 저장되고, 실패 시 Permanent 에러로 에스컬레이션된다(§2.4)
* [ ] `action_plan`이 합성 규칙대로 생성되고(`proposed_action`+`expected_outcome`+`caveats`), `tools/action_plan.py`로 2차 검증된다
* [ ] analyze 스킵 경로에서 `dq_analysis=None`을 넣어도 triage가 동작하며, 보수적으로 `skip_and_report`를 제안할 수 있다
* [ ] 경계 테스트(화이트리스트 외 action, 파라미터 누락, JSON 파싱 실패)가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-17] 디그레이드 모드용 deterministic triage 템플릿을 구현한다

#### DEV-026: LLM 캡/실패 시 fallback이 동작하면 비용 0에서도 경고 리포트가 유지된다

##### priority

P0

##### verify

L1

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-023, DEV-024, DEV-025

##### status

backlog

##### DoD

* [ ] LLM 캡 도달 시 analyze/triage가 LLM 호출 없이 fallback으로 전환되는 동작이 테스트로 고정돼 있다
* [ ] fallback 결과가 `skip_and_report`를 생성하고, report_only 경로로 이어질 수 있다
* [ ] Transient 재시도 소진 후 fallback/에스컬레이션 정책이 테스트로 고정돼 있다
* [ ] 경계 테스트(캡 정확히 도달/초과, 연속 실패 횟수 경계)가 존재한다
* [ ] 기존 CI가 모두 통과한다

---

## G4: HITL 승인(Interrupt/CLI/Timeout)과 알림이 운영 플로우로 고정된다

### Epic: [EPIC-18] Log Analytics 기반 알림 전송을 구현한다

#### DEV-027: Log Analytics로 이벤트 로그를 전송하면 Azure Monitor가 알림 트리거를 받을 수 있다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-004, DEV-005, DEV-006

##### status

backlog

##### DoD

* [ ] `tools/alerting.py`가 Log Analytics DCR 기반으로 이벤트를 전송한다(최소: payload JSON 직렬화 + 요청 전송)
* [ ] 이벤트 타입/심각도(`TRIAGE_READY`, `APPROVAL_TIMEOUT`, `EXECUTION_FAILED`, `POSTMORTEM_FAILED` 등)가 코드 상수로 표준화돼 있다
* [ ] 전송 실패 시 Transient/Permanent 분류가 가능하고, Transient는 제한적 재시도 정책이 있다
* [ ] 단위 테스트(HTTP mock)가 존재한다
* [ ] dev에서 테스트 이벤트 1회 전송 스모크가 성공한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-19] propose + interrupt(HITL) 워크플로우를 구현한다

#### DEV-028: propose가 승인 요청을 기록하고 TRIAGE_READY 이벤트를 emit하면 HITL 프로세스가 시작된다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-025, DEV-027

##### status

backlog

##### DoD

* [ ] `graph/nodes/propose.py`가 `approval_requested_ts`(UTC ISO8601)를 기록한다
* [ ] `TRIAGE_READY` 이벤트에 incident_id/pipeline/요약/action_plan이 포함돼 전송된다
* [ ] propose가 `action_plan`을 변경하지 않고 읽기 전용으로 사용한다(SSOT 준수)
* [ ] 단위 테스트(필드 write, 이벤트 payload)가 존재한다
* [ ] 기존 CI가 모두 통과한다

#### DEV-029: interrupt가 approve/reject/modify/timeout을 처리하면 승인 결과에 따라 그래프가 분기된다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-007, DEV-011, DEV-025, DEV-027, DEV-028

##### status

backlog

##### DoD

* [ ] `graph/nodes/interrupt.py`가 LangGraph interrupt 메커니즘으로 “승인 대기” 상태를 만든다
* [ ] approve/reject/modify/timeout 입력이 반영되어 `human_decision*` 필드가 채워진다
* [ ] reject → `final_status="reported"`로 전환되며 report_only로 종료할 수 있다
* [ ] modify → `modified_params` diff가 남고, `action_plan`이 갱신되어 propose로 되돌아간다
* [ ] timeout → `final_status="escalated"`로 종료되며 알림 이벤트가 전송된다(30/60 정책은 DEV-032에서 감시)
* [ ] 단위 테스트(각 decision 분기 + 필드 write)가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-20] 체크포인트 재개/수정 루프를 운영 가능한 형태로 만든다

#### DEV-030: incident_id로 그래프를 resume하는 runner가 제공되면 중단된 실행을 이어갈 수 있다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-012, DEV-013, DEV-028, DEV-029

##### status

backlog

##### DoD

* [ ] `runtime/agent_runner.py`에 `resume(incident_id, payload)`(또는 동등)가 구현돼 있다
* [ ] resume payload로 approve/reject/modify가 interrupt 노드에 전달되어 그래프가 이어서 실행된다
* [ ] 동일 incident(thread)에서 modify→re-propose가 반복되어도 상태가 유실되지 않는다
* [ ] 로컬에서 sqlite 체크포인터 기반 “interrupt 후 resume” 스모크가 통과한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-21] CLI 승인 인터페이스를 구현한다

#### DEV-031: CLI로 incident를 resume하면 승인/거부/수정이 실제 실행 흐름에 반영된다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-007, DEV-008, DEV-029, DEV-030

##### status

backlog

##### DoD

* [ ] `agentctl approve|reject|modify`(또는 동등 CLI)가 제공된다
* [ ] CLI가 `approval_requested_ts`를 KST로 표시하고, action_plan을 사람이 읽을 수 있게 출력한다
* [ ] modify 시 파라미터 diff가 표시되고, `tools/action_plan.py` 검증을 통과해야 resume된다
* [ ] 단위 테스트(인자 파싱, 잘못된 JSON/파라미터 거부)가 존재한다
* [ ] 로컬/개발 환경에서 “approve로 resume” 스모크가 통과한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-22] 승인 타임아웃(30/60분) + 재알림 정책을 구현한다

#### DEV-032: 승인 타임아웃 감시가 동작하면 30분 재알림과 60분 자동 종료가 수행된다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-019, DEV-027, DEV-028, DEV-029, DEV-030

##### status

backlog

##### DoD

* [ ] watchdog run_once가 “승인 대기 중 incident”를 식별할 수 있다(incident 레지스트리/인덱스 기반)
* [ ] 30분 경과 시 `APPROVAL_REMINDER`가 **1회만** 전송된다(중복 방지)
* [ ] 60분 경과 시 `final_status="escalated"`로 전환되고 `APPROVAL_TIMEOUT` 이벤트가 전송된다(자동 실행 금지)
* [ ] 경계 테스트(정확히 30/60분, 이미 리마인드 발송된 케이스)가 존재한다
* [ ] 기존 CI가 모두 통과한다

---

## G5: 실행/검증/롤백/포스트모템까지 “안전한 End-to-End”가 완성된다

### Epic: [EPIC-23] Databricks Jobs API 도구 래퍼를 구현한다

#### DEV-033: Databricks Jobs API wrapper가 dry-run/live로 실행되면 execute가 안전하게 잡을 호출한다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-004, DEV-005, DEV-006, DEV-007, DEV-008

##### status

backlog

##### DoD

* [ ] `tools/databricks_jobs.py`에 `run_databricks_job`, `check_job_status`(또는 동등)가 구현돼 있다
* [ ] `agent-execute-mode`(dry-run/live)가 반영되어 dry-run은 실제 API를 호출하지 않는다
* [ ] “잡 실행 요청 후 타임아웃” 케이스에서 재시도 전에 `check_job_status`로 실행 여부를 확인한다(§2.5 특수 처리)
* [ ] 단위 테스트(HTTP mock, 타임아웃 특수 처리, 5xx 재시도)가 존재한다
* [ ] dev에서 dry-run 스모크가 통과한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-24] execute 노드(사전 스냅샷 기록 포함)를 구현한다

#### DEV-034: execute가 사전 Delta 버전 기록 후 조치를 실행하면 롤백 가능한 실행이 된다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-003, DEV-007, DEV-028, DEV-029, DEV-033

##### status

backlog

##### DoD

* [ ] `graph/nodes/execute.py`가 `human_decision="approve"`일 때만 실행된다(HITL 강제)
* [ ] 실행 전 `pre_execute_table_version`이 기록된다(rollback 대상 테이블 DESCRIBE HISTORY 기반)
* [ ] `action_plan`이 화이트리스트/파라미터 검증을 통과해야만 Databricks Job이 호출된다
* [ ] 실행 결과(`execution_result`)에 job run 식별자/상태가 저장된다
* [ ] 경계 테스트(approve 아님, action 불일치, 파라미터 누락)가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-25] verify 노드(Blocking/Non-blocking 검증)를 구현한다

#### DEV-035: domain_validator가 verify SQL을 실행하면 데이터 정합성 검증이 자동화된다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-003, DEV-014, DEV-015, DEV-034

##### status

backlog

##### DoD

* [ ] `tools/domain_validator.py`가 #2(건수), #3(중복), #4(DQ 태그), #5(bad_records_rate) 검증을 수행할 수 있다
* [ ] 검증 결과가 구조화된 dict로 반환된다(측정값 + pass/fail + 임계값)
* [ ] 경계 테스트(±50% 정확히 경계, 중복 1건, bad_records_rate 정확히 임계)가 존재한다
* [ ] 단위 테스트(SQL 생성/파라미터 검증)가 존재한다
* [ ] 기존 CI가 모두 통과한다

#### DEV-036: verify가 #1~#5 결과로 final_status를 결정하면 resolved/failed/escalated가 일관된다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-003, DEV-034, DEV-035

##### status

backlog

##### DoD

* [ ] `graph/nodes/verify.py`가 #1~#5를 실행하고 `validation_results`를 저장한다
* [ ] #1 실패는 롤백 없이 즉시 `final_status="escalated"`로 종료한다
* [ ] #2/#3/#5 실패는 rollback 경로로 라우팅된다
* [ ] #4는 non-blocking 경고로 기록되며 resolved 판정 자체를 막지 않는다
* [ ] 결과별 테스트(resolved/failed/escalated)가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-26] rollback 노드(Delta RESTORE)를 구현한다

#### DEV-037: rollback이 Delta RESTORE로 복구하면 blocking 실패 시 안전하게 되돌린다

##### priority

P0

##### verify

L3

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-003, DEV-034, DEV-035, DEV-036

##### status

backlog

##### DoD

* [ ] `graph/nodes/rollback.py`가 `pre_execute_table_version` 기반으로 `RESTORE TABLE`을 수행한다
* [ ] 롤백 결과가 `execution_result`에 기록되고 `final_status="escalated"`로 고정된다
* [ ] `ROLLBACK_*` 이벤트가 알림으로 전송된다(DEV-027 활용)
* [ ] staging에서 **테스트용 Delta 테이블**로 1회 RESTORE 스모크가 성공한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-27] postmortem 노드를 구현한다

#### DEV-038: postmortem이 resolved 사건의 초안을 생성하면 대응 기록이 자동 문서화된다

##### priority

P1

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-022, DEV-023, DEV-035, DEV-036

##### status

backlog

##### DoD

* [ ] `graph/nodes/postmortem.py`가 `final_status="resolved"`에서만 실행된다
* [ ] `pm01_postmortem` 프롬프트로 마크다운을 생성해 `postmortem_report`, `postmortem_generated_at`을 기록한다
* [ ] 생성 실패 시 `POSTMORTEM_FAILED` 경고만 남기고 `final_status`는 변경하지 않는다(§2.4)
* [ ] 단위 테스트(실행 조건, 실패 경고 경로)가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-28] 시나리오 A~F E2E 흐름을 검증 가능한 형태로 만든다

#### DEV-039: 시나리오 A~F E2E 재현이 가능하면 릴리즈 회귀를 사전에 차단한다

##### priority

P0

##### verify

L3

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-019, DEV-031, DEV-032, DEV-035, DEV-036, DEV-037, DEV-038

##### status

backlog

##### DoD

* [ ] 시나리오 A~F(§5.1)를 재현하는 테스트 하네스/스크립트(모킹+스테이징 혼합 가능)가 존재한다
* [ ] 시나리오 E(정상)에서 LLM 호출이 0회임을 검증한다(비용 0 경로)
* [ ] 시나리오 A/B/C/D/F의 `final_status`와 알림 이벤트 타입이 기대와 일치한다
* [ ] 실행 방법(runbook)이 문서로 남아 있다
* [ ] staging에서 최소 A/E 1회 스모크가 성공한다
* [ ] 기존 CI가 모두 통과한다

---

## G6: LLMOps(관측/버전/평가) + 배포 구성이 “운영 가능한 상태”로 끝난다

### Epic: [EPIC-29] LangFuse 트레이싱을 코드에 내장한다

#### DEV-040: LangFuse 콜백을 주입하면 노드별 trace와 토큰/비용이 자동 수집된다

##### priority

P0

##### verify

L2

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-004, DEV-005, DEV-006, DEV-013, DEV-022, DEV-023, DEV-043, DEV-044, DEV-045

##### status

backlog

##### DoD

* [ ] LangFuse `CallbackHandler`가 runner/graph.invoke에 주입된다(§3.2)
* [ ] trace 메타에 `incident_id`, `pipeline`, `run_id`, `prompt_id`, `prompt_version`이 포함된다
* [ ] LangFuse가 일시 장애여도 에이전트 실행이 실패하지 않고 경고 이벤트로 degrade한다
* [ ] 단위 테스트(콜백 주입 여부)가 존재한다
* [ ] dev/staging에서 1회 실행이 LangFuse UI에 표시된다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-30] Eval Runner(Deterministic + Judge)와 픽스처 세트를 구축한다

#### DEV-041: Eval Runner deterministic 검증이 fixtures로 실행되면 프롬프트 회귀가 CI에서 탐지된다

##### priority

P0

##### verify

L1

##### approval

auto

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-022, DEV-023, DEV-024, DEV-025, DEV-038

##### status

backlog

##### DoD

* [ ] `llmops/eval_runner.py`가 `tests/eval/fixtures/*.json`를 로드해 deterministic 체크를 실행한다(§3.4)
* [ ] 최소 fixture 세트(기획서 표의 파일 목록)가 저장돼 있다
* [ ] pytest에서 deterministic eval이 실행되고(LLM 호출 없이) 실패 시 CI를 깨뜨린다
* [ ] “파싱 성공/화이트리스트 포함/필드 값 일치” 같은 체크 유형이 구현돼 있다
* [ ] 기존 CI가 모두 통과한다

#### DEV-042: LLM-as-a-Judge 평가가 품질 기준을 통과해야 배포되면 자연어 품질 회귀가 차단된다

##### priority

P1

##### verify

L2

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-022, DEV-023, DEV-024, DEV-025, DEV-038, DEV-041

##### status

backlog

##### DoD

* [ ] `prompts/judge/v1.0.*`와 `registry.yaml`의 `judge01_eval` 엔트리가 추가된다
* [ ] eval_runner가 judge 모드에서 채점 JSON을 파싱하고, 기준(각 항목 ≥3, 평균 ≥4.0)을 적용한다
* [ ] 비용/레이트리밋을 고려해 judge eval은 “수동 또는 nightly” 실행 경로가 준비돼 있다(결정적 eval은 CI 상시)
* [ ] 단위 테스트(모킹된 judge 응답으로 pass/fail 판정)가 존재한다
* [ ] 기존 CI가 모두 통과한다

### Epic: [EPIC-31] Self-Hosted LangFuse 인프라를 배포한다

#### DEV-043: LangFuse를 AKS에 내부 서비스로 배포하면 외부 SaaS 없이 트레이스를 조회한다

##### priority

P0

##### verify

L3

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-006

##### status

backlog

##### DoD

* [ ] LangFuse 배포 매니페스트(Helm 또는 K8s YAML)가 저장소에 추가돼 있다(Deployment + ClusterIP)
* [ ] ACR 이미지 준비(빌드/푸시 절차 또는 검증된 이미지 사용 절차)가 문서/스크립트로 고정돼 있다
* [ ] 외부 노출 없이 VNet 내부에서만 접근 가능한 형태가 확인된다
* [ ] staging에서 LangFuse UI 접속 스모크가 성공한다
* [ ] 롤백(배포 제거/이전 버전) 절차가 문서화돼 있다

#### DEV-044: LangFuse 전용 PostgreSQL이 연결되면 trace 메타데이터가 영속 저장된다

##### priority

P0

##### verify

L3

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-043

##### status

backlog

##### DoD

* [ ] PostgreSQL Flexible Server(B1ms) 프로비저닝 절차(IaC 또는 실행 스크립트)가 준비돼 있다
* [ ] LangFuse가 전용 DB에 연결되고 마이그레이션이 정상 수행된다
* [ ] Pod 재시작 후에도 기존 trace가 유지되는 스모크가 통과한다
* [ ] DB 접속 정보는 시크릿/Key Vault로 관리된다(평문 저장 금지)
* [ ] staging에서 end-to-end trace 저장 스모크가 성공한다

### Epic: [EPIC-32] Private Endpoint/DNS/NSG 등 네트워크 연결을 완성한다

#### DEV-045: Private Endpoint/DNS/NSG 구성이 적용되면 Databricks·LangFuse·OpenAI 통신이 내부망으로 고정된다

##### priority

P0

##### verify

L3

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-043, DEV-044

##### status

backlog

##### DoD

* [ ] `privatelink.postgres.database.azure.com`, `privatelink.openai.azure.com` 등 Private DNS 설정/레코드가 정의돼 있다(체크리스트 또는 IaC)
* [ ] NSG 규칙이 기획서 네트워크 표와 정합하다(Databricks→LangFuse, LangFuse→DB, 내부 OpenAI PE 등)
* [ ] staging에서 Databricks Job → LangFuse, LangFuse → PostgreSQL 통신 스모크가 성공한다
* [ ] 변경 실패 시 롤백 플랜(규칙 되돌리기)이 문서화돼 있다

### Epic: [EPIC-33] Databricks Job 배포 형태를 고정한다

#### DEV-046: Databricks Job 배포 스펙이 스크립트/문서로 고정되면 환경별 배포가 재현된다

##### priority

P0

##### verify

L2

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-004, DEV-005, DEV-006, DEV-019, DEV-027, DEV-039, DEV-040, DEV-045

##### status

backlog

##### DoD

* [ ] watchdog Job 스케줄(5분)과 실행 엔트리포인트가 배포 스펙으로 고정돼 있다
* [ ] 환경변수/시크릿 주입 목록이 명확하고, dev/staging/prod 값 정책이 문서와 일치한다
* [ ] `agent-execute-mode`로 dry-run/live가 전환되며 코드 변경 없이 동작한다
* [ ] heartbeat 기반 경고(30분 무응답) 룰 연결 방법이 문서화돼 있다
* [ ] dev/staging에서 Job 실행 스모크가 성공한다

### Epic: [EPIC-34] 운영 스모크 테스트 + 관측/알림 최소 기준을 잠근다

#### DEV-047: 운영 스모크가 통과하면 heartbeat/알림/trace/eval이 실제로 동작한다

##### priority

P0

##### verify

L3

##### approval

manual

##### source_doc

`.specs/ai_agent_spec.md`

##### depends_on

DEV-039, DEV-040, DEV-041, DEV-042, DEV-043, DEV-044, DEV-045, DEV-046

##### status

backlog

##### DoD

* [ ] 시나리오 E(정상) 스모크에서 heartbeat 이벤트가 Log Analytics에 남고, LLM 호출이 0회임이 확인된다
* [ ] 최소 1개 장애 스모크에서 `TRIAGE_READY` 알림과 LangFuse trace가 동시에 확인된다
* [ ] 승인 타임아웃 강제 케이스에서 30분 리마인드/60분 에스컬레이션 이벤트가 확인된다
* [ ] deterministic eval은 CI에서 상시 통과, judge eval은 수동/야간 경로로 실행 가능하다
* [ ] 운영 runbook(실패 시 확인 순서: Log Analytics → LangFuse trace → 체크포인터 상태)이 업데이트돼 있다
