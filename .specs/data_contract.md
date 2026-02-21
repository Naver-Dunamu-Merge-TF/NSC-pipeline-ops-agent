# Data Contract (Agent Input SSOT)

DEV-001 기준으로, 에이전트(`detect.py`, `collect.py`)가 실제로 읽는 컬럼만 SSOT로 고정한다. 에이전트 입력 컬럼의 SSOT는 `data_contract.md`다.

## `gold.pipeline_state`

| 컬럼 | 타입(권장) | 에이전트 사용 목적 |
|---|---|---|
| `pipeline_name` | `string` | 파이프라인 필터 |
| `status` | `string` | 장애 판정 (`success`, `failure`) |
| `last_success_ts` | `timestamp` | 컷오프 지연 판단 |
| `last_processed_end` | `timestamp` | downstream 하드 게이트 판정 (`pipeline_b`, `pipeline_c`) |
| `last_run_id` | `string` | fingerprint 생성/추적 |

## `silver.dq_status`

| 컬럼 | 타입(권장) | 에이전트 사용 목적 |
|---|---|---|
| `source_table` | `string` | 점검 대상 테이블 식별 |
| `dq_tag` | `string` | DQ 태그 기반 트리거 분기 |
| `severity` | `string` | 임계 우선순위 판단 (`CRITICAL` 우선) |
| `run_id` | `string` | 최신 run_id 필터 |
| `window_end_ts` | `timestamp` | 최근 윈도우 필터 |
| `date_kst` | `date` | 파티션 필터 |

## `gold.exception_ledger`

| 컬럼 | 타입(권장) | 에이전트 사용 목적 |
|---|---|---|
| `severity` | `string` | CRITICAL 필터 |
| `domain` | `string` | `dq` 필터 (`detect` / `collect` 공통) |
| `exception_type` | `string` | 예외 유형 분류 |
| `source_table` | `string` | 발생 소스 추적 |
| `metric` | `string` | 메트릭 식별 |
| `metric_value` | `decimal(38,6)` | 메트릭 값 |
| `run_id` | `string` | 신규 예외 판정 기준 |
| `generated_at` | `timestamp` | 최근 예외 시각 필터 |

## `silver.bad_records`

| 컬럼 | 타입(권장) | 에이전트 사용 목적 |
|---|---|---|
| `source_table` | `string` | 위반 소스 테이블 |
| `reason` | `string` | 위반 사유/필드 추론 근거 |
| `record_json` | `string` | 원본 레코드 값 |
| `run_id` | `string` | 분석 run_id 추적 |
| `detected_date_kst` | `date` | 분석 파티션 필터 |

`silver.bad_records.reason` 포맷은 **현재 가정 + 확인 필요** 상태로 유지한다.

- 현재 가정: `reason`은 `field`, `rule`, `detail` 키가 들어간 구조 문자열(예: JSON 문자열) 형식을 사용한다.
- `field` 추출이 불확실할 때 fallback으로 `field="unknown"`을 사용한다.
- `reason` 파싱 실패 또는 `field` 키 부재는 수집/분석 경로에서 확인 후 보강 대상으로 관리한다.
