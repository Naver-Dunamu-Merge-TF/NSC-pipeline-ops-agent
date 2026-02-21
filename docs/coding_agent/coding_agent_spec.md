# Coding Agent Spec

> 새 프로젝트에 적용할 Spec-driven + AI 자동화 개발 워크플로 구상.
> 향후 구체화를 위한 참조 문서.

---

## 1. 개요

### 목적

사람은 **설계와 판단**에 집중하고, AI(에이전트 팀)와 자동화 시스템(Sudocode)이 **실행과 검증**을 담당하는
개발 워크플로를 구축한다.

### 기존 방식의 한계

대화형 AI 코딩은 빠른 프로토타이핑에는 유용하지만, 프로젝트가 커질수록 다음과 같은 구조적 문제가 드러난다.

- **맥락 유실과 재현성의 부재** — 대화 기반 작업은 히스토리가 흩어지고, 왜 그렇게 결정했는지 추적할 수 없다. 같은 결과를 다시 만들어내기도 어렵다.
- **자기 검증의 구조적 한계** — 코드를 작성한 모델이 같은 맥락에서 스스로 리뷰하면, 자기 변호에 빠지기 쉽다. 독립적인 검증 단계가 없으면 오류가 그대로 통과된다.
- **사람이 병목이 되는 마이크로매니징** — 매 단계마다 사람이 직접 지시하고 확인해야 하므로, 인지 부하가 급격히 늘어난다. 스스로 정한 작업 루틴조차 빼먹는 휴먼 에러가 생기고, 결국 사람이 전체 흐름의 병목 지점이 된다.

### 워크플로 요약

이 문서가 제안하는 워크플로는 5단계 파이프라인으로 구성된다.

1. **Spec 작성** — 사람이 요구사항과 설계 의도를 문서로 정의한다.
2. **Roadmap 분해** — Spec을 기반으로 실행 가능한 태스크 단위로 쪼갠다. 어떤 순서로 무엇부터 할지는 Sudocode가 알아서 정리한다.
3. **자동 실행** — AI(에이전트 팀)가 구현·테스트·PR 생성까지 자동으로 수행한다. 문제가 있으면 최대 5번까지 자동 루프를 돌며 스스로 수정한다.
4. **사람 리뷰** — 사람은 결과물만 확인하고, 승인 또는 피드백을 준다.
5. **반복** — 리뷰가 끝나면 Sudocode가 다음 태스크를 자동으로 할당한다. 이 사이클이 계속 돌면서 제품이 만들어진다.

### 기대 효과 및 이점

- **사람은 설계와 판단에 집중** — 반복적인 실행 작업을 AI에 위임하여, 사람은 가장 가치 있는 의사결정에만 시간을 쓴다.
- **독립적 검증으로 품질 확보** — 작성과 리뷰를 분리하고, 자동 루프를 통해 사람 손을 타기 전에 신뢰성을 확보한다.
- **모든 결정이 추적 가능** — 설계 의도는 Spec에, 실행 이력은 Issue에, 중간 판단은 ADR에 남아 누구든 맥락을 따라갈 수 있다.


### 핵심 원칙

- Spec 문서(`.specs/`)가 도메인 **규범(intent)**의 SSOT, 코드에서 자동 생성된 문서(`docs/generated/`)는 **사실(fact)** 참조용(읽기 전용)
- 사람의 판단이 필요한 경계와, 자동화 가능한 경계를 명확히 분리
- 태스크의 품질(구체성)이 자동화 성패를 결정

### 사람의 역할 (3가지만)

1. **Spec 작성**: 도메인 요구사항, 스키마, 설계 의도 정의
2. **Roadmap 관리**: 태스크 분해, 우선순위, 의존성 정의
3. **PR 리뷰**: AI가 만든 결과물의 품질 판단

나머지(태스크 선택, 실행 순서 결정, Issue 생성, 브랜치, 구현, 테스트, 상태 추적)는 자동화한다.

---

## 2. 아키텍처: Spec → Roadmap → Issue 파이프라인

### 3-Layer 구조

```
계층           역할                    누가 관리      변경 빈도
─────────────────────────────────────────────────────────────
Spec           도메인 정의 (SSOT)       사람           낮음
Roadmap        실행 계획 수립           사람           중간
Issue          실행 단위 배포           Sudocode 관리  높음
```

### 각 계층의 책임

| 계층 | 담는 것 | 담지 않는 것 |
|------|---------|-------------|
| Spec | 스키마, 비즈니스 규칙, 설계 의도, 임계값 근거 | 실행 순서, 우선순위 |
| Roadmap | 태스크 목록, 우선순위(P0/P1/P2), 의존성, Gate, 검증 레벨, DoD | 도메인 정의 |
| Issue | 태스크 1개의 실행 컨텍스트 (대상 파일, 커맨드, 체크리스트) | 전체 계획 |

### 로드맵 계층 구조: Gate → Epic → Task

| 계층 | 역할 | GitHub 매핑 |
|------|------|-------------|
| **Gate** | 단계별 도달 목표. "이 상태가 되어야 다음으로" | Sudocode tags(`gate:G1`) |
| **Epic** | 하나의 모듈/서비스가 완성되는 기능 묶음 | Sudocode Issue (priority + tags) |
| **Task** | 하나의 기능이 동작하는 상태를 만드는 변경 | Sudocode Issue 1개 = PR 1개 |

**분해 방식 — 모든 단계에서 AI가 초안 제안, 사람이 조정/승인:**

| 단계 | AI | 사람 |
|------|-----|------|
| Spec → Gate | Spec 읽고 Gate 초안 제안 | "이건 합쳐", "이건 빼" 판단 후 확정 |
| Gate → Epic | Gate + Spec 읽고 Epic 초안 제안 | 검토/수정 후 확정 |
| Epic → Task | Epic + Spec + 코드 읽고 **기능 단위** Task + DoD 초안 제안 | 완료 조건 검토/수정 후 확정. 내부 분해는 에이전트에 위임 |

**Task = "하나의 기능이 동작하는 상태"를 만드는 변경 단위**

- 1 Task = 1 Issue = 1 PR
- Task는 **"~하면 ~된다"** 한 문장으로 완료 상태를 설명할 수 있는 크기
- 완료 조건(DoD)에 **검증 항목을 복수로** 나열하고, 전부 통과해야 Task 완료
- 내부 분해(어떤 파일을 어떤 순서로 수정하는지)는 작업 에이전트에게 위임

**적절한 크기의 판단 기준:**

| 질문 | 예 → 적절 |
|------|----------|
| 한 문장으로 설명 가능한가? | "threshold 기능이 파이프라인에 적용되어 동작한다" |
| 이 PR만 머지해도 기존 기능이 깨지지 않는가? | 독립적으로 머지 가능 |
| DoD의 검증 항목을 전부 테스트로 커버할 수 있는가? | 기능의 핵심 경로 + 경계값 + 기존 회귀 = 복수 테스트 |

**너무 크다는 신호:** 설명에 "그리고"가 2번 이상 / 관련 없는 도메인 개념이 섞임
**너무 작다는 신호:** 의미 있는 행동 변화가 없음 / 다음 태스크 없이는 쓸모없는 변경

### 로드맵 포맷: Markdown

- Roadmap은 **Markdown**으로 관리한다.
- Gate → Epic → Task 계층을 헤딩(`##`, `###`, `####`)으로 구분하고, 각 태스크의 필드(priority, verify, approval, source_doc, depends_on, status, DoD)는 `#####` 헤딩으로 구분하여 태스크 블록 단위로 작성한다.
- 사람과 LLM 모두 Markdown을 직접 읽고 수정한다. 별도의 포맷 변환이나 자동 렌더링이 불필요하다.
- GitHub에서 바로 렌더링되므로 가독성이 높다.

### 자동화 경계 (Sudocode 기반)

```
사람 영역                                     자동화 영역
─────────────────────────────────────────────────────────────────────
Spec 작성 ──→ Sudocode에 Issue DAG 등록 ──→ │ Sudocode가 Ready Issue 판별 (위상 정렬)
                                           │ Sudocode 데몬이 `sudocode-mcp_ready`로 자동 디스패치
                                           │ 에이전트가 worktree에서 자동 스폰
                                           │ 구현 + CI 자동 검증
                                PR 리뷰 ←──│
                                           │ Merge
                                           │ 에이전트가 MCP로 체크리스트(DoD) 진행 상황 기록
                                           │ PR 머지 시 데몬이 Issue status → closed
                                           │ Sudocode 데몬이 후속 Issue blocker 자동 해소
```

### Issue 관리: Sudocode 기반 오케스트레이션

GitHub Issues를 사용하지 않는다. 대신 **Sudocode**가 Issue(에픽/태스크)를 `.sudocode/issues/`에 구조화된 JSONL로 관리하고, DAG 기반 의존성 추적 + 에이전트 디스패치를 수행한다.

**흐름:**
1. 로드맵 동기화: Sudocode 데몬이 `.roadmap/roadmap.md` 변경을 감지하여 Issue 및 `blocks` 관계를 점진적(incremental)으로 upsert
2. `sudocode server` 데몬 실행
3. Sudocode가 Ready 상태 Issue를 자동 감지 (`sudocode-mcp_ready` 폴링) → worktree 할당 + 에이전트 자동 스폰
4. 에이전트가 MCP로 Issue 체크리스트 조회 + Spec `[[참조]]`로 컨텍스트 확보
5. 구현 완료 후 PR 생성 (`gh pr create` 시 본문에 Sudocode Issue ID 명시)
6. PR 머지 시 Sudocode 데몬이 Issue를 closed 처리하고 후속 Issue의 blocker를 자동 해소 → 새 Ready Issue 발생 (무한 루프)

**Sudocode Issue의 역할**: 실행 컨텍스트의 중앙 저장소이자 의존성 DAG의 노드. 에이전트가 MCP로 직접 읽고 상태를 업데이트하므로, Issue 내용과 실제 작업 컨텍스트가 항상 일치한다.

**장점:**
- 의존성 기반 자동 실행 순서 결정 (위상 정렬)
- worktree 자동 생성 + 에이전트 스폰 (수동 `git worktree add` 불필요)
- 실시간 모니터링 (웹 UI 칸반보드)
- Spec ↔ Issue 양방향 링크 (`[[SPEC-001]]`)
- Git 네이티브 — 추가 인프라/API 키 불필요

### Roadmap → Sudocode Issue 반영 방식

로드맵 변환은 **지속적**으로 수행된다. Sudocode 데몬이 로드맵 마크다운의 변경을 감지(watch)하여 에이전트를 통해 Sudocode Issue를 점진적으로 생성/수정(upsert)한다.

**Sudocode Issue 필드 매핑:**

| Roadmap 필드 | Sudocode Issue 필드 | 비고 |
|-------------------|---------------------|------|
| `epic_id` | `id` | `EPIC-01` 형태 |
| Epic 제목 | `title` | |
| `priority` | `priority` | P0→1, P1→2, P2→3 |
| `verify` | `tags` | `verify:L2` |
| Gate 소속 | `tags` | `gate:G1` |
| `source_doc` | `implements` 관계 | `[[SPEC-001]]` 링크 |
| `depends_on` | `blocks` 관계 | DAG 엣지 |
| `status` | `status` | open/in_progress/blocked/closed |
| DoD 체크리스트 | `description` | 마크다운 체크리스트 |

### 동기화 방향: Sudocode가 SSOT

- **현행**: Sudocode가 Issue 상태의 SSOT. 에이전트가 MCP로 상태를 업데이트하면 Sudocode가 DAG를 재계산한다.
- Roadmap 마크다운은 **참조 문서**로 유지하되, 실시간 상태 추적은 Sudocode에 위임한다.
- Sudocode의 `.sudocode/` 디렉토리가 Git에 커밋되므로 상태 이력이 자동으로 보존된다.

### 진행률 추적: Sudocode 웹 UI + Roadmap

- Gate의 진행도는 **Sudocode 칸반보드**에서 실시간 확인한다.
- Sudocode의 `get_ready_issues()` API로 현재 실행 가능한 Issue 목록을 조회할 수 있다.
- 주간 리포트 스크립트는 Sudocode의 Issue 상태 + GitHub PR 상태를 대조하여 진행률을 산출한다.

---

## 3. 에이전트 실행 방식: 로컬 자동화 (Sudocode 오케스트레이션)

### 도구 및 환경

- **도구**: superpowers 기반 스킬 중심 코딩 에이전트
- **실행 환경**: 로컬 터미널
- **실행 모드**: 스킬 체인 오케스트레이션

**표준 스킬 체인 상세:**
- `brainstorming`: 요구사항 정리, 가정 명시, 대안 비교
- `writing-plans`: 실행 순서와 검증 커맨드를 문서로 고정
- `test-driven-development` 또는 `systematic-debugging`: 구현/수정 루프 수행
- `verification-before-completion`: 완료 주장 전 검증 결과 확인
- `requesting-code-review`: 로컬 리뷰 수행 및 리스크 확인
- `create-pr` / `create-adr`: 산출물 생성 및 미결사항 기록
- **최대 5회 반복** 후 자동 종료. 5회 내 미완료 시 현재 상태를 Draft PR로 제출하고 사람에게 넘김
- 안전장치:
  - `AGENTS.md`에 "동일 테스트 5회 연속 실패 시 중단, 미결 항목 기록 후 Draft PR 생성" 규칙 명시
  - 런타임 수동 중단 명령으로 언제든 중단 가능

### 흐름

Sudocode 데몬이 `sudocode-mcp_ready`로 태스크 폴링 → Ready Issue 감지 시 에이전트 자동 스폰 → 코드 구현 감독 → 결과 확인 후 PR 생성

완전 자동화 루프를 가동하되, 에이전트 팀의 실제 성능 검증 및 예외 상황(무한 루프 등)을 방지하기 위해 최대 5회 반복 후 중단하는 안전장치를 두어 루프 내 관찰이 가능하게 한다.

### 컨텍스트 주입: 점진적 개선 방식

- 로컬 실행이므로 에이전트가 레포 전체에 직접 접근 가능. 별도의 컨텍스트 주입 파이프라인은 불필요.
- 에이전트가 어떤 파일을 참고해야 하는지 헤매면 사람이 즉시 개입.
- **사전 설계가 아니라 운영 중 점진 개선** 방식을 택한다.

### 병렬 실행: git worktree 활용

의존성이 없는 태스크는 `git worktree`를 사용하여 병렬로 실행할 수 있다.

**전제 조건:**
- 두 태스크 간 `depends_on` 관계가 없을 것
- `affected_files`가 겹치지 않을 것 (겹치면 순차로 전환)

**흐름:**
1. Sudocode 오케스트레이터가 DAG를 분석해 의존성 없는 Ready Issue N개를 감지한다
2. 오케스트레이터가 태스크별 worktree를 자동 생성한다:
   ```bash
   git worktree add ../repo-{task_id} -b feat/{task_id}
   ```
3. 각 worktree에서 독립된 에이전트 세션을 병렬로 자동 스폰한다
4. 각 에이전트가 독립적으로 코드 구현 → 결과 확인 후 PR 생성
5. PR merge는 **먼저 완료된 순서대로 순차 처리**한다
6. 작업 완료 후 오케스트레이터가 worktree를 정리한다:
   ```bash
   git worktree remove ../repo-{task_id}
   ```

**장점:**
- 에이전트별 물리적으로 분리된 working directory → 작업 중 충돌 없음
- 브랜치 전환 오버헤드 없음
- `.venv` 등 환경도 worktree별 독립 가능
- 복잡한 락 추가 인프라 없이도 로컬 워크트리로 격리 보장

**제약:**
- Sudocode가 에이전트 스폰 시 작업 큐를 통해 상태 업데이트 충돌이나 중복 실행 방지(클레임) 로직을 처리해야 함
- merge 시점에 예상치 못한 충돌 발생 시 사람이 판단하여 해결

---

## 4. 전체 자동화 루프

### 흐름

```
Spec 문서
  │
  ▼  (분해)
Roadmap (Markdown)
  │
  ▼  (Sudocode가 Ready Issue 감지 → 에이전트 자동 스폰)
에이전트 팀이 Spec + Roadmap 참조하여 작업 컨텍스트 파악
  │
  ▼  (같은 세션에서 바로)
브랜치 생성 + 코드 구현
  │
  ▼  (에이전트 팀)
PR 생성 (PR 본문에 Sudocode Issue ID 명시)
  │  - 변경 요약 + 문서 영향 + 미결/모호한 점 포함
  │
  ▼  (GitHub Actions)
CI 자동 검증 (verification_level에 따라 L2/L3)
  │
  ▼  
PR 리뷰 (최종 판단)
  │
  ▼  (GitHub)
Merge → Issue 자동 close
  │
  ▼  (필요 시)
미결 항목 → ADR 승격 또는 Spec 수정 태스크 추가
```

### Verification Level: 로컬 vs CI 분리

**로컬 (에이전트 작업 중, 반복 실행)**

| Level | When | Duration | Command | Pass Criteria |
|-------|------|----------|---------|---------------|
| L0 | Per edit | < 30s | `python -m py_compile` | No syntax errors |
| L1 | Pre-commit | < 2min | `.venv/bin/python -m pytest tests/unit/ -x` | All unit tests pass |

**CI (PR 이후, 1회 실행)**

| Level | When | Duration | Command | Pass Criteria |
|-------|------|----------|---------|---------------|
| L2 | Pre-PR | < 10min | `.venv/bin/python -m pytest tests/unit/ tests/integration/ --cov=src --cov-fail-under=80` | 80%+ coverage |
| L3 | Pre-merge | < 30min | Databricks Dev E2E | Idempotency verified |

- Issue의 `verification_level` 라벨은 **"CI에서 어디까지 통과해야 머지 가능한가"**를 의미.
- `verify:L2` → 커버리지 + 통합테스트 통과 시 머지 가능
- `verify:L3` → E2E까지 통과해야 머지 가능
- 로컬의 L0/L1은 모든 태스크에 기본 적용이므로 **라벨을 정의하지 않는다** (`verify:L1` 라벨 없음).

### Auto-Merge (자동 머지) 정책

검증(verify)과 승인(approval) 정책을 분리하여 관리한다.

- `approval: manual` (기본): CI 통과 후 사람이 PR 리뷰 및 머지
- `approval: auto`: CI 통과 및 **AI 리뷰 봇의 명시적 승인(APPROVE)** 시 GitHub Actions가 자동 머지 (`gh pr merge --auto`)

**AI 리뷰 승인의 기준 (Shift-Left 로컬 리뷰어):**
- 클라우드 API(GitHub Actions)에서 무거운 LLM을 호출하여 리뷰 비용을 발생시키지 않는다.
- 대신, 코드를 작성한 작업 에이전트가 PR을 올리기 **직전에 로컬 환경에서 리뷰 에이전트(Momus)를 호출**하여 코드 품질과 Spec 준수 여부를 무료로 상호 검증한다.
- Momus가 통과시키면, PR 본문에 `Reviewed-by: Momus (Local)` 서명을 포함하여 PR을 생성한다.
- GitHub Actions는 LLM을 돌리지 않고, 1) CI(테스트) 통과 여부, 2) PR 본문의 서명 존재 여부, 3) `git diff`상 위험 파일 변경 여부만을 **기계적(Rule-based)으로 검사**한다.
- 모든 조건이 맞으면 GitHub이 제공하는 기본 토큰(`GITHUB_TOKEN`)을 사용해 `gh pr review --approve` 도장을 찍고 즉시 자동 머지한다.

**Fallback (안전장치) 및 상태 전이:**
- 에이전트의 PR 본문(자율 신고)에 의존하지 않고, **CI 단계에서 `git diff`를 기계적으로 검사**한다.
- `docs/adr/*` (새로운 설계 결정) 또는 `.specs/*` (스펙 변경) 파일의 수정이 감지되면 자동 머지를 즉시 중단한다.
- 강제 강등 절차: CI가 `gh pr merge --disable-auto`를 실행하여 머지 예약을 취소하고, PR에 `needs-review` 라벨을 부착하여 `approval: manual` 상태로 강등시켜 사람의 리뷰를 강제한다.

### Spec 변경 cascading

- 특별한 cascading 처리를 만들지 않는다.
- Spec이 바뀌면 그 변경분 자체가 새로운 태스크가 된다.
- **흐름**: Spec 수정 → Roadmap에 수정 태스크 추가 → 기존 파이프라인 그대로 탄다.
- 진행 중인 작업이 변경된 Spec과 충돌하면, 사람이 판단해서 중단하고 새 Issue로 전환.

### Gate 통과 조건: 사람 승인

- Milestone의 모든 Issue가 closed되어도 Gate가 자동 통과되지 않는다. 사람이 명시적으로 승인해야 다음 단계로 넘어간다.
- GitHub Milestone을 사람이 직접 close하는 행위가 곧 Gate 승인이다.
- Gate는 PR 리뷰의 상위 버전. 개별 태스크가 아닌 단계 전체의 품질/완성도를 사람이 판단.

---

## 5. Sudocode Issue: 에이전트 작업 컨텍스트

GitHub Issues 대신 **Sudocode Issue**가 에이전트의 작업 지시서 역할을 한다. Issue는 `.sudocode/issues/issues.jsonl`에 구조화된 형태로 저장되며, 에이전트가 MCP로 직접 조회한다.

**Sudocode Issue 포맷:**

| 필드 | 설명 | 예시 |
|------|------|------|
| `id` | 에픽/태스크 식별자 | `EPIC-05` |
| `title` | 작업 제목 | `프로젝트 스켈레톤 + LangGraph 골격을 구축한다` |
| `description` | DoD 체크리스트 (마크다운) | `- [ ] graph/ 기본 뼈대가 생성돼 있다...` |
| `priority` | 1(P0) / 2(P1) / 3(P2) | `1` |
| `status` | open / in_progress / blocked / closed | `open` |
| `tags` | Gate, verify level | `["gate:G2", "verify:L1"]` |
| `blocks` 관계 | 후속 에픽 의존성 | `EPIC-09, EPIC-10` |
| `implements` 관계 | 연결된 Spec | `[[SPEC-001]]` |

**에이전트 컨텍스트 조회 흐름:**
```
에이전트 → sudocode.get_issue("EPIC-05")
  → title, description(DoD), implements(Spec 링크) 수신
  → Spec 내용은 [[SPEC-001]] 참조로 확인
  → 구현 시작
```

**설계 원칙:**
- description에 DoD 체크리스트가 포함되어 에이전트가 완료 조건을 직접 확인 가능.
- implements 관계로 Spec을 자동 참조하므로 프롬프트에 Spec 경로를 수동 삽입할 필요 없음.
- blocks 관계는 Sudocode 서버가 자동으로 Ready/Blocked 상태를 결정.
- 추적용 메타데이터(priority, tags, status)는 **Sudocode가 SSOT(단일 진실 원천)**로서 관리한다. GitHub 라벨(`approval:auto` 등)은 CI 실행을 위해 Sudocode Issue tag를 그대로 미러링(동기화)한 것에 불과하다.

---

## 6. 문서 자동화 전략

### 핵심 문제

코드가 변경되면 문서가 따라가지 못한다 (documentation drift).
"문서 업데이트하세요"라는 규칙은 작동하지 않는다. 구조로 해결해야 한다.

### 사실(Fact) vs 의도(Intent) 구분

| 구분 | 예시 | 자동화 |
|------|------|--------|
| 사실 | 컬럼명, 타입, 함수 시그니처, 의존성 그래프 | 코드에서 추출 가능 |
| 의도 | "왜 이 설계인가", "왜 이 임계값인가", 운영 절차 | 사람만 작성 가능 |

**원칙: 사실은 생성하고, 의도는 작성한다.**

### 문서 영향 분석 및 PR 리뷰: 3단계 구조

별도의 "문서 영향 분석 AI"를 구축하지 않는다. 대신 3단계로 처리한다.

**1단계 — PR 생성 시 (작업 에이전트가 자기 판단으로 작성)**

작업을 수행한 에이전트가 가장 깊은 컨텍스트를 가지고 있으므로, PR body에 문서 영향과 모호한 점을 직접 기록한다.

PR body 구조:
```markdown
## 변경 요약
<!-- 무엇을 왜 변경했는지 -->

## 문서 영향
<!-- 이 변경이 영향을 줄 수 있는 Spec/문서. 없으면 "없음" -->
- `.specs/data_contract.md`: amount 컬럼 타입이 decimal로 변경됨, Spec 업데이트 필요

## 미결/모호한 점
<!-- Spec에 근거가 없거나 에이전트가 임의로 판단한 부분. ADR을 작성했으면 번호를 달아둔다. -->
- threshold 기본값 0.05는 Spec에 명시적 근거 없음 → ADR-0002
- retry 상한 미정, 현재 임의로 5회 설정 → ADR-0003

## 세션 요약
<!-- 에이전트가 자동 기재. GitHub에 남기지 않으면 사라지는 세션 수준 정보. -->
- 실행 루프 반복 횟수: N회
- L0/L1 실패 항목: (있으면 기재, 없으면 생략)
- Draft PR 여부: 아니오 / 예 (사유: ...)
- 사람 개입: 없음 / (있으면 어떤 판단이 필요했는지)

## 로컬 리뷰 서명
<!-- 에이전트 간(작업 에이전트 → Momus) 사전 리뷰 통과 증빙 -->
- Reviewed-by: Momus (Local)
```

**2단계 — PR 자동 리뷰 (Shift-Left: 로컬 에이전트 사전 리뷰)**

- 클라우드 API 호출 비용을 줄이기 위해, 클라우드 LLM 리뷰 대신 **로컬 환경의 superpowers 기반 리뷰 에이전트(Momus 등)**가 코드를 사전에 검증한다.
- 작업 에이전트가 로컬에서 코드 수정을 완료하면, PR 생성 직전에 리뷰 에이전트를 호출해 `AGENTS.md`의 `## Review guidelines` 기준으로 코드를 검사받는다.
  - `.specs/` 문서와의 정합성 확인
  - 프로젝트 코딩 컨벤션 준수 여부
  - 보안/시크릿 노출 여부
- 리뷰 에이전트가 통과시키면, PR 본문 하단에 `Reviewed-by: Momus (Local)` 서명을 포함하여 `gh pr create`를 실행한다.
- GitHub Actions에서는 더 이상 무거운 LLM 코멘트 리뷰를 수행하지 않고, 이 서명의 존재 여부만 기계적으로(Rule-based) 파악한다.

**3단계 — 사람 리뷰 (최종 판단)**

- 에이전트의 문서 영향 보고와 로컬 리뷰 결과를 참고하여 최종 판단.
- drift 감지 CI가 코드 vs Spec 스키마의 기계적 불일치를 추가로 잡는다.

### 보조 수단

| 수단 | 설명 | 우선순위 |
|------|------|----------|
| Drift 감지 CI | **규범(`.specs/`) → 구현(code)** 단방향 비교, 불일치 시 CI 실패 | 높음 (PR 차단) |
| 사실 문서 자동 생성 | 코드에서 스키마/API 문서 추출 → `docs/generated/` (읽기 전용) | 중간 |

### SSOT 분리 원칙

| 계층 | 경로 | 성격 | 관리 |
|------|------|------|------|
| **규범 (Intent)** | `.specs/` | 도메인 규칙, 계약, 설계 의도 | 사람이 작성·유지 |
| **사실 (Fact)** | `docs/generated/` | 코드에서 추출한 스키마, API 레퍼런스 | 자동 생성, 읽기 전용 |

- 두 계층을 물리적으로 분리하여 "무엇이 SSOT인지" 모호해지는 상황을 방지한다.
- Drift 감지는 **규범(spec) → 구현(code)** 한 방향으로만 수행한다. `docs/generated/`는 코드에서 매번 재생성되므로 drift 대상이 아니다.

---

## 7. ADR 프로세스: PR 미결사항의 중앙 집적

PR body의 "미결/모호한 점"이 PR별로 파편화되는 것을 방지하기 위해, ADR(Architecture Decision Records)을 중앙 저장소로 운영한다.

**저장 위치**: `docs/adr/`

```
docs/adr/
  0001-yaml-roadmap-format.md
  0002-threshold-default-policy.md
  ...
```

**ADR 구조:**

```markdown
# ADR-0002: threshold 기본값 정책

## 상태
승인됨 / 제안됨 / 폐기됨

## 맥락
PR #42에서 threshold 기본값을 0.05로 설정했으나 Spec에 근거 없음.

## 결정
업계 표준 값 0.05를 기본으로 하되, 프로젝트별 override 가능하게 파라미터화.

## 근거
[왜 이 결정을 했는지]
```

**ADR 생성 트리거**: 에이전트 팀이 작업 중에 자율적인 판단 하에 생성

**분류 기준:**
- Spec 업데이트로 해결되는 것 → Roadmap에 Spec 수정 태스크로 추가
- 설계 결정이 필요한 것 → ADR로 승격


---

## 8. AI 생성 산출물 일람

### 생성 원칙: LLM 스킬 통합 (모델 불문)

워크플로에서 AI가 생성하는 구조화된 산출물(PR, ADR)은 **LLM 스킬**을 통해 작성한다. 각 산출물마다 전용 스킬(`skills/create-pr/SKILL.md`, `skills/create-adr/SKILL.md`)을 프롬프트 템플릿으로 정의하여 일관된 인터페이스로 관리한다.

- Issue는 Sudocode가 관리하므로 별도 LLM 스킬이 불필요하다. 로드맵 → Sudocode 변환은 데몬에 의해 지속적으로 동기화된다.
- PR과 ADR은 자연어 해석과 구조화된 포맷 생성이 필요하므로, LLM 스킬을 유지한다.
- LLM 스킬은 프롬프트 템플릿이며, 실제 호출 모델은 실행 환경에서 선택(GPT/Claude 등)한다. 특정 모델에 종속되지 않는다.

### 산출물 목록

워크플로에서 AI 또는 자동화가 생성하는 모든 문서/산출물을 정리한다.

**에이전트 팀이 세션 중 생성하는 산출물:**

| 산출물 | 시점 | 저장 위치 | 설명 |
|--------|------|----------|------|
| Sudocode Issue 상태 업데이트 | 세션 중/종료 시 | `.sudocode/issues/` | 에이전트가 MCP로 체크리스트 진행 상황 기록 (status는 PR 머지 시 데몬이 closed로 변경) |
| PR | 세션 종료 시 | GitHub Pull Requests | 변경 요약, 문서 영향, 미결/모호한 점을 PR body 구조에 맞게 생성 → `gh pr create` |
| ADR 초안 | 작업 중 자율 판단 | `docs/adr/` | 설계 결정이 필요한 항목을 ADR 템플릿으로 작성. 사람은 "결정"과 "근거"만 채움 |

**자동화 파이프라인이 생성하는 산출물:**

| 산출물 | 트리거 | 저장 위치 | 설명 |
|--------|--------|----------|------|
| 주간 리포트 | 주 1회 (GitHub Action 또는 수동) | `docs/reports/YYYY-WNN.md` | Sudocode + GitHub API에서 운영 지표 자동 추출 |

### 산출물별 템플릿

#### Roadmap Markdown

```markdown
<!-- .roadmap/roadmap.md -->

## G1: Secure Binding Ready (due: 2026-03-01)

### Epic: Pipeline B 구축

#### DEV-001: threshold 검증을 파이프라인에 통합한다

##### priority
P0

##### verify
L2

##### approval
manual

##### source_doc
`.specs/data_contract.md`

##### depends_on
-

##### status
backlog

##### DoD
- [ ] build_supply_balance_daily에 threshold 파라미터 추가
- [ ] 파이프라인 실행 시 threshold 초과 row 필터링 동작
- [ ] 경계값 테스트 (초과/미만/정확히 같음)
- [ ] 기존 테스트 전체 통과

#### DEV-002: ...

##### priority
P1

##### verify
L2

##### approval
manual

##### source_doc
`.specs/data_contract.md`

##### depends_on
DEV-001

##### status
backlog

##### DoD
- [ ] ...
```

**필드 설명:**

| 필드 | 필수 | 설명 |
|------|------|------|
| `task_id` (헤딩 prefix) | ✅ | 안정적 식별자. Issue 제목 prefix, 의존성 참조에 사용 |
| `title` (헤딩 suffix) | ✅ | 태스크 한 줄 설명 |
| `priority` | ✅ | `P0` / `P1` / `P2` |
| `verify` | ✅ | CI 머지 게이트 레벨 (`L2` / `L3`) |
| `approval` | ✅ | 승인 주체 및 방식 (`manual` / `auto`) |
| `source_doc` | ✅ | 근거 Spec 문서 경로 |
| `depends_on` | ✅ | 의존하는 task_id (없으면 `-`) |
| `status` | ✅ | `backlog` / `in-progress` / `done` |
| `DoD` | ✅ | 완료 조건 목록. 체크리스트(`- [ ]`) 형태로 기재 |
| `affected_files` | ❌ | 수정/생성 대상 파일. 사전 특정 불가 시 생략 가능 (`#####` 헤딩 추가) |

#### Issue body

```markdown
## 목표
<!-- 이 태스크가 완료되면 무엇이 달라지는지. 한두 문장. -->

## Spec 참조
<!-- 근거가 되는 Spec 문서 경로. 복수 가능. -->
- `.specs/data_contract.md` > amount 컬럼 정의

## 작업 범위
<!-- 수정/생성/삭제 대상. 에이전트가 판단해야 할 경우 생략 가능. -->
- 수정: `src/transforms/ledger_controls.py`
- 수정: `src/pipeline/supply_balance.py`
- 생성: `tests/unit/test_threshold_integration.py`

## 완료 조건
- [ ] build_supply_balance_daily에 threshold 파라미터 추가
- [ ] 파이프라인 실행 시 threshold 초과 row 필터링 동작
- [ ] 경계값 테스트 (초과/미만/정확히 같음)
- [ ] 기존 테스트 전체 통과

## 제약 조건
<!-- 에이전트가 하지 말아야 할 것, 지켜야 할 규칙 -->
- 기존 함수 시그니처의 하위 호환성 유지
- default 값은 Spec에 정의된 0.05 사용

## 추가 검증
<!-- verification ladder 외에 이 태스크 고유의 검증이 필요한 경우만. 없으면 생략. -->
```

#### PR body

```markdown
## 변경 요약
<!-- 무엇을 왜 변경했는지 -->

## 문서 영향
<!-- 이 변경이 영향을 줄 수 있는 Spec/문서. 없으면 "없음" -->
- `.specs/data_contract.md`: amount 컬럼 타입이 decimal로 변경됨, Spec 업데이트 필요

## 미결/모호한 점
<!-- Spec에 근거가 없거나 에이전트가 임의로 판단한 부분. ADR을 작성했으면 번호를 달아둔다. -->
- threshold 기본값 0.05는 Spec에 명시적 근거 없음 → ADR-0002
- retry 상한 미정, 현재 임의로 5회 설정 → ADR-0003

## 세션 요약
<!-- 에이전트가 자동 기재. GitHub에 남기지 않으면 사라지는 세션 수준 정보. -->
- 실행 루프 반복 횟수: N회
- L0/L1 실패 항목: (있으면 기재, 없으면 생략)
- Draft PR 여부: 아니오 / 예 (사유: ...)
- 사람 개입: 없음 / (있으면 어떤 판단이 필요했는지)

## 로컬 리뷰 서명
<!-- 에이전트 간(작업 에이전트 → Momus) 사전 리뷰 통과 증빙 -->
- Reviewed-by: Momus (Local)
```

#### ADR

```markdown
# ADR-NNNN: [제목]

## 상태
승인됨 / 제안됨 / 폐기됨

## 맥락
[이 결정이 필요하게 된 배경. 어떤 작업 중 발생했는지.]

## 결정
[채택한 방안]

## 근거
[왜 이 결정을 했는지]
```

---

## 9. 보안/시크릿 관리

AI 에이전트는 시크릿 노출에 대한 감각이 없으므로 다중 방어를 적용한다.

| 계층 | 도구 | 역할 |
|------|------|------|
| Pre-commit hook | gitleaks | 커밋 시점에 시크릿 차단 |
| Push Protection | GitHub Push Protection | push 시점에 시크릿 포함 커밋 차단 (공개 레포 무료) |
| CI 스캔 | GitHub Actions + gitleaks step | PR 단계에서 추가 차단 |
| 에이전트 행동 규칙 | `AGENTS.md` | 시크릿 커밋 금지, `--no-verify` 사용 금지, 더미 값 사용 등 |

- 구현 복잡도가 거의 없고(전체 40분 이내), 에이전트가 코드를 작성하는 워크플로에서는 사람 리뷰만으로는 시크릿 노출을 확실히 막을 수 없다.

---

## 10. 운영 지표 측정

사람이 기록하는 방식은 누락된다. 이미 GitHub에 존재하는 데이터에서 자동 추출한다.

### 4축 지표 프레임워크

| 축 | 핵심 지표 | 데이터 소스 | 수집 방법 |
|----|----------|------------|----------|
| 성공률 | First-Pass CI Rate | PR 첫 CI 결과 | `ai-generated` 라벨 PR 중 첫 check suite pass 비율 |
| 성공률 | Retry Count | PR 커밋 수 | 첫 커밋 이후 추가 커밋 수 |
| 속도 | PR-to-Merge Time | PR created_at → merged_at | GitHub API 직접 계산 |
| 속도 | Throughput | Merged PR 수 | 주 단위 `ai-generated` + merged 카운트 |
| 자율성 | 사람 개입 정도 | PR 리뷰 코멘트 수 + 추가 커밋 수 | PR 코멘트/커밋 수를 개입의 프록시로 사용 |
| 품질 | Post-Merge Defect Rate | Merge 후 버그 이슈 | 원본 PR을 참조하는 버그 이슈 수 |

**사람 개입 측정**: 별도 로그를 남기지 않는다. PR 리뷰 코멘트 수와 추가 커밋 수를 개입의 프록시(proxy)로 사용. 작업 중 개입까지 세분화가 필요해지면 래퍼 스크립트에 세션 종료 프롬프트를 추가.

### 초기 목표

| 지표 | Phase 1 목표 | 비고 |
|------|-------------|------|
| First-Pass CI Rate | 40%+ | 태스크 정의 품질이 성숙하는 데 시간 필요 |
| Task Completion Rate | 80%+ | Issue → Merge 도달 비율 |
| 평균 Retry Count | ≤ 5회 | 성숙기 목표: ≤ 1회 |

### 주간 리포트

- 스크립트(`scripts/weekly_report.py`)가 GitHub API에서 데이터를 추출하여 `docs/reports/YYYY-WNN.md`에 저장.
- 자동 실행(GitHub Action) 또는 수동 실행 모두 가능.
- 리포트에는 요약, 태스크별 상세, 트렌드가 포함된다.
- 팀 운영 시작 시 Discussion/Slack 알림을 추가하여 보고 채널을 확장.

**라벨 컨벤션**: AI가 생성한 PR에는 `ai-generated` 라벨을 부착한다.

---

## 11. 전체 워크플로 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                        사람 영역                                 │
│                                                                 │
│  .specs/ (SSOT)                                                 │
│    │                                                            │
│    ▼                                                            │
│  .roadmap/ (Markdown)                                           │
│    │  - Gate → Epic → Task 계층 구조                             │
│    │  - 태스크 분해, 우선순위, 의존성, Gate, 검증 레벨              │
│    │  - affected_files, exec_commands, DoD                      │
│    │                                                            │
└────┼────────────────────────────────────────────────────────────┘
     │
     ▼  [Sudocode DAG 기반 자동 디스패치]
┌────┼────────────────────────────────────────────────────────────┐
│    │                   자동화 영역                                │
│    │                                                            │
│    ▼                                                            │
│  Sudocode가 Ready Issue 감지 → 에이전트 자동 스폰 (세션 시작)         │
│    │                                                            │
│    ▼                                                            │
│  에이전트 팀 (superpowers skill-based agent) — 단일 세션         │
│    │                                                            │
│    ├─ 1. Sudocode Issue 및 연결된 Spec을 참조하여 작업 컨텍스트 파악
│    │                                                            │
│    ├─ 2. 같은 세션에서 바로 구현                                   │
│    │  - 로컬 L0/L1 검증 반복                                     │
│    │  - 브랜치 생성, 코드 구현                                    │
│    │                                                            │
│    ├─ 3. [Shift-Left] 로컬 에이전트 사전 리뷰 (Momus 호출)        │
│    │  - 코드 품질 검증, Spec 준수 여부 상호 평가                    │
│    │  - 통과 시 `Reviewed-by: Momus (Local)` 서명 획득             │
│    │                                                            │
│    ▼                                                            │
│  PR 생성 (PR 본문에 Sudocode Issue ID 명시)                       │
│    │  - 변경 요약 + 문서 영향 + 미결/모호한 점 (1단계)             │
│    │                                                            │
│    ├──→ CI 자동 검증 (verify label에 따라 L2/L3)                  │
│    │                                                            │
│    ├──→ Drift 감지 (코드 vs spec 비교)                           │
│    │                                                            │
│    ├──→ gitleaks 시크릿 스캔                                     │
│    │                                                            │
│    ├─ [approval:auto AND git diff에 .specs/나 docs/adr/ 변경 없음]│
│    │  [AND PR 본문에 `Reviewed-by:` 서명이 존재하는 경우]          │
│    │  └──→ Auto-Merge 자동 실행 (`gh pr merge --auto`) ──┐     │
│    │                                  │                  │     │
└────┼──────────────────────────────────┼──────────────────┼──────┘
     │                                  │                  │
     ▼  [approval:manual 이거나         │                  │
        안전장치(Fallback) 발동 시]        │                  │
┌────┼──────────────────────────────────┼──────────────────┼──────┐
│    │                    사람 영역       │                  │      │
│    │                                  │                  │      │
│    ▼                                  │                  │      │
│  PR 리뷰 + 문서 업데이트 판단             │                  │      │
│    │  - 미결 항목 확인: Spec 수정/ADR    │                  │      │
│    │                                  │                  │      │
└────┼──────────────────────────────────┼──────────────────┼──────┘
     │                                  │                  │
     ▼  [Merge]                         ▼                  ▼
┌────┼──────────────────────────────────┼─────────────────────────┐
│    │                   자동화 영역      │                         │
│    │                                  ▼                         │
│    ▼                                                            │
│  Issue 자동 close                                               │
│  Sudocode 데몬의 폴링 루프가 다음 Ready Issue 감지 → 에이전트에 자동 디스패치│
│  (필요 시) ADR 초안 생성 → docs/adr/                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
     │
     ▼  [Gate 도달 시]
┌─────────────────────────────────────────────────────────────────┐
│  사람이 Milestone close = Gate 승인                              │
│  → 다음 Gate로 진행                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 12. 구현 시 고려사항

### 필요 도구

| 도구 | 용도 |
|------|------|
| **Sudocode** (`sudocode server`) | Issue DAG 관리, 에이전트 디스패치(worktree + 스폰), 실시간 모니터링, Spec ↔ Issue 링크 |
| GitHub Actions | CI 검증, `approval:auto` 판단 및 `APPROVE` 도장(기계적 검사), 문서 drift 감지, gitleaks 스캔 |
| `gh` CLI | PR 생성/조작 |
| superpowers 기반 코딩 에이전트 | 작업 에이전트 실행, 스킬 체인 오케스트레이션, 로컬 사전 리뷰(Momus) 수행 |
| LLM 스킬 (`skills/create-pr/SKILL.md`, `skills/create-adr/SKILL.md`) | PR body, ADR 초안 생성 등 보조 산출물 템플릿 제공 (모델 불문) |
| gitleaks | Pre-commit hook + CI 시크릿 스캔 |
| `AGENTS.md` | 프로젝트 컨벤션, 리뷰 가이드라인, 보안 규칙 |


### Issue 간 충돌 관리

- `affected_files`가 겹치는 Issue는 **순차 실행**
- `depends_on`이 없고 `affected_files`가 겹치지 않는 태스크는 **git worktree를 사용하여 병렬 실행** 가능 (§3 참조)
- 병렬 실행 시에도 PR merge는 순차 처리하여 충돌을 최소화한다

### Label 체계 (Sudocode Tag 미러링)

- **SSOT 원칙**: 모든 메타데이터의 진실 원천은 Sudocode Issue(`tags` 필드)이며, GitHub 라벨은 GitHub Actions 구동을 위한 단순 미러링용으로만 사용된다.

| 축 | Label |
|----|-------|
| 범위 | `epic:pipeline-a`, `epic:pipeline-b`, `epic:silver` |
| 유형 | `type:feature`, `type:bug`, `type:infra`, `type:test` |
| 우선순위 | `P0`, `P1`, `P2` |
| 검증 | `verify:L2`, `verify:L3` |
| 승인 | `approval:manual`, `approval:auto` |
| 상태 | `blocked`, `needs-review` |
| AI | `ai-generated` |

### Milestone = Gate

Gate 개념을 GitHub Milestone으로 매핑하면 달성률이 자동 계산됨.

```bash
gh api repos/{owner}/{repo}/milestones --method POST \
  -f title="G1: Secure Binding Ready" \
  -f due_on="2026-03-01"
```
