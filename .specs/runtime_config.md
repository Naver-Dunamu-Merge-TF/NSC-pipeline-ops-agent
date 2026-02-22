# Runtime Config

## Databricks Job ID 설정 위치

Databricks 실행기가 파이프라인별 올바른 Job을 호출하려면 `config/databricks_jobs.yaml`에 Job ID를 설정한다.

- 키 구조: `jobs.<pipeline>.<action>`
- 현재 필수 파이프라인: `pipeline_silver`, `pipeline_b`, `pipeline_c`, `pipeline_a`
- 현재 필수 액션: `refresh`
- 값 타입: 정수(`int`) Job ID만 허용

운영 환경 변경 시에는 코드 수정 없이 `config/databricks_jobs.yaml`의 Job ID만 갱신한다.
