from __future__ import annotations

import json

from tools.bad_records_summarizer import (
    MAX_FIELD_LENGTH,
    MAX_REASON_LENGTH,
    MAX_RECORD_JSON_LENGTH,
    MAX_SAMPLES_PER_TYPE,
    MAX_TABLE_LENGTH,
    MAX_TYPE_COUNT,
    summarize_bad_records,
)


def test_summarize_bad_records_with_zero_records() -> None:
    assert summarize_bad_records([]) == {
        "total_records": 0,
        "type_count": 0,
        "types_truncated": False,
        "types": [],
    }


def test_summarize_bad_records_with_one_record_and_abbreviation() -> None:
    long_source_table = "source_" + ("table_" * 40)
    long_field = "field_" + ("name_" * 40)
    long_reason = "reason_" + ("detail_" * 60)
    long_record_json = json.dumps({"payload": "x" * 2000}, ensure_ascii=False)

    records = [
        {
            "source_table": long_source_table,
            "reason": json.dumps(
                {
                    "field": long_field,
                    "detail": long_reason,
                },
                ensure_ascii=False,
            ),
            "record_json": long_record_json,
        }
    ]

    result = summarize_bad_records(records)

    assert result["total_records"] == 1
    assert result["type_count"] == 1
    assert result["types_truncated"] is False
    assert len(result["types"]) == 1

    violation = result["types"][0]
    assert violation["count"] == 1
    assert violation["samples_truncated"] is False
    assert len(violation["samples"]) == 1

    assert violation["source_table"].endswith("...")
    assert len(violation["source_table"]) <= 80

    assert violation["field"].endswith("...")
    assert len(violation["field"]) <= 80

    assert violation["reason"].endswith("...")
    assert len(violation["reason"]) <= 160

    sample = violation["samples"][0]
    assert sample["record_json"].endswith("...")
    assert len(sample["record_json"]) <= 240


def test_summarize_bad_records_with_large_volume_has_hard_bounds() -> None:
    records: list[dict[str, str]] = []

    for idx in range(10_000):
        type_idx = idx % 120
        records.append(
            {
                "source_table": f"table_{type_idx}",
                "reason": json.dumps(
                    {
                        "field": f"field_{type_idx % 11}",
                        "detail": f"constraint_violation_{type_idx}",
                    },
                    ensure_ascii=False,
                ),
                "record_json": json.dumps(
                    {"index": idx, "payload": "x" * 800},
                    ensure_ascii=False,
                ),
            }
        )

    result = summarize_bad_records(records)

    assert result["total_records"] == 10_000
    assert result["type_count"] == 50
    assert result["types_truncated"] is True
    assert len(result["types"]) == 50

    assert any(violation["samples_truncated"] for violation in result["types"])

    for violation in result["types"]:
        assert len(violation["samples"]) <= 10
        assert len(violation["source_table"]) <= 80
        assert len(violation["field"]) <= 80
        assert len(violation["reason"]) <= 160
        for sample in violation["samples"]:
            assert len(sample["record_json"]) <= 240


def test_summarize_bad_records_does_not_merge_types_with_truncated_reason() -> None:
    records = [
        {
            "source_table": "events",
            "reason": json.dumps(
                {
                    "field": "category",
                    "detail": "shared-prefix-A",
                },
                ensure_ascii=False,
            ),
            "record_json": '{"id": 1}',
        },
        {
            "source_table": "events",
            "reason": json.dumps(
                {
                    "field": "category",
                    "detail": "shared-prefix-B",
                },
                ensure_ascii=False,
            ),
            "record_json": '{"id": 2}',
        },
    ]

    result = summarize_bad_records(records, max_reason_length=10)

    assert result["total_records"] == 2
    assert result["type_count"] == 2
    assert sorted(violation["count"] for violation in result["types"]) == [1, 1]


def test_summarize_bad_records_large_volume_serialized_size_is_bounded() -> None:
    records: list[dict[str, str]] = []

    for idx in range(12_500):
        type_idx = idx % 200
        records.append(
            {
                "source_table": f"table_{type_idx}_" + ("s" * 200),
                "reason": json.dumps(
                    {
                        "field": f"field_{type_idx}_" + ("f" * 200),
                        "detail": f"violation_{type_idx}_" + ("r" * 400),
                    },
                    ensure_ascii=False,
                ),
                "record_json": json.dumps(
                    {
                        "index": idx,
                        "payload": "x" * 2000,
                    },
                    ensure_ascii=False,
                ),
            }
        )

    result = summarize_bad_records(records)
    serialized = json.dumps(result, ensure_ascii=False)

    assert result["total_records"] == 12_500
    assert result["type_count"] == MAX_TYPE_COUNT
    assert result["types_truncated"] is True

    for violation in result["types"]:
        assert len(violation["samples"]) <= MAX_SAMPLES_PER_TYPE
        assert len(violation["source_table"]) <= MAX_TABLE_LENGTH
        assert len(violation["field"]) <= MAX_FIELD_LENGTH
        assert len(violation["reason"]) <= MAX_REASON_LENGTH
        for sample in violation["samples"]:
            assert len(sample["record_json"]) <= MAX_RECORD_JSON_LENGTH

    assert len(serialized.encode("utf-8")) <= 160_000
