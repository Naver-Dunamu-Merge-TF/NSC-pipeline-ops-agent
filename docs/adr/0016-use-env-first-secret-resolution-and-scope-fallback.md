# ADR-0016: Use env-first secret resolution and scope fallback

## Created At

2026-02-24 19:26 KST

## Status

PendingReview

## Context

`get_secret` 호출 경로는 로컬 개발, 테스트, Databricks 런타임을 모두 지원해야 하며, 동일한 코드 경로에서 시크릿 조회 우선순위와 scope 선택 기준이 일관되지 않으면 운영 환경과 비운영 환경 간 동작 차이로 인해 재현성 저하와 장애 분석 비용 증가가 발생한다.

특히 Key Vault 키를 환경변수 스텁으로 주입하는 관례가 명시되지 않으면 팀별로 임의 네이밍을 사용하게 되어 조회 실패가 잦아지고, Databricks secret scope 선택 규칙이 고정되지 않으면 배포 설정 변경 시 의도하지 않은 scope를 참조할 위험이 있다.

관련 제약과 계약 기준은 `.specs/ai_agent_spec.md`의 시크릿 해석 및 실행 환경 설정 규칙을 따른다.

## Decision

`get_secret`의 기본 조회 순서를 env stub 우선 후 Databricks scope 조회로 고정하고, env stub 키는 Key Vault key를 `SECRET_<정규화된 대문자 키>`로 매핑하며, scope 환경변수는 `DATABRICKS_SECRET_SCOPE`를 우선 사용하고 없으면 `KEY_VAULT_SECRET_SCOPE`로 폴백하도록 결정한다.

## Rationale

대안 1은 Databricks scope를 먼저 조회하고 env stub을 보조 수단으로 두는 방식이었지만, 로컬/테스트에서 Databricks 의존성이 불필요하게 커지고 빠른 검증 루프가 깨지므로 기각했다.

대안 2는 env stub 네이밍을 자유 형식으로 허용하는 방식이었지만, 키 정규화 규칙이 없으면 동일 시크릿에 대한 다중 별칭이 생겨 운영 일관성과 디버깅 가능성이 낮아지므로 기각했다.

대안 3은 scope 환경변수를 단일 키만 허용하는 방식이었지만, 기존 배포 설정과의 호환성을 즉시 훼손할 수 있어 전환 비용이 커지므로 `DATABRICKS_SECRET_SCOPE` 우선 + `KEY_VAULT_SECRET_SCOPE` 폴백 전략을 채택했다.

최종 선택은 비운영 환경에서의 민첩한 검증성과 운영 환경에서의 기존 구성 호환성을 동시에 확보하는 절충안이며, 조회 순서와 키/스코프 규약을 명시적으로 고정해 동작 예측 가능성을 높인다.
