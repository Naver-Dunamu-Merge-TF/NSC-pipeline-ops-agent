# Runtime Config

## 환경별 런타임 설정 매트릭스

### 실행 모드 정책 (고정)

- dev: `dry-run` (고정)
- staging: `dry-run` (고정)
- prod: `live`

`agent-execute-mode`는 위 실행 모드 정책을 저장/주입하는 값이며, 환경별 허용값은 이 문서 정책(`dev/staging=dry-run`, `prod=live`)으로 고정한다.

### Key Vault 시크릿 매트릭스

| 항목 | Key Vault 키 | dev | staging | prod |
|------|--------------|-----|---------|------|
| Databricks API 호스트 | `databricks-host` | dev workspace host | staging workspace host | prod workspace host |
| Databricks API 토큰 | `databricks-agent-token` | 개인 PAT | 서비스 계정 토큰 | 서비스 계정 토큰 |
| Azure OpenAI API 키 | `azure-openai-api-key` | dev 배포 키 | staging 배포 키 | prod 배포 키 |
| Azure OpenAI 엔드포인트 | `azure-openai-endpoint` | dev 리전 엔드포인트 | staging 리전 엔드포인트 | prod 리전 엔드포인트 |
| Azure OpenAI 배포명 | `azure-openai-deployment` | `gpt-5.2-dev` | `gpt-5.2-staging` | `gpt-5.2` |
| LangFuse 공개키 | `langfuse-public-key` | dev 키 | staging 키 | prod 키 |
| LangFuse 비밀키 | `langfuse-secret-key` | dev 키 | staging 키 | prod 키 |
| Log Analytics DCR ID | `log-analytics-dcr-id` | dev DCR | staging DCR | prod DCR |
| 실행 모드 | `agent-execute-mode` | `dry-run` (고정) | `dry-run` (고정) | `live` |

### 환경변수 매트릭스

키 이름 검증 기준(DoD3: "환경변수 키 이름 검증")은 `src/orchestrator/utils/config.py`의 `load_runtime_settings` 구현이며,
필수 키는 `("TARGET_PIPELINES", "LANGFUSE_HOST")`, 선택 키는 `CHECKPOINT_DB_PATH`, `LLM_DAILY_CAP`이다.
환경변수 매트릭스 SSOT는 위 `load_runtime_settings` 코드 경로이며, 키 추가/변경 시 코드-문서-`tests/unit/test_runtime_config.py`를 같은 변경에서 함께 갱신한다.
문서/이슈에서 해당 검증 경로를 다시 인용할 때는 `git ls-files src/orchestrator/utils/config.py` 확인을 체크포인트로 사용한다.

`src/orchestrator/utils/config.py` 기준으로 런타임에서 실제 로딩/검증되는 환경변수는 아래 4개다.

| 환경변수 | 코드 키명 (config.py) | 필수 여부 | dev | staging | prod |
|---------|------------------------|-----------|-----|---------|------|
| `TARGET_PIPELINES` | `TARGET_PIPELINES` | 필수 | `pipeline_silver` | `pipeline_silver,pipeline_b,pipeline_c,pipeline_a` | `pipeline_silver,pipeline_b,pipeline_c,pipeline_a` |
| `LANGFUSE_HOST` | `LANGFUSE_HOST` | 필수 | `http://localhost:3000` | `https://langfuse.internal.nsc.com` | `https://langfuse.internal.nsc.com` |
| `CHECKPOINT_DB_PATH` | `CHECKPOINT_DB_PATH` | 선택 (미지정 시 기본값) | `checkpoints/agent.db` | `/Volumes/nsc_dbw_dev_7405610275478542/default/agent_state_checkpoints/agent.db` | `/Volumes/nsc_dbw_dev_7405610275478542/default/agent_state_checkpoints/agent.db` |
| `LLM_DAILY_CAP` | `LLM_DAILY_CAP` | 선택 (미지정 시 `30`) | `30` (기본, 필요 시 override) | `30` (기본, 필요 시 override) | `30` (기본, 운영에서 조정) |

ADR-260225-1012 경계 정책:

- Databricks(prod/staging/serverless strict policy) 운영 기본 경로는 `CHECKPOINT_DB_PATH=/Volumes/nsc_dbw_dev_7405610275478542/default/agent_state_checkpoints/agent.db`로 고정한다. 로컬 개발 기본값은 `checkpoints/agent.db`를 유지한다.
- 경로의 `nsc_dbw_dev_7405610275478542` 토큰은 현재 배포 워크스페이스의 Unity Catalog 식별자이며, 본 범위에서는 serverless 체크포인터 경로 식별자로 의도적으로 사용한다.
- 체크포인터 엔진은 기존과 동일하게 SQLite(`SqliteSaver`)를 유지하며, 이번 변경은 경로 정책 전환만 다룬다.
- `CHECKPOINT_DB_PATH` 검증 증거는 `pragmatic`(Databricks auth/DBFS API)와 `strict`(런타임 `/Volumes/.../agent.db` 경로로 AgentRunner 1회 성공 실행)로 분리 기록한다.
- `databricks fs ls dbfs:/mnt/agent-state/checkpoints`는 과거 DBFS 경로 접근성 확인용 배경 증거로만 보관하며 strict smoke 완료 근거로 사용하지 않는다.

### DEV-012 fingerprint smoke 입력 경로 정책 (ADR-0027)

`tests/smoke/test_incident_fingerprint_smoke.py`의 실행 입력은 아래 규칙으로 고정한다.

- 기본 입력: `tests/fixtures/runtime_inputs/<DEV012_SMOKE_ENV>_incident_input.json`
- `DEV012_SMOKE_ENV` 기본값: `dev` (허용값: `dev`, `staging`)
- 선택 override: `DEV012_RUNTIME_INPUT_PATH` 설정 시 해당 절대/상대 경로를 우선 사용
- 실행 게이트: `RUN_DEV012_FINGERPRINT_SMOKE=1`일 때만 smoke 수행(기본은 skip)

이 정책은 운영 runbook(`docs/runbooks/ai-agent-infra-dev.md`)의 "DEV-012 fingerprint smoke execution policy (ADR-0027)" 절차와 동일해야 하며, 변경 시 테스트/문서를 같은 변경에서 함께 갱신한다.

## Databricks Job ID 설정 위치

Databricks 실행기가 파이프라인별 올바른 Job을 호출하려면 `config/databricks_jobs.yaml`에 Job ID를 설정한다.

- 키 구조: `jobs.<pipeline>.<action>`
- 현재 필수 파이프라인: `pipeline_silver`, `pipeline_b`, `pipeline_c`, `pipeline_a`
- 현재 필수 액션: `refresh`
- 값 타입: 정수(`int`) Job ID만 허용

운영 환경 변경 시에는 코드 수정 없이 `config/databricks_jobs.yaml`의 Job ID만 갱신한다.

## 경로 참조 운영 체크리스트 (활성/역사 분리)

ADR-0017에 따라 경로 정규화/교정 점검은 아래 2개 절차로 분리한다.

### 1) 활성 문서 점검 절차 (`.roadmap/`, `.specs/`)

- 목적: 다음 구현 입력으로 쓰이는 문서의 경로 참조를 실제 코드 경로와 정렬한다.
- 적용 원칙: 불일치가 있으면 해당 문서를 수정한다.

템플릿:

```markdown
- [ ] 점검 범위: `.roadmap/**/*.md`, `.specs/**/*.md`
- [ ] 경로 실존 확인: `git ls-files <path>`
- [ ] 불일치 교정 반영: 활성 문서 본문 업데이트
- [ ] 교정 근거 기록: 관련 ADR/이슈 링크 첨부
```

재현 명령:

```bash
grep -nE '`utils/config\.py`|`utils/secrets\.py`' .roadmap/*.md .specs/*.md | grep -v ".specs/runtime_config.md"
```

### 2) 역사 기록 점검 절차 (`docs/adr/*`, `.sudocode/*`)

- 목적: 과거 경로 잔여를 수정하지 않고 file+line 인덱스로 추적한다.
- 적용 원칙: 본문 재작성 금지, 인덱스 문서만 갱신한다.

템플릿:

```markdown
- [ ] 점검 범위: `docs/adr/*.md`, `.sudocode/*.jsonl`
- [ ] 잔여 인덱스 갱신: 파일 경로 + 라인 번호를 ADR-0017 인덱스에 반영
- [ ] 본문 불변성 확인: 역사 기록 파일 본문은 수정하지 않음
- [ ] 재현 명령 결과 첨부: grep 출력으로 검증
```

재현 명령:

```bash
grep -nE '`utils/config\.py`|`utils/secrets\.py`' docs/adr/*.md | grep -v "docs/adr/0017-limit-path-normalization-to-active-sources.md"
grep -nE '`utils/config\.py`|`utils/secrets\.py`' .sudocode/*.jsonl
```
