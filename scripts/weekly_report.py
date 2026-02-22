#!/usr/bin/env python3
"""Generate a weekly operations report.

Expected environment variables:
- GITHUB_TOKEN
- GITHUB_REPO (owner/repo)
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request


API_BASE = "https://api.github.com"
CHECK_FAILURE_CONCLUSIONS = {
    "failure",
    "timed_out",
    "cancelled",
    "action_required",
    "startup_failure",
    "stale",
}
CHECK_SUCCESS_CONCLUSIONS = {"success"}
MAX_PULLS_PAGES = 20


@dataclass
class PullRequestSummary:
    number: int
    title: str
    author: str
    created_at: datetime
    merged_at: datetime
    head_sha: str
    url: str
    first_pass_ci: bool | None = None


class GitHubClient:
    def __init__(self, token: str, repo: str) -> None:
        if "/" not in repo:
            raise ValueError("GITHUB_REPO must be in owner/repo format")
        self.repo = repo
        self.token = token

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = parse.urlencode(params or {})
        url = f"{API_BASE}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{query}"

        req = request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

        try:
            with request.urlopen(req, timeout=30) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                payload = resp.read().decode(charset)
                return json.loads(payload) if payload else None
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"GitHub API request failed ({exc.code}) for {url}: {body}"
            ) from exc


def parse_utc(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def weekly_window(now: datetime) -> tuple[datetime, datetime, str]:
    this_monday = (now - timedelta(days=now.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    window_end = this_monday
    window_start = window_end - timedelta(days=7)
    iso_year, iso_week, _ = window_start.isocalendar()
    label = f"{iso_year}-W{iso_week:02d}"
    return window_start, window_end, label


def fetch_merged_ai_prs(
    client: GitHubClient,
    window_start: datetime,
    window_end: datetime,
) -> list[PullRequestSummary]:
    results: list[PullRequestSummary] = []

    for page in range(1, MAX_PULLS_PAGES + 1):
        pulls = client.get_json(
            f"repos/{client.repo}/pulls",
            {
                "state": "closed",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
                "page": page,
            },
        )

        if not pulls:
            break

        reached_older_window = False

        for pr in pulls:
            merged_at_raw = pr.get("merged_at")
            if not merged_at_raw:
                continue

            merged_at = parse_utc(merged_at_raw)
            if merged_at < window_start:
                reached_older_window = True
                continue
            if merged_at >= window_end:
                continue

            labels = {label.get("name", "") for label in pr.get("labels", [])}
            if "ai-generated" not in labels:
                continue

            created_at_raw = pr.get("created_at")
            head_sha = ((pr.get("head") or {}).get("sha")) or ""
            if not created_at_raw:
                continue

            results.append(
                PullRequestSummary(
                    number=pr["number"],
                    title=pr.get("title", ""),
                    author=(pr.get("user") or {}).get("login", "unknown"),
                    created_at=parse_utc(created_at_raw),
                    merged_at=merged_at,
                    head_sha=head_sha,
                    url=pr.get("html_url", ""),
                )
            )

        if reached_older_window:
            break

    return sorted(results, key=lambda pr: pr.merged_at)


def evaluate_first_pass_ci(client: GitHubClient, prs: list[PullRequestSummary]) -> None:
    for pr in prs:
        if not pr.head_sha:
            pr.first_pass_ci = None
            continue

        checks = client.get_json(
            f"repos/{client.repo}/commits/{pr.head_sha}/check-runs",
            {"per_page": 100},
        )
        runs = checks.get("check_runs", []) if isinstance(checks, dict) else []
        completed = [run for run in runs if run.get("status") == "completed"]

        if not completed:
            pr.first_pass_ci = None
            continue

        conclusions = {run.get("conclusion") for run in completed}
        has_failure = any(c in CHECK_FAILURE_CONCLUSIONS for c in conclusions)
        has_success = any(c in CHECK_SUCCESS_CONCLUSIONS for c in conclusions)
        pr.first_pass_ci = has_success and not has_failure


def find_roadmap_file(repo_root: Path) -> Path | None:
    preferred = repo_root / ".roadmap" / "roadmap.md"
    if preferred.exists():
        return preferred

    candidates = sorted((repo_root / ".roadmap").glob("*.md"))
    return candidates[0] if candidates else None


def count_roadmap_tasks(roadmap_path: Path | None) -> int:
    if not roadmap_path or not roadmap_path.exists():
        return 0
    with roadmap_path.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.startswith("#### "))


def load_sudocode_issues(repo_root: Path) -> tuple[list[dict[str, Any]], str]:
    candidates = [
        repo_root / ".sudocode" / "issues" / "issues.jsonl",
        repo_root / ".sudocode" / "issues.jsonl",
    ]

    for path in candidates:
        if not path.exists():
            continue

        items: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    items.append(value)

        return items, str(path.relative_to(repo_root))

    return [], "not-found"


def fmt_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def fmt_hours(value: float) -> str:
    return f"{value:.1f}"


def fmt_percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "N/A"
    return f"{(numerator / denominator) * 100:.1f}% ({numerator}/{denominator})"


def build_report(
    repo: str,
    label: str,
    window_start: datetime,
    window_end: datetime,
    prs: list[PullRequestSummary],
    roadmap_display_path: str,
    roadmap_total: int,
    sudocode_issues: list[dict[str, Any]],
    sudocode_source: str,
) -> str:
    lead_times = [(pr.merged_at - pr.created_at).total_seconds() / 3600 for pr in prs]
    avg_lead = statistics.mean(lead_times) if lead_times else 0.0
    median_lead = statistics.median(lead_times) if lead_times else 0.0

    first_pass_known = [pr for pr in prs if pr.first_pass_ci is not None]
    first_pass_success = sum(1 for pr in first_pass_known if pr.first_pass_ci)

    issue_total = len(sudocode_issues)
    issue_closed = sum(
        1
        for issue in sudocode_issues
        if str(issue.get("status", "")).strip().lower() == "closed"
    )

    lines: list[str] = [
        f"# Weekly Report {label}",
        "",
        f"- Generated at (UTC): {fmt_dt(datetime.now(timezone.utc))}",
        f"- Repository: `{repo}`",
        f"- Window (UTC): {fmt_dt(window_start)} -> {fmt_dt(window_end)}",
        "",
        "## PR Metrics (`ai-generated`, merged in window)",
        "",
        f"- Merged PR count: {len(prs)}",
        f"- First-Pass CI Rate: {fmt_percent(first_pass_success, len(first_pass_known))}",
        f"- PR-to-Merge Time (avg hours): {fmt_hours(avg_lead)}",
        f"- PR-to-Merge Time (median hours): {fmt_hours(median_lead)}",
        "",
        "## Sudocode Issue Metrics",
        "",
        f"- Source: `{sudocode_source}`",
        f"- Total issues: {issue_total}",
        f"- Closed issues: {issue_closed}",
        f"- Closed ratio: {fmt_percent(issue_closed, issue_total)}",
        "",
        "## Roadmap vs Sudocode",
        "",
        f"- Roadmap file: `{roadmap_display_path}`",
        f"- Roadmap task count: {roadmap_total}",
        f"- Sudocode closed count: {issue_closed}",
        f"- Gap (roadmap tasks - closed issues): {roadmap_total - issue_closed}",
        "",
        "## Merged PR Details",
        "",
    ]

    if not prs:
        lines.append("- No merged `ai-generated` PRs found in this window.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| PR | Title | Author | Created (UTC) | Merged (UTC) | Lead Time (h) | First-Pass CI |",
            "|---:|---|---|---|---|---:|---|",
        ]
    )

    for pr in prs:
        lead_time_h = (pr.merged_at - pr.created_at).total_seconds() / 3600
        title = pr.title.replace("|", "\\|").replace("\n", " ").strip()
        if len(title) > 80:
            title = title[:77] + "..."
        first_pass = (
            "yes"
            if pr.first_pass_ci is True
            else "no"
            if pr.first_pass_ci is False
            else "n/a"
        )
        lines.append(
            f"| [#{pr.number}]({pr.url}) | {title} | {pr.author} | {fmt_dt(pr.created_at)} | "
            f"{fmt_dt(pr.merged_at)} | {fmt_hours(lead_time_h)} | {first_pass} |"
        )

    return "\n".join(lines) + "\n"


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    reports_dir = repo_root / "docs" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    token = require_env("GITHUB_TOKEN")
    repo = require_env("GITHUB_REPO")

    client = GitHubClient(token=token, repo=repo)
    window_start, window_end, label = weekly_window(datetime.now(timezone.utc))
    prs = fetch_merged_ai_prs(client, window_start, window_end)
    evaluate_first_pass_ci(client, prs)

    roadmap_path = find_roadmap_file(repo_root)
    roadmap_total = count_roadmap_tasks(roadmap_path)
    if roadmap_path is not None:
        try:
            roadmap_display_path = str(roadmap_path.relative_to(repo_root))
        except ValueError:
            roadmap_display_path = str(roadmap_path)
    else:
        roadmap_display_path = "not-found"

    issues, issues_source = load_sudocode_issues(repo_root)

    report = build_report(
        repo=repo,
        label=label,
        window_start=window_start,
        window_end=window_end,
        prs=prs,
        roadmap_display_path=roadmap_display_path,
        roadmap_total=roadmap_total,
        sudocode_issues=issues,
        sudocode_source=issues_source,
    )

    output_path = reports_dir / f"{label}.md"
    output_path.write_text(report, encoding="utf-8")
    print(output_path.relative_to(repo_root))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"weekly_report.py failed: {exc}", file=sys.stderr)
        raise
