# ADR-260225-1012: accept-pragmatic-infra-smoke-evidence

## Created At

2026-02-25 10:12 KST

## Status

Confirmed

## Context

DEV-013-INFRA-SMOKE(i-1i7c)에서 로컬 스모크를 `CHECKPOINT_DB_PATH=/dbfs/mnt/...`로 엄격 검증하려 했지만, 현재 실행 호스트에는 `/dbfs` 마운트가 없어 동일 조건 재현이 불가능했다.

반면 실제 Databricks 워크스페이스 자격 증명 검증과 DBFS API 경로 검증은 성공했으며, 대상 경로 `dbfs:/mnt/agent-state/checkpoints/agent.db` 접근성도 확인되었다(세션 명령/결과 요약 증거: `docs/reports/dev013-checkpoint-db-path-smoke.md`, `docs/reports/dev013-checkpoint-db-path-smoke.jsonl`).

따라서 이번 실행에서 어떤 근거를 승인 가능한 인프라 스모크 증거로 볼지, 그리고 엄격한 런타임 내 검증을 어떻게 후속 의무로 남길지 결정이 필요했다.

## Decision

이번 DEV-013-INFRA-SMOKE 실행에서는 Databricks 인증 및 DBFS API 실경로 검증 결과를 실용적 인프라 스모크 증거로 승인해 진행하고, `/dbfs` 마운트가 보장된 런타임에서의 엄격 로컬 스모크를 후속 필수 검증으로 남기기로 결정한다.

## Rationale

현 호스트 제약(`/dbfs` 미마운트)은 코드 결함이 아니라 실행 환경 차이이므로, 이번 이슈를 완전 차단하면 DEV-013 진행이 불필요하게 지연된다.

대안 검토:
- 엄격 로컬 스모크가 가능할 때까지 현재 이슈를 보류: 증거 강도는 높지만 일정 리스크가 크고, 이미 성공한 실제 워크스페이스 검증 가치를 활용하지 못한다.
- 로컬 우회 경로를 임시 구현해 유사 검증 수행: 본 이슈 범위를 벗어난 추가 구현이 필요하고 검증 의미가 흐려질 수 있다.
- 실용적 인프라 증거로 이번 실행을 통과시키고 엄격 검증을 후속 의무화(선택): 현재 확보 가능한 강한 외부 연동 근거를 활용하면서, 런타임 동등성 검증은 별도 체크포인트로 강제할 수 있다.

이 결정의 트레이드오프는 "즉시 엄격성" 일부를 "검증 가능한 진행성"으로 교환하는 점이며, 후속 이슈에서 런타임 내 `/dbfs` 기반 스모크를 반드시 완료해야 한다.
