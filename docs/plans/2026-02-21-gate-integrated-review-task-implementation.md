# Gate Integrated Review Tasks Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add one gate-level integrated review DEV task to each gate (G1~G6) in `.roadmap/ai_agent_roadmap.md`.

**Architecture:** Keep the existing roadmap format unchanged, and append one new Epic+DEV block at the end of each gate section. Each review DEV depends on all DEV tasks in that gate and uses gate-specific verification level with manual approval.

**Tech Stack:** Markdown, repository roadmap conventions

---

### Task 1: Add G1 integrated review task (DEV-048)

**Files:**
- Modify: `.roadmap/ai_agent_roadmap.md`

**Step 1: Insert new Epic/DEV block before G2 separator**

```markdown
### Epic: [EPIC-35] G1 게이트 통합 리뷰를 수행한다

#### DEV-048: G1 통합 리뷰를 완료하면 Spec/실행 환경 인터페이스의 개발 가능 상태를 공식적으로 확정할 수 있다
```

**Step 2: Set metadata**

- `priority: P0`
- `verify: L1`
- `approval: manual`
- `depends_on: DEV-001~DEV-008`
- `status: backlog`

**Step 3: Add gate-review DoD checklist**

- Include coverage of gate objective, document impact, unresolved items, and CI pass.

### Task 2: Add G2 integrated review task (DEV-049)

**Files:**
- Modify: `.roadmap/ai_agent_roadmap.md`

**Step 1: Insert new Epic/DEV block before G3 separator**

```markdown
### Epic: [EPIC-36] G2 게이트 통합 리뷰를 수행한다

#### DEV-049: G2 통합 리뷰를 완료하면 감지/수집/리포트 경로의 결정적 동작을 게이트 단위로 확정할 수 있다
```

**Step 2: Set metadata**

- `priority: P0`
- `verify: L2`
- `approval: manual`
- `depends_on: DEV-009~DEV-021`
- `status: backlog`

**Step 3: Add gate-review DoD checklist**

- Same review template adapted to G2 gate statement.

### Task 3: Add G3 integrated review task (DEV-050)

**Files:**
- Modify: `.roadmap/ai_agent_roadmap.md`

**Step 1: Insert new Epic/DEV block before G4 separator**

```markdown
### Epic: [EPIC-37] G3 게이트 통합 리뷰를 수행한다

#### DEV-050: G3 통합 리뷰를 완료하면 LLM 분석/트리아지의 스키마 강제 안전 경로를 게이트 단위로 확정할 수 있다
```

**Step 2: Set metadata**

- `priority: P0`
- `verify: L2`
- `approval: manual`
- `depends_on: DEV-022~DEV-026`
- `status: backlog`

### Task 4: Add G4 integrated review task (DEV-051)

**Files:**
- Modify: `.roadmap/ai_agent_roadmap.md`

**Step 1: Insert new Epic/DEV block before G5 separator**

```markdown
### Epic: [EPIC-38] G4 게이트 통합 리뷰를 수행한다

#### DEV-051: G4 통합 리뷰를 완료하면 HITL 승인/타임아웃/알림 운영 플로우를 게이트 단위로 확정할 수 있다
```

**Step 2: Set metadata**

- `priority: P0`
- `verify: L2`
- `approval: manual`
- `depends_on: DEV-027~DEV-032`
- `status: backlog`

### Task 5: Add G5 integrated review task (DEV-052)

**Files:**
- Modify: `.roadmap/ai_agent_roadmap.md`

**Step 1: Insert new Epic/DEV block before G6 separator**

```markdown
### Epic: [EPIC-39] G5 게이트 통합 리뷰를 수행한다

#### DEV-052: G5 통합 리뷰를 완료하면 실행/검증/롤백/포스트모템 End-to-End 안전 경로를 게이트 단위로 확정할 수 있다
```

**Step 2: Set metadata**

- `priority: P0`
- `verify: L3`
- `approval: manual`
- `depends_on: DEV-033~DEV-039`
- `status: backlog`

### Task 6: Add G6 integrated review task (DEV-053)

**Files:**
- Modify: `.roadmap/ai_agent_roadmap.md`

**Step 1: Append new Epic/DEV block after DEV-047 block**

```markdown
### Epic: [EPIC-40] G6 게이트 통합 리뷰를 수행한다

#### DEV-053: G6 통합 리뷰를 완료하면 LLMOps/배포 구성의 운영 가능 상태를 게이트 단위로 확정할 수 있다
```

**Step 2: Set metadata**

- `priority: P0`
- `verify: L3`
- `approval: manual`
- `depends_on: DEV-040~DEV-047`
- `status: backlog`

### Task 7: Validate roadmap consistency

**Files:**
- Verify: `.roadmap/ai_agent_roadmap.md`

**Step 1: Check new DEV/Epic IDs are unique and sequential**

Run: `rg "DEV-05[0-3]|DEV-048|DEV-049|EPIC-3[5-9]|EPIC-40" .roadmap/ai_agent_roadmap.md`
Expected: each new ID appears in exactly one section header.

**Step 2: Check depends_on ranges per gate**

Run: `rg "DEV-048|DEV-049|DEV-050|DEV-051|DEV-052|DEV-053|depends_on" .roadmap/ai_agent_roadmap.md`
Expected: each review DEV depends on only that gate's DEV range.

**Step 3: Check verify levels match gate risk profile**

Run: `rg "DEV-048|DEV-049|DEV-050|DEV-051|DEV-052|DEV-053|##### verify|L1|L2|L3" .roadmap/ai_agent_roadmap.md`
Expected: G1=L1, G2/G3/G4=L2, G5/G6=L3.
