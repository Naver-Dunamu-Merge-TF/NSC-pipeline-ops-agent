from __future__ import annotations

import pytest

from sudocode_orchestrator.utils.config import load_runtime_settings


def test_load_runtime_settings_parses_csv_and_overrides() -> None:
    settings = load_runtime_settings(
        {
            "TARGET_PIPELINES": " pipeline_silver, pipeline_b ,pipeline_c,pipeline_a ",
            "CHECKPOINT_DB_PATH": "/tmp/agent.db",
            "LLM_DAILY_CAP": "12",
            "LANGFUSE_HOST": "https://langfuse.example.com",
        }
    )

    assert settings.target_pipelines == [
        "pipeline_silver",
        "pipeline_b",
        "pipeline_c",
        "pipeline_a",
    ]
    assert settings.checkpoint_db_path == "/tmp/agent.db"
    assert settings.llm_daily_cap == 12
    assert settings.langfuse_host == "https://langfuse.example.com"


def test_load_runtime_settings_uses_defaults_for_optional_keys() -> None:
    settings = load_runtime_settings(
        {
            "TARGET_PIPELINES": "pipeline_silver",
            "LANGFUSE_HOST": "http://localhost:3000",
        }
    )

    assert settings.checkpoint_db_path == "checkpoints/agent.db"
    assert settings.llm_daily_cap == 30


def test_load_runtime_settings_fails_fast_when_required_keys_missing() -> None:
    with pytest.raises(ValueError, match="TARGET_PIPELINES, LANGFUSE_HOST"):
        load_runtime_settings({})


def test_load_runtime_settings_rejects_non_positive_llm_daily_cap() -> None:
    with pytest.raises(ValueError, match="LLM_DAILY_CAP"):
        load_runtime_settings(
            {
                "TARGET_PIPELINES": "pipeline_silver",
                "LLM_DAILY_CAP": "0",
                "LANGFUSE_HOST": "http://localhost:3000",
            }
        )


def test_load_runtime_settings_rejects_empty_target_pipelines_items() -> None:
    with pytest.raises(ValueError, match="TARGET_PIPELINES"):
        load_runtime_settings(
            {
                "TARGET_PIPELINES": "pipeline_silver,,pipeline_b",
                "LANGFUSE_HOST": "http://localhost:3000",
            }
        )
