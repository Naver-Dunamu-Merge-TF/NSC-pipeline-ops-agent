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

Run this Bash snippet to calculate the next ADR number.

```bash
LAST=$(ls docs/adr/[0-9][0-9][0-9][0-9]-*.md 2>/dev/null | sort | tail -1)
LAST=${LAST##*/}
LAST=${LAST%%-*}
NEXT=$(printf '%04d' $((10#${LAST:-0} + 1)))
# NEXT is the zero-padded next ADR number (e.g., "0005")
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
Keep the header label exactly as `Created At` (English only).
`Created At` must use Korean format: `YYYY-MM-DD HH:mm KST`.

```markdown
# ADR-NNNN: <title>

## Created At

2026-02-23 14:30 KST

## Status

PendingReview

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
| **Created At** | Keep the section header in English (`Created At`). Use Korean datetime format `YYYY-MM-DD HH:mm KST`. Keep it as the first section below the ADR title and set it to the initial authoring timestamp. |
| **Context** | Focus on "why this decision was needed." Reference the specific `.specs/` constraint or domain rule that prompted it. |
| **Decision** | One declarative sentence only. If you cannot state it in one sentence, the decision is not ready to be recorded yet. |
| **Rationale** | Always list rejected alternatives with reasons. This is the highest-value section — it prevents future re-litigation. |

---

## 6. Post-ADR Checklist

After writing the ADR file:

- [ ] Record the ADR file path in the current issue handoff/update note
- [ ] Note the affected `.specs/` files (if any) in the same handoff/update note
- [ ] Confirm `## Created At` exists and follows `YYYY-MM-DD HH:mm KST`
- [ ] Run ADR review using a subagent
- [ ] If ADR review returns blocking findings, fix the ADR and run re-review until blocking findings are cleared
- [ ] Create a follow-up Sudocode Issue via MCP and link it from the current issue (mandatory for every ADR)

---

## 7. ADR Review Timing

- Run ADR review immediately after ADR creation and follow-up issue linking.
- Complete ADR fixes before moving the current issue to `needs_review`.
