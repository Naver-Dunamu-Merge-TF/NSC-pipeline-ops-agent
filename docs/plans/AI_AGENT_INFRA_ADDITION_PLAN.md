# NSC AI Agent 인프라 추가 계획서
# 버전: v03
# 기준 문서: `Infra_Manual.md`, `TEAM_CREDENTIALS.md`, `.specs/ai_agent_spec.md`
# 작성일: 2026-02-24

> **목적**: NSC 파이프라인 장애 대응 AI Agent 운영에 필요한 클라우드 리소스를 기존 아키텍처 원칙(Private Endpoint 중심, 레이어 분리, 최소 Public 노출)에 맞춰 추가한다.
> **환경**: dev
> **Resource Group**: `2dt-final-team4`

---

## 1. 개요

본 계획서는 기존 인프라(데이터/보안/분석 레이어) 위에 AI Agent 운영에 필요한 리소스를 **최소 변경**으로 추가하기 위한 실행 기준이다.

- 기존 리소스는 최대한 재사용한다.
- 신규 리소스는 Private Endpoint + Private DNS 기준으로 연결한다.
- 자격증명(비밀번호, 토큰)은 문서에 평문 기록하지 않고 Key Vault로 관리한다.

---

## 2. 현재 상태 요약 (기준선)

현재 dev 환경에는 아래 기반 리소스가 이미 존재한다.

| 구분 | 상태 |
|:---|:---|
| AKS / Databricks / Key Vault / Log Analytics | 구성됨 |
| 기존 PostgreSQL (`nsc-pg-dev`) | 구성됨 |
| 주요 Private Endpoint (SQL, PostgreSQL, Key Vault, ACR, Event Hubs, ADLS) | 구성됨 |
| `privatelink.postgres.database.azure.com` | 구성됨 |
| `privatelink.openai.azure.com` | 미구성 |
| Azure OpenAI Private Endpoint | 미구성 |
| LangFuse 전용 PostgreSQL 분리 구성 | 미구성 |
| LangFuse AKS 내부 서비스 배포 | 미구성 |
| Azure Monitor Alert Rule / Action Group (Agent 이벤트용) | 미구성 |

---

## 3. 추가 필요 항목

### 3.1 리소스

| 항목 | 필요 여부 | 설명 |
|:---|:---:|:---|
| Azure OpenAI 계정 (기존 재사용 또는 신규) | Must | AI Agent의 analyze/triage/postmortem 호출 대상 |
| LangFuse 애플리케이션 배포 (AKS 내부 Service) | Must | Self-Hosted trace 조회/수집 서비스 |
| LangFuse 전용 PostgreSQL Flexible Server | Must | 기존 업무 DB와 분리된 trace 메타데이터 저장소 |
| Azure Monitor Alert Rule / Action Group | Must | 승인/타임아웃/실패 알림 체계 |

### 3.2 엔드포인트

| 항목 | 필요 여부 | 설명 |
|:---|:---:|:---|
| Azure OpenAI용 Private Endpoint | Must | OpenAI 접근을 내부망으로 고정 |
| LangFuse 전용 PostgreSQL용 Private Endpoint | Must | LangFuse DB 접근을 내부망으로 고정 |

### 3.3 DNS

| 항목 | 필요 여부 | 설명 |
|:---|:---:|:---|
| `privatelink.openai.azure.com` Private DNS Zone | Must | OpenAI Private Endpoint 내부 이름 해석 |
| `privatelink.postgres.database.azure.com` 레코드 연결 (기존 Zone 재사용) | Must | LangFuse 전용 PostgreSQL Private Endpoint 내부 이름 해석 |

### 3.4 부대 설정

| 항목 | 필요 여부 | 설명 |
|:---|:---:|:---|
| 두 Private DNS Zone의 VNet Link 구성 | Must | `nsc-vnet-dev` 내부 이름 해석 일관성 확보 |
| OpenAI/PostgreSQL 접근 정책 private-only 고정 | Must | Public 접근 차단 원칙 유지 |
| Databricks/AKS -> OpenAI/PG 경로 네트워크 정책 반영 | Must | 실제 런타임 통신 가능 상태 보장 |
| ACR 이미지 경로 및 AKS 배포 연계 | Must | LangFuse 워크로드를 내부 서비스로 운영 |
| Agent 이벤트용 Alert Rule + Action Group 구성 | Must | `TRIAGE_READY`/`APPROVAL_TIMEOUT`/`EXECUTION_FAILED` 등 운영 알림 |
| Key Vault 시크릿 운영(값 등록/권한) | Must | 애플리케이션/잡의 런타임 설정 주입 |

### 3.5 Key Vault 필수 키

| 키 이름 | 구분 | 비고 |
|:---|:---|:---|
| `azure-openai-api-key` | 필수 | OpenAI 인증 키 |
| `azure-openai-endpoint` | 필수 | OpenAI 엔드포인트 |
| `azure-openai-deployment` | 필수 | OpenAI 배포명 |
| `langfuse-public-key` | 필수 | LangFuse SDK 인증 |
| `langfuse-secret-key` | 필수 | LangFuse SDK 인증 |
| `log-analytics-dcr-id` | 필수 | Agent 이벤트 로그 전송 |
| `agent-execute-mode` | 필수 | dev/staging `dry-run`, prod `live` 정책 |
| `databricks-agent-token` | 기존/필수 | Databricks Jobs API 연동 |

### 3.6 리소스 이름 (팀 공유용)

| 구분 | 이름 | 비고 |
|:---|:---|:---|
| Azure OpenAI | `nsc-aoai-dev` | OpenAI 계정 |
| PostgreSQL (LangFuse 전용) | `nsc-pg-langfuse-dev` | Flexible Server |
| Private Endpoint (OpenAI) | `nsc-pe-openai` | OpenAI private-only 경로 |
| Private Endpoint (LangFuse PG) | `nsc-pe-pg-langfuse` | LangFuse DB private-only 경로 |
| Private DNS Zone (OpenAI) | `privatelink.openai.azure.com` | 신규 |
| Private DNS Zone (PostgreSQL) | `privatelink.postgres.database.azure.com` | 기존 Zone 재사용 |
| Action Group | `nsc-ag-agent-dev` | Agent 이벤트 공통 알림 |
| Alert Rule | `nsc-alert-triage-ready-dev` | `TRIAGE_READY` |
| Alert Rule | `nsc-alert-approval-timeout-dev` | `APPROVAL_TIMEOUT` |
| Alert Rule | `nsc-alert-execution-failed-dev` | `EXECUTION_FAILED` |
| AKS Deployment | `langfuse` | 내부 trace 서비스 |
| AKS Service | `langfuse-internal` | `ClusterIP` |

> 위 이름은 dev 기준 실행안이며, 인프라팀 네이밍 규칙 충돌 시 접두/접미만 조정한다.

---

## 4. 레이어 배치 원칙

OpenAI Private Endpoint 배치는 아래 원칙으로 결정한다.

| 후보 레이어 | 판정 | 이유 |
|:---|:---:|:---|
| Application 레이어 | 비권장 | 앱 워크로드와 외부 PaaS 진입점이 과결합됨 |
| Databricks/Analytics 레이어 | 비권장 | 분석 워크로드 종속성이 커지고 확장 시 예외가 늘어남 |
| Data 레이어 | 권장(조건부) | 기존 Private Endpoint 패턴과 정합, 변경 범위 최소 |

**결론**: 신규 OpenAI Private Endpoint는 **Data 레이어 운영 패턴**에 맞춰 추가한다.

---

## 5. 실행 단계 (Phase Plan)

### Phase 1 - 기반 리소스 확정

- Azure OpenAI 계정 경로 확정 (재사용 또는 신규)
- LangFuse 전용 PostgreSQL Flexible Server 생성
- Alert Rule / Action Group 기준 이벤트 세트 확정

### Phase 2 - Private 연결 구성

- OpenAI / LangFuse PostgreSQL Private Endpoint 생성
- Private DNS Zone 및 VNet Link 구성
- `privatelink.postgres.database.azure.com` 기존 Zone에 LangFuse PG 레코드 연결

### Phase 3 - 애플리케이션/알림 연계

- ACR 이미지 경로 준비 및 LangFuse AKS 내부 서비스 배포
- Key Vault 시크릿/권한 반영
- Alert Rule / Action Group 생성 및 이벤트 연결

### Phase 4 - 운영 검증

- 내부 DNS 해석 확인
- OpenAI 호출 및 LangFuse DB 연결 스모크 테스트
- LangFuse trace 저장/조회 스모크 테스트
- 알림 이벤트 스모크 테스트 (`TRIAGE_READY`, `APPROVAL_TIMEOUT`, `EXECUTION_FAILED`)
- 공인망 우회 없이 private 경로로만 통신되는지 확인

---

## 6. 완료 기준 (Definition of Done)

- [ ] OpenAI 계정/경로가 dev 환경에서 확정되어 있다.
- [ ] OpenAI Private Endpoint가 생성되고 내부 DNS로 해석된다.
- [ ] LangFuse 전용 PostgreSQL Flexible Server가 생성되어 기존 업무 DB와 분리되어 있다.
- [ ] LangFuse 전용 PostgreSQL Private Endpoint가 생성되고 내부 DNS로 해석된다.
- [ ] LangFuse가 AKS 내부 서비스(외부 노출 없음)로 배포된다.
- [ ] Databricks/AKS에서 OpenAI 및 LangFuse DB로 내부 통신 스모크가 성공한다.
- [ ] LangFuse trace 저장/조회 스모크가 성공한다.
- [ ] Alert Rule / Action Group이 구성되고 핵심 이벤트 알림 스모크가 성공한다.
- [ ] Key Vault 필수 키(`azure-openai-*`, `langfuse-*`, `log-analytics-dcr-id`, `agent-execute-mode`, `databricks-agent-token`) 존재가 확인된다.
- [ ] 관련 시크릿이 Key Vault로 관리되며 평문 자격증명 문서화가 없다.

---

## 7. 운영 문서 반영 항목

인프라 적용 후 아래 문서를 동일 형식으로 갱신한다.

| 문서 | 반영 항목 |
|:---|:---|
| `Infra_Manual.md` | 4.3(Private Endpoint 매핑), 6.6(알림 흐름), 7.2(네트워크 설정), 7.3(보안 설정) 갱신 |
| `TEAM_CREDENTIALS.md` | OpenAI/LangFuse 연결 정보는 값 대신 Key Vault 참조 키 이름 기준으로 기재 |

---

## 8. 태스크 겹침 분석 (Sudocode 이슈 대조)

본 계획은 인프라 선행 작업 중심 문서이지만, 아래 이슈의 DoD와 **직접 또는 부분 겹침**이 있다.

### 8.1 직접 겹침 (핵심)

| 이슈 | 겹침 수준 | 겹치는 계획 항목 | 비고 |
|:---|:---:|:---|:---|
| `DEV-043` (`i-63cv`) | 높음(부분) | LangFuse AKS 내부 서비스, ACR 연계 | UI 스모크/롤백 절차는 별도 증빙 필요 |
| `DEV-044` (`i-2y1l`) | 높음(부분) | LangFuse 전용 PostgreSQL + PE + Key Vault 연계 | DB 마이그레이션/재기동 보존 증빙 필요 |
| `DEV-045` (`i-7zqb`) | 중간~높음(부분) | OpenAI/PG PE, Private DNS, 네트워크 정책 반영 | NSG 정합성/롤백 플랜 명시 강화 필요 |
| `DEV-047` (`i-34cy`) | 중간(선행 기반) | trace/알림 스모크, 운영 검증 | heartbeat/타임아웃/eval/runbook까지는 별도 범위 |

### 8.2 간접 연계 (선행 의존)

| 이슈 | 연계 이유 |
|:---|:---|
| `DEV-040` (`i-2nua`) | LangFuse 콜백/trace 수집은 인프라 준비(043~045) 전제 |
| `DEV-046` (`i-3jp5`) | Databricks Job 배포 스펙과 알림/heartbeat 연결이 맞물림 |
| `DEV-005` (`i-32vd`), `DEV-006` (`i-7eux`) | Key Vault 키/환경 매트릭스 정합성이 필수 |
| `DEV-027` (`i-3yss`) | Log Analytics 이벤트 전송과 Alert Rule/Action Group 연계 |
| `DEV-023` (`i-9s8w`) | OpenAI endpoint/key 주입이 클라이언트 가드레일 동작 전제 |

### 8.3 상태 해석 가이드

- 본 계획 실행만으로 상기 이슈를 자동 `closed` 처리하지 않는다.
- 기본 해석은 **"인프라 선행 충족 -> 이슈 `in_progress` 전환 근거"**로 사용한다.
- 각 이슈 DoD의 코드/테스트/staging 스모크 증빙이 확보될 때 최종 완료를 판단한다.
- `OPS: INFRA-READY 게이트` 상태(`i-875b`)가 닫혀 있으면, 겹침 이슈도 `open` 전환 없이 `blocked` 유지 정책을 따른다.

---

## 9. 보안 메모

- `TEAM_CREDENTIALS.md`에는 실제 비밀번호/토큰을 직접 기록하지 않는다.
- 시크릿 값은 Key Vault 저장을 원칙으로 하고, 문서에는 키 이름과 참조 방법만 기록한다.
- 기존 평문 자격증명(예: DB 비밀번호, PAT)은 문서에서 제거 후 즉시 회전한다.
- AKS/Databricks/CI의 시크릿 접근 권한은 RBAC 최소권한으로 분리한다.
