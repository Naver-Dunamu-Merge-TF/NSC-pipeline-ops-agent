---
name: create-adr
description: >
  ADR (Architecture Decision Record) authoring workflow. Use when a design
  decision needs to be recorded in docs/adr/NNNN-title.md. Covers numbering,
  file naming, section templates, and post-ADR checklist.
  ADR trigger criteria are defined in skills/create-pr/SKILL.md §3.
---

# Create ADR Skill

> **Language rule:** The SKILL instructions below are in English.
> **ADR content (each section body) must be written in Korean.**

---

## 1. When to Write an ADR

See **`skills/create-pr/SKILL.md §3`** for the full trigger criteria. In short, write an ADR when:

- A design decision diverges from what existing `.specs/` documents specify
- You chose one approach over multiple valid alternatives and the tradeoff needs to be recorded
- The change introduces a breaking or backwards-incompatible interface modification
- The decision has direct security or performance implications

When in doubt, write the ADR. It is cheaper to document than to re-litigate later.

---

## 2. ADR Number Assignment

Scan `docs/adr/` for existing `NNNN-*.md` files, extract the highest number, and increment by 1. Start at `0001` if none exist.

```bash
LAST=$(ls docs/adr/*.md 2>/dev/null \
  | xargs -I{} basename {} .md \
  | grep -oP '^\d+' \
  | sort -n \
  | tail -1)
NEXT=$(printf '%04d' $(( ${LAST:-0} + 1 )))
# → NEXT is the zero-padded next ADR number (e.g., "0003")
# If no ADRs exist, LAST is empty and NEXT becomes "0001"
```

---

## 3. File Naming Convention

```
docs/adr/NNNN-<kebab-case-title>.md
```

- Use a decision verb in the title (e.g., `use-langgraph-for-agent-state`, `reject-polling-in-favor-of-event-driven`)
- Keep the title concise (3–6 words)

---

## 4. ADR Template

Copy the template below and fill in each section **in Korean**.

```markdown
# ADR-NNNN: <title>

## Status

Proposed / Accepted / Deprecated

## Context

<!-- 이 결정이 필요해진 배경을 서술한다.
     - 해결해야 할 문제 또는 충족해야 할 요구사항
     - 관련 제약조건 (성능, 보안, 운영 비용 등)
     - 참조 스펙: `.specs/<파일>.md` §<섹션> -->

## Decision

<!-- 선택한 접근법을 단 한 문장으로 선언한다.
     형식: "~로 결정한다."
     한 문장으로 정리되지 않는다면 결정이 아직 명확하지 않은 것이다. -->

## Rationale

<!-- 이 접근법을 선택한 이유와 기각한 대안을 기록한다.
     - 고려한 대안 목록 (각 대안의 장단점 포함)
     - 최종 선택의 트레이드오프
     - 기각 이유 (미래의 에이전트/사람이 같은 고민을 반복하지 않도록) -->
```

---

## 5. Section Writing Guidelines

| Section | Key Principle |
|---------|---------------|
| **Context** | Focus on "why this decision was needed." Reference the specific `.specs/` constraint or domain rule that prompted it. |
| **Decision** | One declarative sentence only. If you cannot state it in one sentence, the decision is not ready to be recorded yet. |
| **Rationale** | Always list rejected alternatives with reasons. This is the highest-value section — it prevents future re-litigation. |

---

## 6. Post-ADR Checklist

After writing the ADR file:

- [ ] Link the ADR file path in the PR body `## Document Impact` section
- [ ] Note the affected `.specs/` files (if any) in the same section
- [ ] `approval:auto` is **disabled** for this PR — `docs/adr/` changes block Auto-Merge automatically (see `AGENTS.md`)
- [ ] If the decision requires a `.specs/` update, add a spec-update task to `.roadmap/roadmap.md` first — the Sudocode daemon will sync it to the Issue DAG. If the Roadmap is not immediately editable (e.g., agent context), register directly via MCP as a fallback:
  ```
  sudocode.upsert_issue({
    "title": "spec-update: <brief description>",
    "description": "Update .specs/<file>.md to reflect ADR NNNN decision.",
    "tags": ["spec-update"],
    "depends_on": ["<current-issue-id>"]
  })
  ```

---

## 7. gh Command

Include the ADR in the same PR as the implementation change that triggered it.
No separate PR is needed for a new ADR unless it affects `.specs/` (which requires a dedicated spec-update task).
