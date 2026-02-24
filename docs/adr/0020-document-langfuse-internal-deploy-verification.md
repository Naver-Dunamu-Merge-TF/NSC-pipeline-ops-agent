# ADR-0020: DEV-043 내부 LangFuse 배포 증빙을 문서/검증 스크립트로 고정

## Created At

2026-02-25 00:00 KST

## Status

PendingReview

## Context

DEV-043 DoD는 LangFuse를 AKS 내부 서비스로 운영하기 위한 배포 매니페스트, ACR 이미지 준비 절차, 내부 접근 확인, staging UI 스모크, 롤백 절차를 저장소에서 재현 가능하게 남길 것을 요구한다. 기존 자산에는 Deployment/Service와 기본 배포 스크립트가 있었지만, ACR 이미지 준비와 staging UI 스모크 절차가 운영자 관점에서 충분히 명시적이지 않았다.

## Decision

DEV-043 범위에서는 새 배포 도구를 추가하지 않고, 기존 `scripts/infra`와 runbook 문서를 확장해 운영 절차를 고정한다. 동시에 `verify_ai_agent_infra_dev.sh`에 LangFuse 외부 노출 방지 확인(LoadBalancer ingress 없음, `app=langfuse` Ingress 없음)을 추가한다.

## Rationale

대안 1은 Helm 차트/추가 자동화 스크립트를 새로 도입하는 방식이었지만, DEV-043 DoD를 충족하기 위해 필수는 아니며 변경 범위를 불필요하게 넓힌다. 대안 2는 문서만 보강하고 검증 스크립트는 유지하는 방식이었지만, 내부 전용 노출 조건이 수동 확인에만 의존하게 된다. 기존 구조를 유지하면서 문서 + 자동 확인을 함께 강화하는 현재 결정이 가장 작은 변경으로 DoD 증빙 가능성과 롤백 용이성을 동시에 확보한다.
