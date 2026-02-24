# ADR-0027: DEV-012 스모크 런타임 입력을 fixture 우선으로 사용

## Created At

2026-02-25 02:32 KST

## Status

Confirmed

## Context

i-3rd5(DEV-012-INFRA-SMOKE) 구현 과정에서 실환경 의존 없이 재현 가능한 smoke 실행 경로가 필요했다. dev/staging 값을 직접 참조하면 환경 변동과 접근 제약에 따라 결과가 흔들리고, 로컬·CI에서 동일한 실패/성공 신호를 얻기 어렵다. 또한 이번 변경은 low-impact/reversible 원칙을 유지해야 하므로 기존 운영 설정을 강제 변경하지 않으면서 필요 시 실환경 입력을 선택적으로 주입할 수 있어야 했다.

## Decision

DEV-012 smoke의 dev/staging 런타임 입력은 기본적으로 fixture 경로를 사용하고, 필요할 때만 env override로 대체하며, 실행은 opt-in 게이트를 통과한 경우에만 수행하도록 구성하기로 결정한다.

## Rationale

대안 1은 dev/staging 실환경 입력을 기본값으로 직접 읽는 방식이었으나, 환경 접근성 차이와 외부 상태 변화로 재현성이 낮고 CI 안정성을 해쳐 기각했다. 대안 2는 fixture만 허용하고 env override를 제공하지 않는 방식이었으나, 실제 값 기반 확인이 필요한 점검 시나리오에서 유연성이 부족해 기각했다. 대안 3은 기존 smoke를 상시 실행하도록 두는 방식이었으나, 불필요한 실행 비용과 외부 의존 노출을 증가시켜 low-impact/reversible 목표와 맞지 않아 기각했다. 최종안은 fixture 기본값으로 결정론적 실행을 확보하면서 env override와 opt-in 게이트를 통해 필요한 경우에만 확장할 수 있어 안정성, 운영 부담, 되돌리기 용이성의 균형이 가장 좋다.
