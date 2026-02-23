# ADR-0012: use-log-output-for-report-only-payload

## Created At

2026-02-23 22:26 KST

## Status

Confirmed

## Context

- DEV-018은 `report_only` 노드에서 `incident_id`, `pipeline`, `detected_issues`, 주요 상태를 결정적으로 구성해 최소 1개 매체에 저장/출력해야 한다.
- 현재 AgentState의 `report_only` 쓰기 계약은 `final_status`만 허용되어 있고, 신규 상태 필드 추가는 범위 밖 변경이 된다.
- 동일 DoD를 만족하는 저장/출력 후보로 파일 저장, 체크포인트 아티팩트 저장, 로그 출력이 가능했다.

## Decision

DEV-018 범위에서는 `report_only` payload를 정렬된 JSON 문자열로 로그에 출력하는 방식으로 결정한다.

## Rationale

- 로그 출력은 기존 상태 스키마를 바꾸지 않고도 DoD의 "최소 1개 매체 저장/출력" 요구를 충족한다.
- `json.dumps(..., sort_keys=True)`를 사용하면 키 순서가 고정되어 payload 출력이 결정적으로 유지된다.
- 시간 표시는 DEV-011의 KST 변환 유틸(`to_kst`)을 그대로 재사용할 수 있어 중복 구현을 피한다.
- 대안 1(파일 저장)은 경로/권한/수명주기 정책 결정을 추가로 요구해 DEV-018 범위를 넘는다.
- 대안 2(체크포인트 아티팩트 필드 추가)는 AgentState 계약 변경이 필요해 후속 이슈들과 결합도가 커진다.
