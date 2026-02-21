from __future__ import annotations

import re

from .models import IssueContext


PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")
REQUIRED_KEYS = {
    "manifest_id",
    "task_id",
    "gate_id",
    "epic_id",
    "title",
    "depends_on",
    "dod_checklist_full",
}


def render_prompt(template_text: str, payload: dict[str, str]) -> str:
    placeholders_in_template = set(PLACEHOLDER_PATTERN.findall(template_text))
    missing_keys = sorted((placeholders_in_template & REQUIRED_KEYS) - set(payload))
    if missing_keys:
        raise ValueError(f"Missing values for placeholders: {', '.join(missing_keys)}")

    rendered = template_text
    for key in REQUIRED_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        rendered = re.sub(r"{{\s*" + re.escape(key) + r"\s*}}", value, rendered)

    unresolved = sorted(set(PLACEHOLDER_PATTERN.findall(rendered)))
    if unresolved:
        raise ValueError(f"Unresolved placeholders remain: {', '.join(unresolved)}")

    return rendered


def render_issue_prompt(template_text: str, issue: IssueContext) -> str:
    return render_prompt(
        template_text,
        {
            "manifest_id": issue.manifest_id,
            "task_id": issue.task_id,
            "gate_id": issue.gate_id,
            "epic_id": issue.epic_id,
            "title": issue.title,
            "depends_on": issue.depends_on,
            "dod_checklist_full": issue.dod_checklist_full,
        },
    )
