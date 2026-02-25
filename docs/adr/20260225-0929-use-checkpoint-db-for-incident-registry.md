# ADR-20260225-0929: use-checkpoint-db-for-incident-registry

## Created At

2026-02-25 09:29 KST

## Status

Confirmed

## Context

DEV-013에서는 `CHECKPOINT_DB_PATH`를 기반으로 체크포인터를 구성하고, 동일 `incident_id`로 재시작/재개 가능한 실행 경로를 제공해야 한다. 이때 운영자가 재개 상태를 추적할 최소 메타데이터(`incident_id`, `pipeline`, `detected_at`, `fingerprint`, `status`)를 어디에 저장할지 명시가 필요했다.

선택지는 (1) 체크포인터 DB와 분리된 별도 SQLite 파일, (2) 메모리/프로세스 로컬 저장소, (3) 체크포인터와 동일 SQLite 파일 내 별도 테이블이었다. DEV-013의 범위는 로컬 재시작 복구 스모크를 충족하는 최소 구현이며, 추가 인프라나 동기화 계층을 도입하지 않는 것이 우선이었다.

참조 스펙: `.specs/ai_agent_spec.md` §체크포인터 및 재개 경로 요구사항(DEV-013 문맥)

## Decision

incident 최소 메타 레지스트리는 `CHECKPOINT_DB_PATH`가 가리키는 동일 SQLite 파일의 `incident_registry` 테이블에 저장하고, `status`는 `final_status` 우선·부재 시 `invoke=running`/`resume=resumed` 기본값으로 기록하도록 결정한다.

## Implementation-time Status Transition Policy

구현 시점에서 `incident_registry.status` 허용값은 `running`, `resumed`, `resolved`, `failed`, `escalated`, `reported`로 한정한다.

`final_status`가 없거나 허용 집합 밖이면 `invoke` 경로는 `running`, `resume` 경로는 `resumed`를 기본값으로 사용한다.

단조 증가 가드로 terminal 상태(`resolved`, `failed`, `escalated`, `reported`)는 이후 `running`/`resumed`로 되돌리지 않는다.

다만 현재 구현은 더 최신의 유효한 `final_status`가 도착하면 terminal 간 덮어쓰기를 허용하며, 이 규칙은 후속 이슈에서 재검토한다.

## Rationale

선택한 접근(동일 DB 내 별도 테이블)은 DEV-013의 요구를 가장 적은 변경으로 충족한다. 체크포인터와 레지스트리가 동일 파일을 공유하므로 재시작 후 상태 추적 경로가 단순해지고, 배포 시 추가 저장소 경로를 관리하지 않아도 된다.

대안 비교:
- 분리 SQLite 파일: 저장소 책임이 명확해지지만 경로/백업/동기화 관리 포인트가 늘어나 DEV-013 최소 범위를 넘어선다.
- 메모리/프로세스 로컬 저장소: 구현은 단순하지만 재시작 시 데이터가 소실되어 요구사항(재개 가능성)을 만족하지 못한다.
- 동일 DB 내 테이블(선택): 운영 단순성과 재시작 복구 요구를 동시에 충족하지만, 향후 `status` 분류 체계 표준화와 다중 프로세스 경쟁 조건 점검이 필요하다.

트레이드오프로 이번 결정은 상태값 기본 규칙을 임시 최소 정책으로 고정했다. 후속 작업에서 상태 전이 사전과 외부 관측 지표 정렬 규칙을 정교화한다.
