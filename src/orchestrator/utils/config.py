from __future__ import annotations

import os
from typing import Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    PositiveInt,
    ValidationError,
    field_validator,
)


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    target_pipelines: list[str]
    checkpoint_db_path: str = "checkpoints/agent.db"
    llm_daily_cap: PositiveInt = 30
    langfuse_host: str

    @field_validator("target_pipelines", mode="before")
    @classmethod
    def _parse_target_pipelines(cls, value: object) -> list[str]:
        if isinstance(value, str):
            entries = [item.strip() for item in value.split(",")]
        elif isinstance(value, list):
            entries = []
            for item in value:
                if not isinstance(item, str):
                    raise ValueError("TARGET_PIPELINES must only contain strings")
                entries.append(item.strip())
        else:
            raise ValueError("TARGET_PIPELINES must be a comma-separated string")

        cleaned = [item for item in entries if item]
        if len(cleaned) != len(entries):
            raise ValueError("TARGET_PIPELINES contains empty pipeline name")
        if not cleaned:
            raise ValueError("TARGET_PIPELINES must contain at least one pipeline")
        return cleaned


def load_runtime_settings(environ: Mapping[str, str] | None = None) -> RuntimeSettings:
    env = environ if environ is not None else os.environ
    missing = [
        key
        for key in ("TARGET_PIPELINES", "LANGFUSE_HOST")
        if not env.get(key, "").strip()
    ]
    if missing:
        missing_keys = ", ".join(missing)
        raise ValueError(f"Missing required runtime settings: {missing_keys}")

    try:
        return RuntimeSettings.model_validate(
            {
                "target_pipelines": env["TARGET_PIPELINES"],
                "checkpoint_db_path": env.get(
                    "CHECKPOINT_DB_PATH", "checkpoints/agent.db"
                ),
                "llm_daily_cap": _parse_llm_daily_cap(env.get("LLM_DAILY_CAP")),
                "langfuse_host": env["LANGFUSE_HOST"],
            }
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid runtime settings: {exc}") from exc


def _parse_llm_daily_cap(raw: str | None) -> int:
    if raw is None:
        return 30
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            "Invalid runtime settings: LLM_DAILY_CAP must be a positive integer"
        ) from exc
    if value <= 0:
        raise ValueError(
            "Invalid runtime settings: LLM_DAILY_CAP must be a positive integer"
        )
    return value
