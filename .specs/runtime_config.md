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
| Databricks API 토큰 | `databricks-agent-token` | 개인 PAT | 서비스 계정 토큰 | 서비스 계정 토큰 |
| Azure OpenAI API 키 | `azure-openai-api-key` | dev 배포 키 | staging 배포 키 | prod 배포 키 |
| Azure OpenAI 엔드포인트 | `azure-openai-endpoint` | dev 리전 엔드포인트 | staging 리전 엔드포인트 | prod 리전 엔드포인트 |
| Azure OpenAI 배포명 | `azure-openai-deployment` | `gpt-4o-dev` | `gpt-4o-staging` | `gpt-4o` |
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
| `CHECKPOINT_DB_PATH` | `CHECKPOINT_DB_PATH` | 선택 (미지정 시 기본값) | `checkpoints/agent.db` | `/dbfs/mnt/agent-state/checkpoints/agent.db` | `/dbfs/mnt/agent-state/checkpoints/agent.db` |
| `LLM_DAILY_CAP` | `LLM_DAILY_CAP` | 선택 (미지정 시 `30`) | `30` (기본, 필요 시 override) | `30` (기본, 필요 시 override) | `30` (기본, 운영에서 조정) |

## Databricks Job ID 설정 위치

Databricks 실행기가 파이프라인별 올바른 Job을 호출하려면 `config/databricks_jobs.yaml`에 Job ID를 설정한다.

- 키 구조: `jobs.<pipeline>.<action>`
- 현재 필수 파이프라인: `pipeline_silver`, `pipeline_b`, `pipeline_c`, `pipeline_a`
- 현재 필수 액션: `refresh`
- 값 타입: 정수(`int`) Job ID만 허용

운영 환경 변경 시에는 코드 수정 없이 `config/databricks_jobs.yaml`의 Job ID만 갱신한다.
