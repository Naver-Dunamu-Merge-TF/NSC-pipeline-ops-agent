---
name: create-pr
description: >
  PR creation workflow for AI agents. Use when you have finished a Sudocode task
  and are ready to open a pull request via gh pr create. Covers pre-flight checks,
  PR body authoring (Change Summary, Document Impact, Unresolved, Session Notes,
  local review signature), ADR trigger criteria, and gh command template.
---

# PR Creation Skill

## 1. Pre-flight Checklist

Before opening a PR, confirm all of the following:

> **L0/L1은 오케스트레이션이 보장한다.** 실행 루프(spec review → code quality review → verification freshness 게이트)를
> 통과한 세션에서 생성된 PR이므로 여기서 재실행하지 않는다.
> 로컬 리뷰 서브에이전트 실행도 오케스트레이션의 code quality review 단계 책임이며,
> create-pr은 그 결과물인 `Reviewed-by:` 서명이 PR body에 포함됐는지만 확인한다.

- [ ] **L2 local sanity** — CI 실패를 미리 방지하기 위한 로컬 sanity run: `.venv/bin/python -m pytest tests/unit/ tests/integration/ --cov=src --cov-fail-under=80`
  > L2/L3 are CI gates that run on GitHub Actions after PR creation. This local run is a sanity check to avoid a predictably failing CI, not a replacement for the CI gate.
  > `tests/integration/`가 아직 없는 경우 해당 경로는 생략 가능 (`tests/unit/` 단독 실행).
- [ ] **L3 (verify:L3 issues only)** — Check the Sudocode Issue `tags` field. If `verify:L3` is set, confirm that the Databricks Dev E2E run (idempotency verified) is expected to pass before creating the PR. If not yet runnable locally, note it in **Unresolved**.
- [ ] **gitleaks** — `gitleaks protect --staged` returns no findings
- [ ] **ADR link gate (decision-bearing only)** — If ADR trigger criteria in §3 apply, confirm an ADR file exists in `docs/adr/` and the ADR link is present in **문서 영향**.
- [ ] **Follow-up issue link gate (decision-bearing only)** — If ADR trigger criteria in §3 apply, confirm a follow-up Sudocode Issue exists and its ID/link is present in **문서 영향**.

Do not proceed if any check fails. Resolve failures first, and use a **Draft PR** only when unresolved blockers remain (see Section 4).

---

## 2. PR Body — Authoring Guide

> **Language rule:** Write all PR body content (변경 요약, 문서 영향, 미결/모호한 점, 세션 요약) in **Korean**.
> Keep section header names exactly as shown in the template below (Korean).
> Exception: code, commands, file paths, and proper nouns (Sudocode, etc.) stay as-is.

Write the PR body following the five-section Minimum Contract. Save to a temp file before passing to `gh`:

```bash
cat > /tmp/pr-body.md << 'EOF'
## 변경 요약

<!-- 무엇을 왜 변경했는지. diff가 보여주는 내용이 아닌 이유와 맥락에 집중한다.
     Sudocode Issue ID를 반드시 명시한다 (예: EPIC-05).
     "Closes #NNN" 문법은 사용하지 않는다 — 이 프로젝트는 GitHub Issues가 아닌
     Sudocode Issues (.sudocode/issues/)로 이슈를 관리하며, #NNN은 해당 시스템과 무관하다. -->

Sudocode Issue: <issue-id>

<이 PR이 해결하는 문제나 요구사항을 설명한다>

## 문서 영향

<!-- 이 변경이 영향을 줄 수 있는 .specs/ 파일을 모두 나열한다.
     ADR 작성 트리거 기준에 해당하면 (skills/create-pr/SKILL.md §3 참고) ADR을 먼저 작성하고 여기에 링크한다. -->

- `.specs/<file>.md` — <어떤 부분에 영향을 주는지 간략히>

ADR: <!-- 작성했으면 링크, 없으면 "없음" -->

Follow-up Issue: <!-- 작성했으면 Sudocode Issue ID/링크, 없으면 "없음" -->

## 미결/모호한 점

<!-- Spec에 근거가 없거나 에이전트가 임의로 판단한 부분을 기재한다.
     블로커가 있으면 Draft PR으로 전환한다. -->

- 없음

## 세션 요약

<!-- 운영 지표 수집용 필수 필드 (weekly_report.py가 참조한다): -->
- 실행 루프 반복 횟수: <!-- N회 -->
- L0/L1 실패 항목: <!-- 있으면 기재, 없으면 "없음" -->
- Draft PR 여부: <!-- 아니오 / 예 (사유: ...) -->
- 사람 개입: <!-- 없음 / 있었다면 어떤 판단이 필요했는지 -->

<!-- 추가 관찰: 시도한 접근법, 기각한 대안, 주요 결정 사항 -->

## 로컬 리뷰 서명

Reviewed-by: review-subagent (local)
EOF
```

---

## 3. ADR Trigger Criteria

Write `docs/adr/NNNN-title.md` (see `skills/create-adr/SKILL.md` for full authoring guide) and link it in **Document Impact** if any of the following apply:

- A design decision diverges from what existing `.specs/` documents specify
- You chose one approach over multiple valid alternatives and the tradeoff needs to be recorded
- The change introduces a breaking interface modification or backwards-incompatible behavior
- The decision has direct security or performance implications
- ADR가 필요한 "in-session decision"이 있었다면, 해당 결정의 후속 추적을 위한 Follow-up Sudocode Issue도 반드시 생성하고 **문서 영향**에 ADR과 함께 링크한다.

When in doubt, write the ADR. It is cheaper to document than to re-litigate later.

---

## 4. gh pr create Command

**Standard PR:**

```bash
gh pr create \
  --title "<Issue ID>: <one-line description of why, not what>" \
  --body-file /tmp/pr-body.md \
  --label "ai-generated"
```

**Draft PR** (use when Unresolved items are blocking):

```bash
gh pr create \
  --title "<Issue ID>: <description> [WIP]" \
  --body-file /tmp/pr-body.md \
  --label "ai-generated" \
  --draft
```

> **Title guidance:** State the *why*, not *what*.
> Bad: `Add retry logic to pipeline executor`
> Good: `Pipeline executor was dropping transient network errors silently`

---

## 5. Post-PR: Sudocode Issue Status Update

Immediately after creating the PR, record the issue state via Sudocode MCP. Do NOT set `closed` directly — `closed` transition happens after PR merge, outside the agent session.

```
sudocode.update_issue("<issue-id>", {
  "status": "in_progress",
  "description": "<reflect DoD checklist progress — mark completed items with [x]>"
})
```

> Skipping this update delays Sudocode DAG recalculation and postpones the next Ready Issue from becoming available.

---

## 6. Non-negotiable Rules

| Rule | Detail |
|------|--------|
| No `--no-verify` | Never bypass pre-commit hooks |
| No secrets | Never include `.env` files or real credentials. Use `PLACEHOLDER` in examples |
| 로컬 리뷰 서명 필수 | PR body must contain `Reviewed-by: review-subagent (local)` — Auto-Merge will reject without it |
| `.specs/` or `docs/adr/` changes | Auto-Merge is disabled automatically for these paths; flag for manual approval in PR body |
| Decision-bearing doc gate | No ADR-only / no issue-only for decision-bearing changes — both ADR and Follow-up Issue links are required |
| Scope | 1 Task = 1 Issue = 1 PR. Do not bundle unrelated changes |
