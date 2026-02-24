---
name: create-sudocode-adr-issue
description: "Publishes a follow-up Sudocode issue for an ADR that was just written. Covers issue creation via sudocode-mcp_upsert_issue, title/tag formatting with ADR-YYYYMMDD-HHMM prefix, DoD checklist generation, and linking to the parent issue."
---

# create-sudocode-adr-issue

## 1. Collect Context

From the current session, identify:

- **ADR identifier** (YYYYMMDD-HHMM) and file path: `docs/adr/YYYYMMDD-HHMM-<slug>.md`
- **ADR decision** — the one-sentence Decision from the ADR
- **ADR rationale** — key open items or follow-up triggers (from the Rationale section)
- **Parent issue ID** — the Sudocode issue that was being worked on when the ADR was created

## 2. Issue Title

```
ADR-YYYYMMDD-HHMM: <imperative phrase describing the follow-up work to be done> (Korean)
```

Example: `ADR-20260225-1430: src/ 통합 기준에 따라 패키징 스크립트를 수정한다`

## 3. Call `sudocode-mcp_upsert_issue`

Parameters:

| Field | Value |
|-------|-------|
| `title` | `ADR-NNNN: <follow-up action>` |
| `priority` | `1` |
| `status` | `open` |
| `tags` | `["adr", "adr:NNNN", "decision-bearing"]` |
| `description` | Body from §4 below |

## 4. Issue Body Template

Write the description in Korean using this structure:

```
배경:
- ADR-NNNN(`docs/adr/NNNN-<slug>.md`)에서 <핵심 결정>을 결정했다.
- <why follow-up tracking is needed — e.g., open items, deferred decisions, re-evaluation triggers>

작업 범위:
1. <specific follow-up task 1>
2. <specific follow-up task 2>

완료 기준 (DoD):
- [ ] <ADR 결정이 실제로 반영됐는지 확인하는 항목 — Implementation gate>
- [ ] <영향받는 .specs/ 문서가 ADR 결정과 일치하는지 확인하는 항목 — Docs gate>
- [ ] <ADR Rationale에서 도출된 추가 항목 (필요 시)>
```

Derive each DoD item from the ADR content. Every checklist must cover two gates:
1. **Implementation gate** — the ADR decision is applied in code/config
2. **Docs gate** — affected `.specs/` files reflect the decision

## 5. Link to Parent Issue

Verify the issue ID returned in §3 is non-empty, then call `sudocode-mcp_link`:

| Field | Value |
|-------|-------|
| `from_id` | new ADR issue ID |
| `to_id` | parent issue ID |
| `type` | `discovered-from` |
