# RAG 기반 유사 사건 조회 스펙

> **프로젝트**: NSC 결제/정산 데이터 플랫폼 — 파이프라인 장애 대응 에이전트 확장
> **최종 수정일**: 2026-02-22 (v2 — 리뷰 반영)
> **전제**: 기존 로드맵(ai_agent_spec.md) 구현 완료 후 적용

---

## 1. 개요

### 1.1 목적

`triage` 노드가 현재 incident를 분석할 때 과거 유사 장애의 조치 결과를 참조할 수 없다.
동일 패턴의 장애가 반복될 때마다 LLM이 처음부터 추론을 반복하므로 판단 품질이 일정하지 않다.

`postmortem` 노드가 생성하는 장애 보고서를 벡터 DB에 인덱싱하고, triage 시 유사 사건
Top-k를 검색하여 프롬프트에 주입함으로써 판단의 일관성과 속도를 높인다.

### 1.2 해결하는 문제

| 문제 | 현재 상태 | 도입 후 |
|------|----------|--------|
| 반복 패턴 재추론 | 동일 pipeline + 동일 위반 유형이어도 매번 처음부터 추론 | 유사 사건 2~3건을 프롬프트에 제공, LLM이 선례를 참고하여 판단 |
| `skip_and_report` 오판 | Bronze 원인임에도 backfill 시도 추천 위험 | 과거 동일 패턴에서 skip이 올바른 선택이었음을 컨텍스트로 제공 |
| 포스트모템 활용 없음 | 생성 후 저장, 재활용 안 됨 | 인덱싱 파이프라인이 자동으로 지식 베이스에 추가 |

### 1.3 기대 효과

- **판단 근거 명확화**: triage 출력의 `caveats`에 "유사 사건 N건 참조" 표시 가능
- **신규 당직자 지원**: 시니어가 과거에 내린 판단이 누적되어 LLM의 추론 기반이 됨
- **Cold start 이후**: incident 누적 6개월 이상 시 실질적 품질 향상 기대

### 1.4 범위 밖

- `analyze`, `execute`, `verify` 노드 변경 없음
- contracts.py 동적화 (별도 검토 사항)
- 업스트림 수정 가이드 라이브러리 (별도 검토 사항)

---

## 2. 아키텍처

### 2.1 전체 흐름

```
[인덱싱 파이프라인]
postmortem 노드
  └─ final_status = "resolved" AND postmortem_report is not None인 경우
       └─ IncidentIndexer.index_resolved_incident(state)
            ├─ LLM 호출: triage_report + action + outcome → 영어 요약 생성 (~150 토큰)
            │   (이 호출은 incident 처리용 LLM_DAILY_CAP에서 분리된 별도 쿼터)
            ├─ AzureEmbeddingClient.embed(english_summary) → vector(1536)
            └─ IncidentStore.insert(record) → incident_embeddings 테이블

[조회 파이프라인]
triage 노드
  └─ IncidentRetriever.retrieve_for_triage(state)
       ├─ degraded mode이면 즉시 빈 문자열 반환 (embedding 호출 스킵)
       ├─ 쿼리 텍스트 구성 (dq_analysis + exceptions + dq_tags)
       ├─ AzureEmbeddingClient.embed(text) → query vector
       ├─ IncidentStore.search_similar(pipeline, query_vector, k=3)
       └─ _format_for_prompt(similar_incidents) → 프롬프트 주입 문자열
```

### 2.2 triage 프롬프트 주입 위치

기존 triage 프롬프트에 다음 섹션을 추가:

```
## Similar Past Incidents (reference only; omit section if none)
1. [2026-01-15] pipeline_silver | action: backfill_silver | outcome: resolved
   Root cause: Bronze source transaction_ledger_raw stale (T-1 data missing).
   Violations: amount≤0 (43%, ~1,200 records), source_stale on 2 tables.
   Action: backfill_silver window=2026-01-14. Verified resolved in 12 min.
   Key insight: When amount violations coexist with source_stale, fix source freshness first.

2. [2026-01-08] pipeline_silver | action: skip_and_report | outcome: escalated
   Root cause: Upstream ETL filter bug causing non-positive amounts.
   Violations: amount≤0 (98%, ~8,000 records). No data freshness issue.
   Action: skip_and_report — backfill deemed futile, upstream fix required.
   Key insight: Near-100% amount violation rate indicates upstream origin, not Silver logic.
```

- 요약은 인덱싱 시 LLM이 생성한 영어 텍스트 (구조화, ~150 토큰/건)
- 토큰 예산: triage 기존 예산 3,000 토큰 중 **최대 600 토큰** 할당 (k=3 × ~150 토큰 + 헤더)
- 유사 사건 없으면 섹션 전체 생략 (토큰 낭비 없음)

---

## 3. DB 스키마

기존 LangFuse PostgreSQL Flexible Server에 `pgvector` extension 추가.
별도 서비스 불필요.

```sql
-- pgvector extension (최초 1회)
CREATE EXTENSION IF NOT EXISTS vector;

-- 인덱싱 테이블
CREATE TABLE incident_embeddings (
    id              SERIAL PRIMARY KEY,
    incident_id     TEXT NOT NULL UNIQUE,          -- AgentState.incident_id
    pipeline        TEXT NOT NULL,                 -- AgentState.pipeline
    triage_summary  TEXT NOT NULL,                 -- 검색 결과 표시용 원문
    embedding       vector(1536),                  -- text-embedding-3-small
    action_taken    TEXT NOT NULL,                 -- backfill_silver | retry_pipeline | skip_and_report
    final_status    TEXT NOT NULL,                 -- resolved | failed | escalated
    detected_at     TIMESTAMPTZ NOT NULL,          -- AgentState.detected_at
    indexed_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 벡터 유사도 검색 인덱스
-- lists 값은 데이터 규모에 따라 조정 (아래 확장 계획 참조)
CREATE INDEX ON incident_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);
```

**마이그레이션 파일**: `migrations/001_incident_embeddings.sql`

**pgvector ivfflat 확장 계획**:

| 누적 incident 수 | lists 값 | 재인덱싱 절차 |
|-----------------|---------|-------------|
| 0 ~ 1,000건 | `10` (초기값) | — |
| 1,000 ~ 10,000건 | `50` | DDL 재실행 |
| 10,000건+ | `100` | DDL 재실행 |

재인덱싱 시 다운타임 없이 수행 가능 (PostgreSQL `CREATE INDEX CONCURRENTLY`):
```sql
DROP INDEX incident_embeddings_embedding_idx;
CREATE INDEX CONCURRENTLY ON incident_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);
```

dev 환경에서는 `pgvector/pgvector:pg16` Docker 이미지로 대체 가능:
```bash
docker run -e POSTGRES_PASSWORD=dev -p 5432:5432 pgvector/pgvector:pg16
```

---

## 4. 컴포넌트 명세

### 4.1 AzureEmbeddingClient

**파일**: `src/agent/rag/embedding.py`

| 항목 | 값 |
|------|---|
| 모델 | `text-embedding-3-small` |
| 차원 | 1536 |
| API | 기존 Azure OpenAI endpoint 재사용 (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`) |
| 일일 한도 영향 | 없음 — chat completions 한도(`LLM_DAILY_CAP`, 기본 30회/day)와 별도 쿼터 |
| 비용 | $0.00002 / 1K tokens (월 100건 incident 기준 $0.01 미만) |

```python
class AzureEmbeddingClient:
    MODEL = "text-embedding-3-small"

    def embed(self, text: str) -> list[float]:
        """
        단일 텍스트 임베딩.
        실패 시 EmbeddingError 발생.
        재시도: 429/timeout → 최대 3회 exponential backoff.
        """
```

**환경변수** (기존 변수 재사용):
```yaml
AZURE_OPENAI_ENDPOINT:     기존 LLM과 동일
AZURE_OPENAI_API_KEY:      기존 LLM과 동일
AZURE_EMBEDDING_DEPLOYMENT: text-embedding-3-small 배포명
```

### 4.2 IncidentStore

**파일**: `src/agent/rag/incident_store.py`

```python
class IncidentStore:
    def insert(self, record: IncidentRecord) -> None:
        """
        incident_id UNIQUE 제약으로 중복 삽입 방지 (멱등).
        ON CONFLICT DO NOTHING 사용.
        """

    def search_similar(
        self,
        pipeline: str,
        query_embedding: list[float],
        k: int = 3,
        min_cosine_similarity: float = 0.70,
    ) -> list[SimilarIncident]:
        """
        동일 pipeline 내에서 cosine 유사도 기준 Top-k 조회.
        min_cosine_similarity 미달 결과는 제외 (무관한 사례 주입 방지).

        임계값 0.70 선정 근거:
        - 도메인 특화 영어 요약은 어휘 변이가 있어 0.75는 과도하게 엄격
        - 0.70 (≈46도) = 관련성 높음 수준, 이질적 사건 차단 가능
        - 모니터링: 월별 검색 성공률 추적
          * 성공률 < 30% → 0.65로 완화
          * 성공률 > 80% → 0.75로 강화
        """
```

pgvector SQL 패턴:
```sql
SELECT incident_id, pipeline, triage_summary, action_taken, final_status,
       detected_at, 1 - (embedding <=> %s::vector) AS similarity
FROM incident_embeddings
WHERE pipeline = %s
  AND 1 - (embedding <=> %s::vector) >= %s
ORDER BY embedding <=> %s::vector
LIMIT %s;
```

### 4.3 IncidentRetriever

**파일**: `src/agent/rag/retriever.py`

```python
class IncidentRetriever:
    def retrieve_for_triage(self, state: AgentState) -> str:
        """
        triage 프롬프트에 주입할 유사 사건 컨텍스트 문자열 반환.
        - degraded mode(LLM 일일 한도 초과)이면 즉시 빈 문자열 반환 (embedding 호출 스킵)
          판단 기준: get_llm_call_count() >= LLM_DAILY_CAP
        - 유사 사건 없으면 빈 문자열 반환 (graceful degradation)
        - 임베딩 실패 시 WARNING 로그 + 빈 문자열 반환 (triage 차단 안 함)
        - 출력 토큰 예산: 600 토큰 이하로 강제 절단 (k=3→2→1→"" fallback)
        """
```

쿼리 텍스트 구성 (embed 입력):
```
{pipeline} | dq: {dq_analysis 앞 200자} | exceptions: {exception_type 목록} | dq_tags: {dq_tag 목록}
```

**토큰 예산 초과 시 k 감소 전략**:
```python
def _format_for_prompt(incidents: list[SimilarIncident], max_chars: int = 2400) -> str:
    # 2,400자 ≈ 600 토큰 (영어 기준 4자/토큰)
    for k in [3, 2, 1]:
        text = _render_incidents(incidents[:k])
        if len(text) <= max_chars:
            return text
    return ""  # k=1도 초과하면 컨텍스트 없이 진행
```

### 4.4 IncidentIndexer

**파일**: `src/agent/rag/indexer.py`

```python
class IncidentIndexer:
    def index_resolved_incident(self, state: AgentState) -> None:
        """
        postmortem 노드 완료 후 호출.
        - final_status != "resolved" 이면 즉시 반환 (실패/에스컬레이션 사례 제외)
        - postmortem_report is None 이면 즉시 반환 + WARNING 로그
          (postmortem LLM 실패 시 final_status는 "resolved"로 유지되므로 별도 체크 필요)
        - 임베딩 또는 DB 실패 시 WARNING 로그만, 예외 전파 안 함
        - incident_id UNIQUE 제약으로 중복 인덱싱 자동 방지
        - 이 LLM 호출은 LLM_DAILY_CAP에서 분리된 별도 쿼터로 계산
        """
```

**AgentState → IncidentRecord 필드 매핑**:

| IncidentRecord 필드 | AgentState 소스 | 비고 |
|--------------------|-----------------|----|
| `incident_id` | `state["incident_id"]` | |
| `pipeline` | `state["pipeline"]` | |
| `triage_summary` | LLM 생성 영어 요약 | 아래 LLM 프롬프트 참조 |
| `action_taken` | `state["action_plan"]["action"]` | 운영자가 승인한 최종 조치 |
| `final_status` | `state["final_status"]` | `"resolved"` 고정 |
| `detected_at` | `state["detected_at"]` | UTC ISO8601 → TIMESTAMPTZ |

**triage_report 필드 참조** (ai_agent_spec.md TriageReport 스키마 기준):

| 사용 필드 | 접근 경로 | 없을 경우 fallback |
|----------|----------|-------------------|
| 장애 요약 | `triage_report["summary"]` | `triage_report.get("incident_summary", "")` |
| 근본 원인 | `triage_report["root_causes"]` | `[]` |
| 영향 범위 | `triage_report.get("impact", "")` | `""` |

**영어 요약 생성 LLM 프롬프트**:
```
You are summarizing a pipeline incident for future reference.
Write a concise English summary (max 120 words) covering:
- Root cause and affected tables/fields
- Key violation statistics (type, count, percentage)
- Action taken and outcome
- One-line key insight for similar future incidents

Input:
Pipeline: {pipeline}
Summary: {triage_report[summary]}
Root causes: {triage_report[root_causes]}
Action: {action_plan[action]} (params: {action_plan[parameters]})
Outcome: {final_status}
```

### 4.5 데이터 클래스

**파일**: `src/agent/rag/schema.py`

```python
@dataclass(frozen=True)
class IncidentRecord:
    incident_id:    str
    pipeline:       str
    triage_summary: str
    embedding:      list[float]
    action_taken:   str
    final_status:   str
    detected_at:    datetime

@dataclass(frozen=True)
class SimilarIncident:
    incident_id:   str
    pipeline:      str
    triage_summary: str
    action_taken:  str
    final_status:  str
    detected_at:   datetime
    similarity:    float        # 0.0~1.0
```

---

## 5. 인프라 요건

| 항목 | 현재 | 변경 |
|------|------|------|
| 서버 | LangFuse PostgreSQL Flexible Server (B1ms) | 변경 없음 |
| DB extension | 없음 | `pgvector` 활성화 (DDL 1줄) |
| Azure OpenAI | gpt-4o deployment 존재 | `text-embedding-3-small` deployment 추가 |
| Python 의존성 | - | `pgvector>=0.2.0`, `psycopg2-binary>=2.9` |

Azure Database for PostgreSQL Flexible Server는 `pgvector`를 공식 extension으로 지원.
별도 승인 절차 없이 `CREATE EXTENSION` 실행으로 활성화 가능.

---

## 6. 제약 및 Graceful Degradation

### 6.1 Cold Start

초기 incident 0건 — `search_similar`가 빈 리스트 반환.
`retrieve_for_triage`는 빈 문자열 반환, triage 프롬프트에서 유사 사건 섹션 생략.
triage 동작에 영향 없음.

### 6.2 임베딩 실패

`AzureEmbeddingClient.embed`가 3회 재시도 후 `EmbeddingError` 발생 시:
- **retriever**: WARNING 로그 + 빈 문자열 반환 (triage 계속 진행)
- **indexer**: WARNING 로그 + 반환 (postmortem final_status 변경 없음)

### 6.3 유사도 임계값

`min_cosine_similarity = 0.70` (기본값).
임계값 미달 결과는 "유사하지 않음"으로 판단하고 제외.
파이프라인이 다른 사건은 `WHERE pipeline = %s` 조건으로 사전 필터링.

**월별 모니터링 지표**:

| 지표 | 목표 | 조정 |
|------|------|------|
| 검색 성공률 (retrieved / total triage) | 6개월 후 > 60% | < 30% → 0.65로 완화 / > 80% → 0.75로 강화 |
| Top-1 recall (인간 평가) | > 0.80 | 낮으면 embedding 모델 재검토 |

### 6.4 토큰 예산 초과 방지

출력 문자열이 **600 토큰(≈2,400자)** 을 초과하면 k를 줄여 fallback:

```
k=3 → k=2 → k=1 → "" (빈 문자열, triage는 컨텍스트 없이 진행)
```

각 요약이 LLM 프롬프트로 ~150 토큰에 생성되므로 k=3 기준 450 토큰 — 예산 600 이내.
요약이 예외적으로 길 경우에만 k 감소 발동.

### 6.5 LLM 일일 한도 영향 없음

text-embedding-3-small API는 chat completions 일일 한도(`LLM_DAILY_CAP`, 기본 30회/day)와 **별도 쿼터**.
degraded mode 진입 조건에 포함되지 않음.

---

## 7. 구현 파일 경로

```
src/agent/rag/
  __init__.py
  schema.py             # IncidentRecord, SimilarIncident
  embedding.py          # AzureEmbeddingClient
  incident_store.py     # IncidentStore (pgvector CRUD)
  retriever.py          # IncidentRetriever
  indexer.py            # IncidentIndexer

migrations/
  001_incident_embeddings.sql

tests/unit/rag/
  test_embedding.py
  test_incident_store.py
  test_retriever.py
  test_indexer.py

tests/integration/rag/
  test_store_integration.py   # Docker pgvector 필요
```

**triage 노드 연동 지점** (triage.py 구현 시):
```python
# triage 노드 구현 시 다음 패턴으로 IncidentRetriever 호출
similar_context = retriever.retrieve_for_triage(state)  # "" or ≤600-token string
# similar_context가 있을 때만 triage 프롬프트에 "Similar Past Incidents" 섹션 추가
```

**postmortem 노드 연동 지점** (postmortem.py 구현 시):
```python
# postmortem 노드 완료 직후 (postmortem_report 생성 후)
# 조건: final_status == "resolved" AND postmortem_report is not None
indexer.index_resolved_incident(state)  # 실패해도 예외 전파 안 함
```
