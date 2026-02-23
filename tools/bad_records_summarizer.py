from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

MAX_TYPE_COUNT = 50
MAX_SAMPLES_PER_TYPE = 10
MAX_TABLE_LENGTH = 80
MAX_FIELD_LENGTH = 80
MAX_REASON_LENGTH = 160
MAX_RECORD_JSON_LENGTH = 240


def summarize_bad_records(
    bad_records: list[dict[str, Any]],
    *,
    max_type_count: int = MAX_TYPE_COUNT,
    max_samples_per_type: int = MAX_SAMPLES_PER_TYPE,
    max_table_length: int = MAX_TABLE_LENGTH,
    max_field_length: int = MAX_FIELD_LENGTH,
    max_reason_length: int = MAX_REASON_LENGTH,
    max_record_json_length: int = MAX_RECORD_JSON_LENGTH,
) -> dict[str, Any]:
    if not bad_records:
        return {
            "total_records": 0,
            "type_count": 0,
            "types_truncated": False,
            "types": [],
        }

    grouped_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    grouped_samples: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(
        list
    )

    for record in bad_records:
        source_table = _normalize_text(record.get("source_table", "unknown"))
        field, reason = _extract_field_and_reason(
            record.get("reason"),
        )

        violation_key = (source_table, field, reason)
        grouped_counts[violation_key] += 1

        if len(grouped_samples[violation_key]) < max_samples_per_type:
            grouped_samples[violation_key].append(
                {
                    "record_json": _abbreviate(
                        record.get("record_json", ""),
                        max_record_json_length,
                    )
                }
            )

    sorted_keys = sorted(
        grouped_counts,
        key=lambda key: (-grouped_counts[key], key[0], key[1], key[2]),
    )
    selected_keys = sorted_keys[:max_type_count]

    types = []
    for key in selected_keys:
        source_table, field, reason = key
        count = grouped_counts[key]
        samples = grouped_samples[key]
        types.append(
            {
                "source_table": _abbreviate(source_table, max_table_length),
                "field": _abbreviate(field, max_field_length),
                "reason": _abbreviate(reason, max_reason_length),
                "count": count,
                "samples_truncated": count > len(samples),
                "samples": samples,
            }
        )

    return {
        "total_records": len(bad_records),
        "type_count": len(types),
        "types_truncated": len(sorted_keys) > max_type_count,
        "types": types,
    }


def _extract_field_and_reason(
    raw_reason: Any,
) -> tuple[str, str]:
    parsed_reason: dict[str, Any] = {}
    original_reason_text = ""

    if isinstance(raw_reason, dict):
        parsed_reason = raw_reason
    elif isinstance(raw_reason, str):
        original_reason_text = raw_reason
        try:
            loaded = json.loads(raw_reason)
            if isinstance(loaded, dict):
                parsed_reason = loaded
        except json.JSONDecodeError:
            parsed_reason = {}

    field_value = parsed_reason.get("field")
    field_text = field_value if isinstance(field_value, str) else "unknown"
    if not field_text.strip():
        field_text = "unknown"

    reason_text = ""
    for reason_key in ("detail", "rule", "reason"):
        value = parsed_reason.get(reason_key)
        if value is None:
            continue
        reason_text = value if isinstance(value, str) else str(value)
        if reason_text.strip():
            break

    if not reason_text.strip():
        reason_text = original_reason_text or "unknown"

    return (field_text, reason_text)


def _normalize_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def _abbreviate(value: Any, max_length: int) -> str:
    text = value if isinstance(value, str) else str(value)
    if max_length < 0:
        max_length = 0
    if len(text) <= max_length:
        return text
    if max_length <= 3:
        return text[:max_length]
    return f"{text[: max_length - 3]}..."
