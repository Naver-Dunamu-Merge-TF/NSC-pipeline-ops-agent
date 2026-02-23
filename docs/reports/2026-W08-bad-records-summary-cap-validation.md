# bad_records_summary 상한 정책 검증 보고서 (ADR-0009 / i-6xp6)

- 작성 시각 (UTC): 2026-02-23
- 대상 이슈: `i-6xp6`
- 기준 문서: `docs/adr/0009-bound-bad-records-summary-size.md`

## 1) 검증 목적

- `bad_records_summary` 하드 캡 정책(타입 50, 샘플 10, 길이 80/80/160/240)이 analyze 입력 폭주를 억제하는지 재현 가능한 방식으로 확인한다.
- 검증 결과에 따라 상한값 유지/수정 여부를 확정한다.

## 2) 재현 커맨드

- 단위 경계/회귀 테스트:
  - `python3 -m pytest tests/unit/test_bad_records_summarizer.py -q`
- 대량 입력 직렬화 크기 확인(합성 데이터):
  - 아래 스크립트를 그대로 실행한다.

```bash
python3 - <<'PY'
import json

from tools.bad_records_summarizer import summarize_bad_records

records = []
for idx in range(10_000):
    type_idx = idx % 120
    records.append(
        {
            "source_table": "table_" + str(type_idx) + "_" + ("s" * 220),
            "reason": json.dumps(
                {
                    "field": "field_" + str(type_idx) + "_" + ("f" * 220),
                    "detail": "reason_" + str(type_idx) + "_" + ("r" * 420),
                },
                ensure_ascii=False,
            ),
            "record_json": json.dumps(
                {"idx": idx, "payload": "x" * 2000},
                ensure_ascii=False,
            ),
        }
    )

summary = summarize_bad_records(records)
serialized = json.dumps(summary, ensure_ascii=False)

print("type_count", summary["type_count"])
print("types_truncated", summary["types_truncated"])
print("max_samples", max(len(v["samples"]) for v in summary["types"]))
print("serialized_bytes", len(serialized.encode("utf-8")))
PY
```

## 3) 검증 시나리오와 기준

- 0건: 빈 입력에서 구조가 고정(`total_records=0`, `types=[]`)되는지 확인
- 1건: 문자열 상한 절단(`...`)과 필드 길이 상한 준수 확인
- 1만건+: 다유형/긴 문자열 입력에서 다음을 동시에 확인
  - `type_count <= 50`
  - `len(samples) <= 10` per type
  - 문자열 상한 `80/80/160/240` 준수
  - 결과 JSON 직렬화 크기 상한(회귀 기준): `<= 160,000 bytes`

## 4) 결과

- 단위 테스트에서 0건/1건/대량 케이스가 모두 통과했다.
- 대량 합성 데이터(10,000건, 120유형, 긴 문자열) 측정 결과:
  - `type_count=50`
  - `types_truncated=True`
  - `max_samples=10`
  - `serialized_bytes=154178`
- 명시적 합격 기준: `serialized_bytes <= 160000`
- 판정: `154178 <= 160000`이므로 합격
- 결론: 현재 상한값은 폭주 억제 관점에서 유효하며, 기준 대비 여유(5,822 bytes)가 있어 **현 정책 유지**로 결정한다.

## 5) 변경 관리 규칙

- 상한값 조정이 필요하면, 먼저 경계 테스트(0건/1건/1만건+)와 직렬화 크기 회귀 테스트를 실패 상태로 재현한다.
- 이후 상한값/절단 규칙 수정 -> 테스트 통과 -> ADR-0009 + `.specs/ai_agent_spec.md` 동기화 순으로 반영한다.
