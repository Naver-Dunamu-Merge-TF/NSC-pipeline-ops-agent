# ADR-0020: LangFuse 내부 UI smoke 자동화 범위를 VNet 내부 실행으로 제한 채택

## Created At

2026-02-25 00:00 KST

## Status

Confirmed

## Context

`docs/runbooks/ai-agent-infra-dev.md`는 staging VNet 내부 호스트에서 `kubectl port-forward` 후 `curl`로 LangFuse UI 응답(200/302)을 확인하는 수동 smoke를 요구한다. 현재 방식은 운영자가 터미널 2개를 열어 절차를 수행하고 증빙(로그/스크린샷)을 별도로 남겨야 하므로, 누락·형식 불일치·재실행 난이도 같은 운영 리스크가 존재한다.

수동 절차의 직접 비용은 낮지만 반복 실행 시 사람 의존성이 커서 배포/회귀 검증의 리드타임이 늘어난다. 특히 실패 시점에 어떤 명령이 어떤 네트워크 컨텍스트에서 실행됐는지 일관되게 남기기 어려워 사후 분석 비용이 증가한다.

자동화 대안은 세 가지로 정리된다. 대안 1(현상 유지)은 즉시 비용이 없지만 증빙 품질 편차가 계속 남는다. 대안 2(`verify_ai_agent_infra_dev.sh`에 UI smoke 직접 통합)는 단일 명령 UX가 장점이지만, 실행 환경이 VNet 내부라는 제약 때문에 GitHub-hosted runner/외부 네트워크에서는 구조적으로 실패하며, 스크립트 실패 원인이 인프라 결함인지 실행 위치 문제인지 구분이 어려워진다. 대안 3(VNet 내부 전용 비대화형 smoke 스크립트 분리)는 자동화 이득을 확보하면서도 실행 경계를 명확히 분리할 수 있다.

보안 측면에서 대안 2/3 모두 "내부망에서만 접근" 원칙을 유지해야 하며, smoke 아티팩트에 세션 정보/민감 헤더가 남지 않도록 출력 최소화가 필요하다. 또한 public ingress를 새로 열어 CI에서 접근 가능하게 만드는 방식은 내부 전용 배포 원칙과 충돌하므로 선택지에서 제외한다.

## Decision

staging LangFuse UI smoke 자동화는 "조건부 채택"으로 결정하며, `verify_ai_agent_infra_dev.sh` 본체에는 통합하지 않고 VNet 내부 실행 전용 비대화형 보조 스크립트를 별도 도입하되 필수 증빙 산출물은 단일 JSON 파일 규격으로 고정한다.

## Rationale

대안 1(현상 유지)은 변경 비용이 가장 작지만 사람 의존 절차의 누락/편차 리스크를 해소하지 못하므로 장기 운영 효율이 낮다. 대안 2(`verify_ai_agent_infra_dev.sh` 직접 통합)는 한 번에 실행된다는 장점이 있으나, 현재 검증 스크립트가 Azure/K8s 리소스 정합성 검사를 담당하는 범위를 넘어 네트워크 위치 의존 smoke를 결합하게 되어 책임 경계가 흐려진다. 또한 VNet 외부 실행 환경에서는 오탐 실패가 빈번해질 가능성이 높다.

대안 3(전용 보조 스크립트 분리)은 실행 환경 제약을 명시적으로 코드화할 수 있고, 수동 단계의 핵심 실수를 줄이면서도 기존 검증 스크립트의 목적(구성 검증)과 충돌하지 않는다. 트레이드오프로 "완전 무인 CI"는 당장 달성하지 못하지만, self-hosted runner/jumpbox 예약 실행 같은 후속 확장 경로를 열어 둔다.

조건부 채택의 성공 기준과 재검토 트리거는 다음과 같이 고정한다. 성공 기준은 스크립트 도입 이후 연속된 10회의 staging 검증 실행에서 (1) 필수 JSON 산출물 제출률 100%, (2) smoke 판정 결과 `pass` 비율 90% 이상, (3) "실행 환경 부적합"으로 인한 실패 0회를 동시에 만족하는 것이다. 재검토 트리거는 (a) 연속된 3회 staging 검증에서 JSON 산출물이 누락되는 경우, (b) 최근 10회 기준 `pass` 비율이 90% 미만으로 하락하는 경우, (c) 민감정보(`Set-Cookie`, `Authorization`, 토큰 평문) 노출이 1회라도 확인되는 경우다. 재검토 트리거 충족 시 자동화 방식은 유지하지 않고 "수동 smoke + 원인 시정"으로 즉시 롤백해 ADR-0020 후속 의사결정을 다시 연다.

후속 작업의 산출물 형식 모호성을 제거하기 위해, 허용되는 증빙 산출물 형식은 JSON 단일 파일 1종으로 제한한다. 파일명 규칙은 `langfuse-ui-smoke-result.json`이며, 루트 객체 키는 `timestamp_utc`, `namespace`, `runner_context`, `http_code`, `result`, `response_sha256`만 허용한다. `result`는 `pass` 또는 `fail`만 허용하고, `pass` 판정은 `http_code`가 200 또는 302이며 `response_sha256`가 비어 있지 않을 때로 고정한다.

채택 후 작업 항목은 다음으로 분해한다.

1. `scripts/infra/`에 VNet 내부 전용 LangFuse UI smoke 스크립트(비대화형, 종료코드 기반) 추가.
2. smoke 결과를 `langfuse-ui-smoke-result.json` 단일 규격으로 출력하고(`timestamp_utc`, `namespace`, `runner_context`, `http_code`, `result`, `response_sha256`), 그 외 형식(스크린샷/자유 텍스트)을 DoD 증빙으로 인정하지 않도록 규칙을 명시.
3. `docs/runbooks/ai-agent-infra-dev.md`를 "수동 2터미널 절차"에서 "전용 스크립트 실행 + 아티팩트 첨부" 중심으로 갱신.
4. `verify_ai_agent_infra_dev.sh`에는 직접 통합하지 않고, 전용 smoke 스크립트 존재/사용 경로를 문서 링크로만 연결.
