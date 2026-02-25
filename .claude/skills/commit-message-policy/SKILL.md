---
name: commit-message-policy
description: Commit message guidelines. Use when writing git commit messages, reviewing commits, or version control tasks.
---

# Commit Message Policy

## Rules

**0. Write in English** — Commit subject and body must be written in English.

Bad: `로컬 메타 부산물을 무시해 작업 이력에 노이즈가 섞이지 않게 함`
Good: `Ignore local metadata artifacts to keep history focused on product changes`

**1. No Conventional Commits** — Do not use `fix:`, `feat:`, `chore:` or similar prefixes.

**2. Focus on Why** — Explain reasoning, not what changed (the diff shows that).

Bad: `Add validation function to user input`
Good: `User input was causing database errors with special characters`

**3. Permalink URLs** — Use full URLs, not `#123`.

Bad: `Fix crash reported in #456`
Good: `Fix crash when loading large files` + URL in body

## Example

```
Prevent duplicate form submissions during network latency

Users on slow connections could submit multiple times before response,
creating duplicate records.

https://github.com/org/repo/issues/789

```
