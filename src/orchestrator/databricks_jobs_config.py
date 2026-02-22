from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PipelineJobConfig(_StrictModel):
    refresh: int


class JobsConfig(_StrictModel):
    pipeline_silver: PipelineJobConfig
    pipeline_b: PipelineJobConfig
    pipeline_c: PipelineJobConfig
    pipeline_a: PipelineJobConfig


class DatabricksJobsConfig(_StrictModel):
    jobs: JobsConfig


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: _UniqueKeyLoader, node: yaml.Node, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"Duplicate key: {key}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def default_databricks_jobs_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "databricks_jobs.yaml"


def load_databricks_jobs_config(
    config_path: str | Path | None = None,
) -> DatabricksJobsConfig:
    path = (
        Path(config_path)
        if config_path is not None
        else default_databricks_jobs_config_path()
    )
    with path.open("r", encoding="utf-8") as handle:
        raw_config = yaml.load(handle, Loader=_UniqueKeyLoader)
    return DatabricksJobsConfig.model_validate(raw_config)
