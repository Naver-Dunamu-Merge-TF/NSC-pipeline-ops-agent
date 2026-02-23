from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from llmops.prompt_registry import load_prompt


ROOT = Path(__file__).resolve().parents[2]


def test_registry_yaml_matches_spec_section_3_3() -> None:
    registry_path = ROOT / "prompts" / "registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))

    assert registry == {
        "prompts": {
            "dq01_bad_records": {
                "active_version": "v1.0",
                "model": "gpt-4o",
                "temperature": 0.2,
                "description": "bad_records 위반 분석 + 수정 가이드 생성",
            },
            "ops01_triage": {
                "active_version": "v1.0",
                "model": "gpt-4o",
                "temperature": 0.1,
                "description": "파이프라인 장애 트리아지 + 실행 가능 조치 제안",
            },
            "pm01_postmortem": {
                "active_version": "v1.0",
                "model": "gpt-4o",
                "temperature": 0.3,
                "description": "장애 대응 완료 후 포스트모템 초안 생성",
            },
        }
    }


def test_prompt_files_include_json_or_safety_rules() -> None:
    dq_text = (ROOT / "prompts" / "dq01" / "v1.0.txt").read_text(encoding="utf-8")
    ops_text = (ROOT / "prompts" / "ops01" / "v1.0.txt").read_text(encoding="utf-8")
    pm_text = (ROOT / "prompts" / "pm01" / "v1.0.txt").read_text(encoding="utf-8")

    assert "JSON 외 다른 텍스트를 출력하지 않는다." in dq_text
    assert "JSON 외 다른 텍스트를 출력하지 않는다." in ops_text
    assert "원본 데이터 값" in pm_text


def test_load_prompt_returns_active_version_text_and_meta() -> None:
    prompt = load_prompt("dq01_bad_records")

    assert prompt.prompt_id == "dq01_bad_records"
    assert prompt.version == "v1.0"
    assert prompt.model == "gpt-4o"
    assert prompt.temperature == 0.2
    assert "JSON 외 다른 텍스트를 출력하지 않는다." in prompt.text


def test_load_prompt_fail_fast_on_missing_prompt_id() -> None:
    with pytest.raises(KeyError, match="unknown_prompt"):
        load_prompt("unknown_prompt")


def test_load_prompt_fail_fast_on_missing_version_file(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    (prompts_dir / "dq01").mkdir(parents=True)
    registry_path = prompts_dir / "registry.yaml"
    registry_path.write_text(
        """
prompts:
  dq01_bad_records:
    active_version: "v9.9"
    model: "gpt-4o"
    temperature: 0.2
    description: "test"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="v9.9"):
        load_prompt(
            "dq01_bad_records",
            registry_path=registry_path,
            prompts_root=prompts_dir,
        )
