# Coding Agent Roadmap

> `coding_agent_spec.md` 구현 순서서.
> 각 태스크의 담당과 구체적 실행 방법 정리.

**표기 규칙**
- `[사람]` — 직접 실행/결정
- `[AI]` — Claude Code에 요청하면 파일 생성
- `[AI→CLI]` — Claude Code가 gh/shell 명령어 직접 실행

---

## G0. 사전 준비

이후 모든 단계의 전제조건. 전부 사람이 직접 해야 함.

### 0-1. GitHub 저장소 생성 `[사람]`

**할 일:**
- github.com → New repository
- 저장소 이름 결정
- 공개(Public) / 비공개(Private) 선택
- **README 없이 빈 저장소로 초기화**

**완료 확인:** `https://github.com/{owner}/{repo}` 접근 가능

---

### 0-2. gh CLI 설치 + 인증 `[사람]`

**설치 (Windows):**
```bash
winget install --id GitHub.cli
```
또는 https://github.com/cli/cli/releases 에서 MSI 다운로드

**설치 (Linux / WSL):**
```bash
# 공식 APT 저장소 등록
(type -p wget >/dev/null || (sudo apt update && sudo apt-get install wget -y)) \
  && sudo mkdir -p -m 755 /etc/apt/keyrings \
  && out=$(mktemp) && wget -nv -O$out https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  && cat $out | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
  && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
  && sudo apt update \
  && sudo apt install gh -y
```
또는 Homebrew가 설치되어 있다면:
```bash
brew install gh
```

**인증:**
```bash
gh auth login
# → GitHub.com 선택
# → HTTPS 선택
# → 브라우저 인증
```

**완료 확인:**
```bash
gh auth status
```

---

### 0-3. gitleaks 설치 `[사람]`

**설치 (Windows):**
```bash
choco install gitleaks
```
또는 https://github.com/gitleaks/gitleaks/releases 에서 바이너리 다운로드 후 PATH에 추가

**설치 (Linux / WSL):**
```bash
# Homebrew 사용
brew install gitleaks
```
또는 바이너리 직접 설치:
```bash
# 최신 버전 확인 후 다운로드 (amd64 예시)
wget https://github.com/gitleaks/gitleaks/releases/download/v8.21.2/gitleaks_8.21.2_linux_x64.tar.gz
tar -xzf gitleaks_8.21.2_linux_x64.tar.gz
sudo mv gitleaks /usr/local/bin/
```

**완료 확인:**
```bash
gitleaks version
```

---

### 0-4. pre-commit 설치 `[사람]`

```bash
pip install pre-commit
pre-commit --version
```

> **WSL 참고:** WSL에서는 Python이 기본 설치되어 있을 수 있으나, `pip`이 없다면 `sudo apt install python3-pip`을 먼저 실행.

---

### 0-5. Oh My OpenCode 설치/설정 `[사람]`

- Oh My OpenCode 설치 (공식 가이드 참조)
- GPT Pro 계정 연동
- 로컬 실행 확인

---

### 0-6. 로컬에 레포 clone `[사람]`

```bash
gh repo clone {owner}/{repo}
cd {repo}
```

---

### 0-7. git worktree 개념 숙지 (Sudocode 데몬 자동화 기반) `[사람]`

병렬 에이전트 자동 실행 시 Sudocode 데몬이 백그라운드에서 활용하는 기능이므로, 개념적 이해가 필요하다.

**Sudocode가 내부적으로 실행하는 명령어:**
```bash
# worktree 자동 생성 (태스크별 독립 디렉토리)
git worktree add ../repo-{task_id} -b feat/{task_id}

# 작업 완료 후 데몬이 자동 정리
git worktree remove ../repo-{task_id}
```

**병렬 실행 조건 (데몬이 판단):**
- 두 태스크 간 `depends_on` 없음
- `affected_files`가 겹치지 않음
- 위 조건 미충족 시 데몬이 자동으로 순차 디스패치 전환

---

### 0-8. Sudocode 설치 및 환경 초기화 `[사람]`

> **WSL 참고:** WSL에 Node.js가 없다면 nvm으로 설치:
> ```bash
> curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
> source ~/.bashrc
> nvm install --lts
> node -v && npm -v   # 설치 확인
> ```

**할 일:**
1. Sudocode 전역 설치:
   ```bash
   npm install -g sudocode
   ```
2. 프로젝트 루트에서 초기화 (`.sudocode/` 디렉토리 생성):
   ```bash
   sudocode init
   ```
3. OpenCode에 MCP 서버 등록:
   `opencode.json` 파일에 다음 설정 추가:
   ```json
   {
     "mcp": {
       "sudocode-mcp": {
         "type": "local",
         "command": "sudocode-mcp"
       }
     }
   }
   ```

**완료 확인:** `sudocode server` 실행 후 `http://localhost:3000` 로컬 접속 성공 및 OpenCode에서 `sudocode.upsert_issue` 도구 확인

---

## G1. 저장소 뼈대

디렉토리 구조 + 핵심 설정 파일. 1-1~1-3은 Claude Code에 요청.

### 1-1. 디렉토리 구조 생성 `[AI]`

**Claude Code에:** "디렉토리 구조 만들어줘"

**생성될 구조:**
```
{repo}/
├── .specs/             # 도메인 규범 SSOT (사람이 작성)
├── .roadmap/           # 실행 계획 Markdown
├── docs/
│   ├── adr/            # Architecture Decision Records
│   ├── generated/      # 코드에서 자동 추출된 문서 (읽기 전용)
│   ├── reports/        # 주간 리포트
│   └── upstream/       # 연관(상위) 프로젝트 문서 레퍼런스
├── scripts/            # 자동화 스크립트
├── skills/             # 에이전트 프롬프트 템플릿
└── .github/
    └── workflows/
```

각 빈 디렉토리에 `.gitkeep` 자동 생성.

---

### 1-2. .gitignore 작성 `[AI]`

**Claude Code에:** ".gitignore 작성해줘"

포함 항목: `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `.env`, `*.egg-info/`, `.DS_Store`, `Thumbs.db`, `.idea/`, `.vscode/`

---

### 1-3. AGENTS.md 작성 `[AI]`

**Claude Code에:** "AGENTS.md 작성해줘"

**포함될 섹션:**
- `## 프로젝트 개요` — 워크플로 구조 한 줄 설명
- `## 파일 구조` — 각 디렉토리 역할
- `## 에이전트 행동 규칙`
  - `--no-verify` 절대 사용 금지
  - `.env` 파일 절대 커밋 금지
  - 시크릿은 더미 값(`PLACEHOLDER`) 사용
  - **PR 생성 직전 로컬 리뷰 에이전트(Momus)를 호출하여 코드 검증 필수**
- 동일 테스트 5회 연속 실패 시 Draft PR 생성 후 중단
- `## Review guidelines` — spec 정합성, 컨벤션, 시크릿 노출 여부, **Momus 리뷰 서명 포함 여부**
- `## Verification Ladder` — L0~L3 명세

---

### 1-4. docs/upstream/ 에 연관 프로젝트 문서 복사 `[사람]`

**할 일:**
1. 연관(상위) 프로젝트의 관련 문서를 `docs/upstream/`에 복사
2. `docs/upstream/README.md` 작성:

```markdown
# Upstream References

에이전트와 작업자가 맥락 파악 시 참고하는 연관 프로젝트 문서.
이 디렉토리의 파일은 직접 수정하지 않음 (읽기 전용 레퍼런스).

| 파일 | 출처 | 버전/날짜 |
|------|------|----------|
| example.md | {프로젝트명} | {날짜} |
```

---

### 1-5. 초기 커밋 + push `[사람]`

```bash
git add .
git commit -m "chore: initialize repository structure"
git push origin main
```

**완료 확인:** GitHub에서 파일 구조 확인

---

## G2. 오케스트레이션 상태 관리 (GitHub + Sudocode)

GitHub 라벨/마일스톤 대신 Sudocode 로컬 서버를 기본 상태 관리자로 사용.

### 2-1. Spec 문서 → Sudocode Spec 등록 `[AI]`

**Claude Code에:** "현재 `docs/coding_agent/` 안의 문서를 Sudocode MCP(`sudocode.upsert_spec`)를 사용해 Spec으로 등록해줘"

**예시:**
- `coding_agent_spec.md` → SPEC-001
- `data_contract.md` → SPEC-002

**완료 확인:** `.sudocode/specs/specs.jsonl`에 항목이 추가되었는지 확인

---

### 2-2. GitHub Push Protection 활성화 `[사람]`

**경로:** `https://github.com/{owner}/{repo}/settings/security_analysis`

→ "Push protection" → Enable

> 공개 레포는 무료. 비공개 레포는 GitHub Advanced Security 필요.

---

## G3. 보안 레이어

에이전트가 시크릿을 실수로 커밋하는 것을 pre-commit hook으로 차단.

### 3-1. .pre-commit-config.yaml 작성 `[AI]`

**Claude Code에:** "pre-commit config 작성해줘"

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2
    hooks:
      - id: gitleaks
```

---

### 3-2. pre-commit hook 설치 `[사람]`

레포 루트에서:
```bash
pre-commit install
```

**완료 확인:** `.git/hooks/pre-commit` 파일 존재

---

### 3-3. hook 동작 확인 `[사람]`

```bash
# 더미 파일로 테스트
echo "GITHUB_TOKEN=ghp_testtoken1234567890" > test_secret.txt
git add test_secret.txt
git commit -m "test"
# → gitleaks가 차단해야 함

# 정리
git restore --staged test_secret.txt
rm test_secret.txt
```

---

## G4. CI/CD GitHub Actions

전부 AI가 작성. 사람은 push 후 Actions 탭에서 동작 확인만.

### 4-1. L2 검증 워크플로 `[AI]`

**Claude Code에:** "L2 CI 워크플로 작성해줘"

**생성 파일:** `.github/workflows/ci-l2.yml`

- 트리거: PR 생성/업데이트, main 브랜치 push
- 실행: `pytest tests/unit/ tests/integration/ --cov=src --cov-fail-under=80`
- Python 버전: 요청 시 지정

---

### 4-2. gitleaks CI 스캔 `[AI]`

**Claude Code에:** "보안 스캔 워크플로 작성해줘"

**생성 파일:** `.github/workflows/ci-security.yml`

- 트리거: 모든 PR
- 실행: gitleaks GitHub Action (`gitleaks/gitleaks-action`)

---

### 4-3. Drift 감지 워크플로 `[AI]`

**Claude Code에:** "drift 감지 워크플로 작성해줘"

**생성 파일:** `.github/workflows/ci-drift.yml`

- 트리거: 모든 PR
- 실행: `.specs/` 스키마 정의 vs 코드 비교 로직 실행
- 결과: 규범(`.specs/`)과 구현(코드) 간 불일치 발생 시 즉시 **CI 실패 (PR 차단)** 처리

---

### 4-4. 주간 리포트 워크플로 (선택) `[AI]`

**Claude Code에:** "주간 리포트 워크플로 작성해줘"

**생성 파일:** `.github/workflows/weekly-report.yml`

- 트리거: `cron: '0 9 * * 1'` (매주 월 09:00 UTC) + 수동 실행 가능
- 실행: `python scripts/weekly_report.py`
- 결과: `docs/reports/YYYY-WNN.md` 커밋

---

### 4-5. Auto-Merge 워크플로 `[AI]`

**Claude Code에:** "Auto-Merge 워크플로 작성해줘"

**생성 파일:** `.github/workflows/auto-merge.yml`

- 트리거: PR 업데이트 시
- 실행: 
  1. 사전 CI (L2 등) 검증 파이프라인 통과 여부 확인
  2. `docs/adr/*` 또는 `.specs/*` 파일 변경 여부 기계적 검사 (변경 시 Auto-Merge 중단)
  3. PR 본문에 `Reviewed-by: Momus (Local)` 서명 존재 여부 확인
  4. 모든 조건 만족 시 `gh pr review --approve` 및 `gh pr merge --auto` 자동 실행
  5. 실패/Fallback 시 `gh pr merge --disable-auto` 실행으로 예약 취소 후 `needs-review` 라벨 부착 및 `approval: manual` 상태로 강등

---

### 4-6. 워크플로 push + 동작 확인 `[사람]`

```bash
git add .github/
git commit -m "ci: add GitHub Actions workflows"
git push origin main
```

**완료 확인:** GitHub → Actions 탭 → 워크플로 목록 확인

---

## G5. 에이전트 스킬 & 스크립트

에이전트 팀이 Issue/PR/ADR 생성 시 사용하는 프롬프트 템플릿과 리포트 스크립트.

### 5-1. skills/pr.md `[AI]`

**Claude Code에:** "PR 생성 스킬 작성해줘"

에이전트가 작업 완료 후 `gh pr create`를 실행하는 프롬프트 템플릿.

포함 내용:
- 변경 요약 작성 방법
- **PR 본문에 해결한 Sudocode Issue ID 반드시 명시**
- 문서 영향 분석 방법 (어떤 `.specs/` 문서가 영향받는지)
- 미결/모호한 점 식별 방법
- ADR 작성 트리거 기준
- 로컬 리뷰 서명 (`Reviewed-by: Momus (Local)`) 포함 지침

---

### 5-2. skills/adr.md `[AI]`

**Claude Code에:** "ADR 스킬 작성해줘"

에이전트가 설계 결정 발생 시 `docs/adr/NNNN-title.md`를 작성하는 프롬프트 템플릿.

포함 내용:
- ADR 번호 채번 방법 (기존 파일 목록 확인 후 +1)
- 맥락/결정/근거 섹션 작성 지침

---

### 5-3. scripts/weekly_report.py `[AI]`

**Claude Code에:** "weekly_report.py 작성해줘"

**기능:**
- GitHub API로 `ai-generated` + merged PR 수집
- Sudocode 로컬 파일(`.sudocode/issues/issues.jsonl`)에서 Issue 상태/통계 추출
- First-Pass CI Rate, PR-to-Merge Time 계산
- Roadmap 총량 vs Sudocode Closed 상태 대조
- `docs/reports/YYYY-WNN.md` 생성

**필요 환경변수:** `GITHUB_TOKEN`, `GITHUB_REPO` (`owner/repo` 형식)

---

## G6. 첫 실행 (연기 테스트)

인프라가 실제로 동작하는지 end-to-end 검증.

### 6-1. 첫 .specs/ 문서 작성 `[사람]`

**할 일:**
1. 가장 핵심적인 도메인 하나 선택
2. `.specs/{도메인명}.md` 작성

**포함 내용:** 스키마, 비즈니스 규칙, 설계 의도, 임계값 근거

> **주의:** Spec에는 "왜"와 "무엇"만. 구현 방법("어떻게")은 쓰지 않음.

---

### 6-2. Roadmap 초안 생성 `[AI]`

**Claude Code에:** "방금 작성한 Spec 읽고 Roadmap 초안 만들어줘"

**생성 파일:** `.roadmap/roadmap.md`

비전 문서의 Roadmap 포맷 준수:
- Gate → Epic → Task 계층 (`##`, `###`, `####` 헤딩)
- 각 태스크 필드 (`#####` 헤딩 단위로 priority, verify, approval, source_doc, depends_on, status 작성)
- 각 Task별 DoD 체크리스트

---

### 6-3. Roadmap을 Sudocode Issue DAG로 동기화 (데몬 설정) `[사람+AI]`

**할 일:**
1. 로드맵을 작성하면 Sudocode 데몬이 이를 감지하여 `.sudocode/issues/issues.jsonl`에 점진적(incremental)으로 upsert하도록 watch 모드 활성화.
2. 마크다운의 `depends_on`이 `blocks` 엣지로 정확히 위상 정렬되는지 확인.

**확인 항목:**
- 데몬 실행 중 `.roadmap/roadmap.md` 수정 시 `.sudocode/issues/issues.jsonl`에 실시간 반영되는가?
- `sudocode server` 웹 UI에서 DAG 시각화가 정상 표현되는가?

---

### 6-4. 에이전트 디스패치 (단일 실행 자동 스폰 테스트) `[사람+AI]`

**할 일:**
1. `sudocode server` 데몬 실행 및 웹 UI (`http://localhost:3000`) 접속
2. "Ready" 칸에 있는 의존성 없는 Task (예: EPIC-01) 발생 확인
3. 데몬이 **자동으로 `sudocode-mcp_ready` 폴링을 통해 worktree를 할당하고 에이전트를 스폰**하는지 관찰 (수동 디스패치 아님)
4. 에이전트가 MCP로 체크리스트 조회 후 구현 진행 및 PR 생성 과정 관찰

---

### 6-5. 결과 리뷰 + 조정 `[사람]`

확인 항목:
- [ ] PR body에 Sudocode Issue ID, 문서 영향/미결사항, Momus 서명이 포함되었는가? (skills/pr.md 양식)
- [ ] CI(Auto-Merge 등)가 정상 동작했는가?
- [ ] PR 머지 시 데몬이 Issue 상태를 `closed`로 자체 전환했는가?
- [ ] 에이전트 세션 종료 및 Issue closed 후 후속 의존성 에픽이 Ready 상태로 자동 전환(blocker 해소)되는지 웹 UI에서 확인

**조정:** 문제 발생 시 AGENTS.md 또는 `skills/` 템플릿 수정 후 재시도.

---

### 6-6. 병렬 에이전트 테스트 (Sudocode 동시 디스패치) `[사람+AI]`

> 6-4 순차 실행이 안정적으로 동작한 후 시도.

**전제:** Sudocode 웹 UI "Ready" 칸에 `affected_files`가 겹치지 않는 태스크가 2개 이상 존재

**할 일:**
1. 웹 UI에서 독립된 태스크 2개(예: EPIC-03, EPIC-04)를 찾아 [Dispatch] 버튼을 각각 클릭
2. Sudocode가 두 개의 독립된 worktree를 생성하고 각각 에이전트를 스폰하는지 확인
3. 두 개의 터미널(또는 백그라운드 프로세스)이 동시에 각자 할 일을 하는지 확인
4. 에이전트 종료 후 PR 두 개가 각각 정상 생성되었는지 확인
5. PR 머지는 순차적으로 진행 (Conflict 방지)
6. 작업 완료된 worktree 수동 또는 자동 정리 상태 확인

**확인 항목:**
- [ ] 두 PR이 각각 독립적으로 CI 통과하는가?
- [ ] merge 시 충돌이 발생하지 않는가?
- [ ] Issue/PR 번호가 정상적으로 분리되는가?

---

## 전체 진행 순서 요약

```
G0 (사람: 설정 및 도구/Sudocode 설치)
  ↓
G1 (AI: 뼈대 파일 생성) + (사람: upstream 문서 복사, 커밋)
  ↓
G2 (AI: Spec을 Sudocode에 등록) + (사람: GitHub UI 설정)
  ↓
G3 (AI: pre-commit config) + (사람: hook 설치 및 테스트)
  ↓
G4 (AI: GitHub Actions 워크플로 전부) + (사람: push 후 동작 확인)
  ↓
G5 (AI: skills/ + scripts/ 전부)
  ↓
G6 (사람: Spec) → (AI: Roadmap) → (AI: Sudocode Issue로 변환) → (사람+AI: Dispatch 테스트) → (사람+AI: 다중 Dispatch 테스트)
```

**AI가 생성하는 파일 수:** 약 15개
**사람이 반드시 직접 해야 하는 것:** G0 도구 설치/인증, GitHub UI 설정 2개, upstream 문서 복사, Spec 작성
