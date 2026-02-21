from pathlib import Path

import pytest

from sudocode_orchestrator.prompt_renderer import render_prompt


def _template_text() -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / "docs" / "prompts" / "prompt_template.md").read_text(
        encoding="utf-8"
    )


def test_render_prompt_replaces_only_known_placeholders() -> None:
    rendered = render_prompt(
        _template_text(),
        {
            "manifest_id": "m-001",
            "task_id": "DEV-001",
            "gate_id": "G1",
            "epic_id": "EPIC-01",
            "title": "Lock SSOT schema",
            "depends_on": "-",
            "dod_checklist_full": "* [ ] item 1\n* [ ] item 2",
        },
    )

    assert "{{" not in rendered
    assert "- manifest_id: m-001" in rendered
    assert "- task_id: DEV-001" in rendered
    assert "### Ordered Workflow (Do Not Reorder)" in rendered
    assert "### Overflow Handling (Retry Limit Exceeded)" in rendered


def test_render_prompt_raises_when_placeholder_value_missing() -> None:
    with pytest.raises(ValueError, match="Missing values for placeholders"):
        render_prompt(
            _template_text(),
            {
                "manifest_id": "m-001",
                "task_id": "DEV-001",
                "gate_id": "G1",
                "epic_id": "EPIC-01",
                "title": "Lock SSOT schema",
                "depends_on": "-",
            },
        )
