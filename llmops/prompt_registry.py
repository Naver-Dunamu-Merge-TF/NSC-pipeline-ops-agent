from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PromptDefinition:
    prompt_id: str
    version: str
    model: str
    temperature: float
    text: str


def _default_prompts_root() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts"


def _load_registry(registry_path: Path) -> dict[str, Any]:
    with registry_path.open("r", encoding="utf-8") as handle:
        registry: dict[str, Any] = yaml.safe_load(handle)
    return registry


def _load_prompt_meta(meta_path: Path, prompt_id: str) -> dict[str, Any]:
    if not meta_path.exists():
        raise FileNotFoundError(
            f"Prompt metadata file not found for {prompt_id}: {meta_path}"
        )
    with meta_path.open("r", encoding="utf-8") as handle:
        meta: dict[str, Any] = yaml.safe_load(handle)
    return meta


def load_prompt(
    prompt_id: str,
    *,
    registry_path: str | Path | None = None,
    prompts_root: str | Path | None = None,
) -> PromptDefinition:
    root = Path(prompts_root) if prompts_root is not None else _default_prompts_root()
    resolved_registry_path = (
        Path(registry_path) if registry_path is not None else root / "registry.yaml"
    )
    registry = _load_registry(resolved_registry_path)

    prompts = registry.get("prompts")
    if not isinstance(prompts, dict):
        raise KeyError("registry.yaml must contain top-level 'prompts' mapping")

    prompt_entry = prompts.get(prompt_id)
    if not isinstance(prompt_entry, dict):
        raise KeyError(f"Prompt key not found in registry: {prompt_id}")

    active_version = prompt_entry.get("active_version")
    if not isinstance(active_version, str) or not active_version:
        raise KeyError(f"active_version missing for prompt: {prompt_id}")

    prompt_family = prompt_id.split("_", maxsplit=1)[0]
    prompt_text_path = root / prompt_family / f"{active_version}.txt"
    if not prompt_text_path.exists():
        raise FileNotFoundError(
            f"Prompt version file not found for {prompt_id}: {active_version}"
        )
    prompt_meta_path = root / prompt_family / f"{active_version}_meta.yaml"

    prompt_text = prompt_text_path.read_text(encoding="utf-8")
    prompt_meta = _load_prompt_meta(prompt_meta_path, prompt_id)

    model = prompt_meta.get("model")
    if not isinstance(model, str) or not model:
        raise KeyError(
            f"model missing in prompt metadata: {prompt_id}@{active_version}"
        )

    temperature = prompt_meta.get("temperature")
    if not isinstance(temperature, (int, float)):
        raise KeyError(
            f"temperature missing in prompt metadata: {prompt_id}@{active_version}"
        )

    return PromptDefinition(
        prompt_id=prompt_id,
        version=active_version,
        model=model,
        temperature=float(temperature),
        text=prompt_text,
    )
