#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


FAILURE_MARKERS = (
    "Execution did not complete successfully",
    "Changes unavailable",
)

SUCCESS_STATUS = "needs_review"
FAILURE_STATUS = "open"
VALID_INITIAL_STATUSES = {"open", "in_progress"}

PROTECTED_SCOPE_PATTERNS = (".specs/", "docs/adr/")
METIS_REQUIRED_THRESHOLD = 6
MOMUS_REQUIRED_THRESHOLD = 4
MAX_ULW_ITERATIONS_BY_RISK = {"low": 1, "medium": 2, "high": 3}
VERIFY_SCORE = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
RISK_TIER_ORDER = {"low": 0, "medium": 1, "high": 2}
RISK_TIER_BONUS = {"low": 0, "medium": 2, "high": 4}

ENV_METIS_APPROVED = "DISPATCHER_METIS_APPROVED"
ENV_MOMUS_APPROVED = "DISPATCHER_MOMUS_PRE_APPROVED"
ENV_MOMUS_POST_APPROVED = "DISPATCHER_MOMUS_POST_APPROVED"


class DispatchError(RuntimeError):
    pass


def normalize_command(command: str) -> str:
    normalized = (command or "").strip()
    if normalized.startswith("/"):
        normalized = normalized[1:]
    return normalized.strip()


def normalize_tags(raw_tags: Any) -> List[str]:
    if not isinstance(raw_tags, list):
        return []
    tags: List[str] = []
    for tag in raw_tags:
        if isinstance(tag, str):
            value = tag.strip()
            if value:
                tags.append(value)
    return tags


def extract_verify_level(issue: Dict[str, Any]) -> str:
    for tag in normalize_tags(issue.get("tags")):
        if not tag.startswith("verify:"):
            continue
        value = tag.split(":", 1)[1].strip().upper()
        if value in VERIFY_SCORE:
            return value
    return "L0"


def extract_gate_tier(issue: Dict[str, Any]) -> str:
    for tag in normalize_tags(issue.get("tags")):
        if not tag.startswith("gate:"):
            continue
        value = tag.split(":", 1)[1].strip().lower()
        if value in RISK_TIER_BONUS:
            return value
    return "low"


def extract_priority_level(issue: Dict[str, Any]) -> Optional[int]:
    priority = issue.get("priority")
    if isinstance(priority, int):
        return priority
    if isinstance(priority, str):
        stripped = priority.strip()
        if stripped.startswith("P") and stripped[1:].isdigit():
            return int(stripped[1:])
        if stripped.isdigit():
            return int(stripped)

    for tag in normalize_tags(issue.get("tags")):
        if tag.startswith("priority:"):
            value = tag.split(":", 1)[1].strip().upper()
            if value.startswith("P") and value[1:].isdigit():
                return int(value[1:])
            if value.isdigit():
                return int(value)
    return None


def mentions_protected_scope(content: str, title: str = "") -> bool:
    combined = f"{title}\n{content}".lower()
    return any(pattern in combined for pattern in PROTECTED_SCOPE_PATTERNS)


def max_risk_tier(*tiers: str) -> str:
    selected = "low"
    score = RISK_TIER_ORDER[selected]
    for tier in tiers:
        current = RISK_TIER_ORDER.get(tier, 0)
        if current > score:
            score = current
            selected = tier
    return selected


def build_gate_profile(issue: Dict[str, Any]) -> GateProfile:
    tags = normalize_tags(issue.get("tags"))
    verify_level = extract_verify_level(issue)
    gate_tier = extract_gate_tier(issue)
    priority_level = extract_priority_level(issue)

    reasons: List[str] = []

    verify_score = VERIFY_SCORE.get(verify_level, 0)
    priority_score = 0
    if priority_level is None:
        reasons.append("No explicit priority found")
    else:
        if priority_level <= 0:
            priority_score = 3
            reasons.append("Priority indicates highest urgency (P0)")
        elif priority_level == 1:
            priority_score = 2
            reasons.append("Priority indicates P1")
        else:
            priority_score = 1
            reasons.append(f"Priority indicates P{priority_level}")

    gate_score = RISK_TIER_BONUS.get(gate_tier, 0)
    if gate_tier in RISK_TIER_BONUS:
        reasons.append(f"Gate override tag set to {gate_tier}")

    risk_score = verify_score + priority_score + gate_score

    if "approval:manual" in tags:
        risk_score += 2
        reasons.append("Manual approval tag requested")

    if mentions_protected_scope(
        str(issue.get("content") or ""), str(issue.get("title") or "")
    ):
        risk_score += 2
        reasons.append("Protected scope appears in issue content")

    risk_tier = "low"
    if risk_score >= 6:
        risk_tier = "high"
    elif risk_score >= 4:
        risk_tier = "medium"

    risk_tier = max_risk_tier(risk_tier, gate_tier)

    recommended = MAX_ULW_ITERATIONS_BY_RISK[risk_tier]

    return GateProfile(
        risk_score=risk_score,
        risk_tier=risk_tier,
        requires_metis=risk_score >= METIS_REQUIRED_THRESHOLD,
        requires_momus_pre_review=risk_score >= MOMUS_REQUIRED_THRESHOLD,
        recommended_ulw_iterations=recommended,
        reasons=reasons,
    )


def enforce_gates(profile: GateProfile, issue_id: str, strict: bool) -> None:
    if not strict:
        return

    if profile.requires_momus_pre_review:
        if not (os.environ.get(ENV_MOMUS_APPROVED) == "1"):
            raise DispatchError(
                f"Issue {issue_id} requires Momus pre-review approval. Set {ENV_MOMUS_APPROVED}=1 to proceed."
            )

    if profile.requires_metis:
        if not (os.environ.get(ENV_METIS_APPROVED) == "1"):
            raise DispatchError(
                f"Issue {issue_id} requires Metis gate pass. Set {ENV_METIS_APPROVED}=1 to proceed."
            )


def enforce_post_review(profile: GateProfile, issue_id: str, strict: bool) -> None:
    if not strict:
        return
    if not profile.requires_momus_pre_review:
        return
    if not (os.environ.get(ENV_MOMUS_POST_APPROVED) == "1"):
        raise DispatchError(
            f"Issue {issue_id} requires Momus post-review approval. Set {ENV_MOMUS_POST_APPROVED}=1 to proceed."
        )


def run_verification_command(verify_command: str, cwd: Path) -> CommandResult:
    try:
        args = shlex.split(verify_command)
    except ValueError as exc:
        return CommandResult(
            args=[verify_command],
            returncode=2,
            stdout="",
            stderr=f"Invalid verify command: {exc}",
        )

    if not args:
        return CommandResult(
            args=[verify_command],
            returncode=2,
            stdout="",
            stderr="Verify command is empty after parsing",
        )
    return run_command(args=args, cwd=cwd)


def extract_verify_command_from_content(content: str) -> Optional[str]:
    prefixes = (
        "verify_command:",
        "verification_command:",
        "verify command:",
        "verification command:",
    )
    for line in content.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix):
                candidate = stripped[len(prefix) :].strip()
                if candidate:
                    return candidate
    return None


def resolve_verify_command(
    issue: Dict[str, Any],
    override: Optional[str],
) -> tuple[Optional[str], str]:
    if isinstance(override, str):
        stripped_override = override.strip()
        if stripped_override:
            return stripped_override, "arg"

    for key in (
        "verify_command",
        "verification_command",
        "verifyCommand",
        "verificationCommand",
    ):
        value = issue.get(key)
        if isinstance(value, str):
            stripped_value = value.strip()
            if stripped_value:
                return stripped_value, f"issue.{key}"

    content_command = extract_verify_command_from_content(
        str(issue.get("content") or "")
    )
    if content_command:
        return content_command, "issue.content"

    return None, "none"


def run_ulw_loop(
    command: str,
    message: str,
    cwd: Path,
    issue_id: str,
    agent: Optional[str],
    model: Optional[str],
    max_iterations: int,
    expected_status: str,
    verify_command: Optional[str],
    verify_command_source: str,
) -> tuple[CommandResult, int, List[Dict[str, Any]], bool, str]:
    max_iterations = max(1, max_iterations)
    attempts: List[Dict[str, Any]] = []
    result = CommandResult(
        args=[
            "opencode",
            "run",
            "--command",
            command,
            "--format",
            "default",
            message,
        ],
        returncode=1,
        stdout="",
        stderr="",
    )
    final_iteration = 0
    state_drift = False
    latest_issue_status = expected_status

    for iteration in range(1, max_iterations + 1):
        status_before = read_issue_status(issue_id=issue_id, cwd=cwd)
        attempt_result = run_opencode(
            command=command,
            message=message,
            cwd=cwd,
            agent=agent,
            model=model,
        )
        final_iteration = iteration
        result = attempt_result
        opencode_success = classify_success(attempt_result)

        verification_result = None
        verification_success = True
        if verify_command:
            verification_result = run_verification_command(
                verify_command=verify_command,
                cwd=cwd,
            )
            verification_success = verification_result.returncode == 0

        status_after = read_issue_status(issue_id=issue_id, cwd=cwd)
        latest_issue_status = status_after
        checkpoint_status = status_after
        iteration_drift = status_after != expected_status
        if not iteration_drift:
            checkpoint_status = update_issue_status(
                issue_id=issue_id,
                status=expected_status,
                fallback=None,
                cwd=cwd,
            )
            latest_issue_status = checkpoint_status

        attempt_success = (
            opencode_success and verification_success and not iteration_drift
        )
        attempts.append(
            {
                "iteration": iteration,
                "return_code": attempt_result.returncode,
                "success": attempt_success,
                "opencode_success": opencode_success,
                "status_before": status_before,
                "status_after": status_after,
                "status_checkpoint": checkpoint_status,
                "status_drift": iteration_drift,
                "verification": {
                    "command": verify_command,
                    "source": verify_command_source,
                    "skipped": verify_command is None,
                    "success": verification_success,
                    "return_code": (
                        verification_result.returncode if verification_result else None
                    ),
                    "args": verification_result.args if verification_result else None,
                },
            }
        )
        if iteration_drift:
            state_drift = True
            break
        if attempt_success:
            break

    if result is None:
        raise DispatchError("ULW loop returned no command result")

    return result, final_iteration, attempts, state_drift, latest_issue_status


def final_status_for_success(success: bool) -> str:
    return SUCCESS_STATUS if success else FAILURE_STATUS


@dataclass
class CommandResult:
    args: List[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass
class GateProfile:
    risk_score: int
    risk_tier: str
    requires_metis: bool
    requires_momus_pre_review: bool
    recommended_ulw_iterations: int
    reasons: List[str]


def utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_command(args: List[str], cwd: Path) -> CommandResult:
    completed = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        args=args,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_json(args: List[str], cwd: Path) -> Dict[str, Any]:
    result = run_command(args=args, cwd=cwd)
    if result.returncode != 0:
        raise DispatchError(
            f"Command failed ({result.returncode}): {' '.join(args)}\n{result.stderr.strip()}"
        )
    raw = result.stdout.strip()
    if not raw:
        raise DispatchError(f"Command returned empty JSON: {' '.join(args)}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DispatchError(
            f"Invalid JSON from command: {' '.join(args)}\n{raw[:500]}"
        ) from exc
    if not isinstance(payload, dict):
        raise DispatchError(f"Expected JSON object from: {' '.join(args)}")
    return payload


def run_json_list(args: List[str], cwd: Path) -> List[Dict[str, Any]]:
    result = run_command(args=args, cwd=cwd)
    if result.returncode != 0:
        raise DispatchError(
            f"Command failed ({result.returncode}): {' '.join(args)}\n{result.stderr.strip()}"
        )
    raw = result.stdout.strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DispatchError(
            f"Invalid JSON from command: {' '.join(args)}\n{raw[:500]}"
        ) from exc
    if not isinstance(payload, list):
        raise DispatchError(f"Expected JSON list from: {' '.join(args)}")
    return [item for item in payload if isinstance(item, dict)]


def pick_ready_issue(cwd: Path) -> str:
    ready_payload = run_json(["sudocode", "--json", "ready"], cwd)
    issues = ready_payload.get("issues")
    if not isinstance(issues, list) or not issues:
        raise DispatchError("No ready issues available")
    first = issues[0]
    if not isinstance(first, dict) or not first.get("id"):
        raise DispatchError("Unable to parse ready issue id")
    return str(first["id"])


def show_issue(issue_id: str, cwd: Path) -> Dict[str, Any]:
    return run_json(["sudocode", "--json", "issue", "show", issue_id], cwd)


def read_issue_status(issue_id: str, cwd: Path) -> str:
    issue = show_issue(issue_id=issue_id, cwd=cwd)
    status = str(issue.get("status") or "")
    if not status:
        raise DispatchError(f"Unable to read status for issue {issue_id}")
    return status


def rollback_issue_to_open(
    issue_id: str,
    fallback_status: str,
    cwd: Path,
    reason: str,
) -> Dict[str, Any]:
    status_before = fallback_status
    try:
        status_after = update_issue_status(
            issue_id=issue_id,
            status=FAILURE_STATUS,
            fallback=None,
            cwd=cwd,
        )
    except Exception as exc:
        status_after = status_before
        raise DispatchError(
            f"Failed to rollback issue {issue_id} to '{FAILURE_STATUS}' after {reason}: {exc}"
        ) from exc

    return {
        "rolled_back": status_before != status_after,
        "from_status": status_before,
        "to_status": status_after,
        "reason": reason,
    }


def update_issue_status(
    issue_id: str,
    status: str,
    cwd: Path,
    fallback: Optional[str] = None,
) -> str:
    args = ["sudocode", "issue", "update", issue_id, "--status", status]
    result = run_command(args=args, cwd=cwd)
    if result.returncode == 0:
        return status
    if fallback and fallback != status:
        fallback_args = ["sudocode", "issue", "update", issue_id, "--status", fallback]
        fallback_result = run_command(args=fallback_args, cwd=cwd)
        if fallback_result.returncode == 0:
            return fallback
        raise DispatchError(
            "Failed to update status and fallback failed\n"
            f"primary={status}: {result.stderr.strip()}\n"
            f"fallback={fallback}: {fallback_result.stderr.strip()}"
        )
    raise DispatchError(
        f"Failed to update issue status to '{status}': {result.stderr.strip()}"
    )


def build_message(issue: Dict[str, Any], override: Optional[str]) -> str:
    if override:
        return override
    issue_id = str(issue.get("id") or "")
    title = str(issue.get("title") or "")
    content = str(issue.get("content") or "")
    return (
        f"Issue {issue_id}: {title}\n\n"
        "Follow the issue content and complete the work fully.\n"
        "Update Sudocode state via MCP as you progress.\n\n"
        f"{content}"
    )


def run_opencode(
    command: str,
    message: str,
    cwd: Path,
    agent: Optional[str],
    model: Optional[str],
) -> CommandResult:
    normalized_command = normalize_command(command)
    if not normalized_command:
        raise DispatchError("OpenCode command is empty after normalization")

    args = [
        "opencode",
        "run",
        "--command",
        normalized_command,
        "--format",
        "default",
    ]
    if agent:
        args.extend(["--agent", agent])
    if model:
        args.extend(["--model", model])
    args.append(message)
    return run_command(args=args, cwd=cwd)


def classify_success(result: CommandResult) -> bool:
    if result.returncode != 0:
        return False
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if not stdout and not stderr:
        return False
    combined = f"{stdout}\n{stderr}"
    return not any(marker in combined for marker in FAILURE_MARKERS)


def write_artifacts_safe(
    *args: Any,
    **kwargs: Any,
) -> Optional[Path]:
    try:
        return write_artifacts(*args, **kwargs)
    except OSError as exc:
        print(
            f"dispatcher warning: failed to persist artifacts: {exc}", file=sys.stderr
        )
        return None


def write_artifacts(
    logs_dir: Path,
    issue_id: str,
    issue_title: str,
    command_result: CommandResult,
    selected_issue_status: str,
    final_issue_status: str,
    success: bool,
    gate_profile: Optional[GateProfile],
    ulw_iterations: int,
    ulw_attempts: Optional[List[Dict[str, Any]]],
    post_review: Optional[Dict[str, Any]],
    rollback: Optional[Dict[str, Any]],
    issue_status_journey: Optional[List[Dict[str, Any]]],
    verify_command: Optional[str],
    verify_command_source: str,
) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now_text()
    base_name = f"{stamp}_{issue_id}"
    log_path = logs_dir / f"{base_name}.log"
    meta_path = logs_dir / f"{base_name}.json"

    rendered_cmd = shlex.join(command_result.args)
    log_body = (
        f"# Command\n{rendered_cmd}\n\n"
        f"# Return Code\n{command_result.returncode}\n\n"
        "# STDOUT\n"
        f"{command_result.stdout}\n\n"
        "# STDERR\n"
        f"{command_result.stderr}\n"
    )
    log_path.write_text(log_body, encoding="utf-8")

    meta_payload = {
        "timestamp_utc": stamp,
        "issue_id": issue_id,
        "issue_title": issue_title,
        "selected_issue_status": selected_issue_status,
        "final_issue_status": final_issue_status,
        "success": success,
        "return_code": command_result.returncode,
        "failure_markers": [
            marker
            for marker in FAILURE_MARKERS
            if marker in f"{command_result.stdout}\n{command_result.stderr}"
        ],
        "command": command_result.args,
        "gate_profile": asdict(gate_profile) if gate_profile else None,
        "post_review": post_review,
        "rollback": rollback,
        "ulw": {
            "iterations": ulw_iterations,
            "attempts": ulw_attempts or [],
            "status_journey": issue_status_journey or [],
            "verify_command": verify_command,
            "verify_command_source": verify_command_source,
        },
    }
    meta_path.write_text(
        json.dumps(meta_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return log_path


def ensure_binary_exists(binary: str) -> None:
    path = shutil_which(binary)
    if not path:
        raise DispatchError(f"Required binary not found on PATH: {binary}")


def shutil_which(binary: str) -> Optional[str]:
    path = os.environ.get("PATH", "")
    for candidate_dir in path.split(os.pathsep):
        if not candidate_dir:
            continue
        candidate = Path(candidate_dir) / binary
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Claim a Sudocode issue, run OpenCode command execution, "
            "and reconcile issue status on success/failure."
        )
    )
    parser.add_argument("--issue-id", help="Specific Sudocode issue id (e.g. i-rxxt)")
    parser.add_argument(
        "--command",
        default="/ulw-loop",
        help="OpenCode slash command to execute via `opencode run --command`",
    )
    parser.add_argument(
        "--message",
        help="Optional explicit message payload; defaults to issue title/content",
    )
    parser.add_argument(
        "--agent",
        help="Optional OpenCode agent name passed to `opencode run --agent`",
    )
    parser.add_argument(
        "--model",
        help="Optional model override passed to `opencode run --model`",
    )
    parser.add_argument(
        "--on-success",
        default="needs_review",
        help="Issue status to set after successful execution (default: needs_review)",
    )
    parser.add_argument(
        "--on-failure",
        default="open",
        help="Issue status to set after failed execution (default: open)",
    )
    parser.add_argument(
        "--logs-dir",
        default=".sudocode/logs",
        help="Directory for dispatcher logs and metadata",
    )
    parser.add_argument(
        "--ulw-iterations",
        type=int,
        default=None,
        help="Max ULW iterations; defaults to risk-profile recommendation",
    )
    parser.add_argument(
        "--strict-gates",
        action="store_true",
        help="Require explicit environment approvals for conditional gates",
    )
    parser.add_argument(
        "--verify-command",
        help=(
            "Optional verification command to run after each ULW iteration; "
            "overrides issue-defined verification command"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and print selected issue/command without executing",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()

    normalized_command = normalize_command(args.command)
    if not normalized_command:
        print(
            "dispatcher error: OpenCode command is empty after normalization",
            file=sys.stderr,
        )
        return 1
    args.command = normalized_command

    configured_logs_dir = Path(args.logs_dir)
    if configured_logs_dir.is_absolute():
        logs_dir = configured_logs_dir
    else:
        logs_dir = repo_root / configured_logs_dir

    issue_id = ""
    issue_title = ""
    issue: Dict[str, Any] = {}
    current_status = "open"
    selected_status = current_status
    final_status = current_status
    gate_profile = GateProfile(
        risk_score=0,
        risk_tier="low",
        requires_metis=False,
        requires_momus_pre_review=False,
        recommended_ulw_iterations=1,
        reasons=[],
    )
    command_result = CommandResult(
        args=[
            "opencode",
            "run",
            "--command",
            normalized_command,
            "--format",
            "default",
        ],
        returncode=1,
        stdout="",
        stderr="",
    )
    success = False
    ulw_attempts: List[Dict[str, Any]] = []
    ulw_executed_iterations = 0
    ulw_state_drift = False
    issue_status_journey: List[Dict[str, Any]] = []
    post_review: Dict[str, Any] = {
        "required": False,
        "strict": args.strict_gates,
        "result": "not-required",
        "approval_env": ENV_MOMUS_POST_APPROVED,
    }
    rollback_info: Optional[Dict[str, Any]] = None
    verify_command: Optional[str] = None
    verify_command_source = "none"

    def persist_artifacts(artifact_status: str) -> None:
        if not issue_id:
            return
        write_artifacts_safe(
            logs_dir=logs_dir,
            issue_id=issue_id,
            issue_title=issue_title,
            command_result=command_result,
            selected_issue_status=selected_status,
            final_issue_status=artifact_status,
            success=success,
            gate_profile=gate_profile,
            ulw_iterations=ulw_executed_iterations,
            ulw_attempts=ulw_attempts,
            post_review=post_review,
            rollback=rollback_info,
            issue_status_journey=issue_status_journey,
            verify_command=verify_command,
            verify_command_source=verify_command_source,
        )

    try:
        ensure_binary_exists("sudocode")
        ensure_binary_exists("opencode")

        issue_id = args.issue_id or pick_ready_issue(repo_root)
        issue = show_issue(issue_id=issue_id, cwd=repo_root)

        current_status = str(issue.get("status") or "open")
        issue_title = str(issue.get("title") or "")
        gate_profile = build_gate_profile(issue)
        post_review["required"] = bool(
            gate_profile.requires_momus_pre_review and args.strict_gates
        )
        post_review["result"] = "required" if post_review["required"] else "optional"
        verify_command, verify_command_source = resolve_verify_command(
            issue=issue,
            override=args.verify_command,
        )
        max_iterations = (
            args.ulw_iterations
            if args.ulw_iterations
            else gate_profile.recommended_ulw_iterations
        )

        message = build_message(issue=issue, override=args.message)
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "issue_id": issue_id,
                        "issue_title": issue_title,
                        "current_status": current_status,
                        "command": normalized_command,
                        "agent": args.agent,
                        "model": args.model,
                        "gate_profile": asdict(gate_profile),
                        "ulw_config": {
                            "max_iterations": max_iterations,
                            "verify_command": verify_command,
                            "verify_command_source": verify_command_source,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        enforce_gates(gate_profile, issue_id, strict=args.strict_gates)

        if current_status not in VALID_INITIAL_STATUSES:
            raise DispatchError(
                f"Issue {issue_id} has status '{current_status}', expected open/in_progress"
            )
        selected_status = current_status
        if current_status != "in_progress":
            selected_status = update_issue_status(
                issue_id=issue_id,
                status="in_progress",
                cwd=repo_root,
            )

        result, ulw_executed_iterations, ulw_attempts, ulw_state_drift, loop_status = (
            run_ulw_loop(
                command=normalized_command,
                message=message,
                cwd=repo_root,
                issue_id=issue_id,
                agent=args.agent,
                model=args.model,
                max_iterations=max_iterations,
                expected_status="in_progress",
                verify_command=verify_command,
                verify_command_source=verify_command_source,
            )
        )
        issue_status_journey = ulw_attempts
        command_result = result

        success = bool(ulw_attempts and ulw_attempts[-1].get("success"))
        if ulw_state_drift:
            success = False

        if success and post_review["required"]:
            if args.strict_gates:
                try:
                    enforce_post_review(gate_profile, issue_id, strict=True)
                    post_review["result"] = "approved"
                except DispatchError as exc:
                    post_review["result"] = "missing"
                    success = False
                    fail_reason = str(exc)
                else:
                    fail_reason = None
            else:
                post_review["result"] = "optional"
                fail_reason = None
        else:
            fail_reason = None

        if not success:
            rollback_reason = fail_reason
            if rollback_reason is None:
                if ulw_state_drift:
                    rollback_reason = f"state drift to '{loop_status}' during ULW loop"
                else:
                    rollback_reason = "ULW execution did not succeed"
            rollback_info = rollback_issue_to_open(
                issue_id=issue_id,
                fallback_status=loop_status,
                cwd=repo_root,
                reason=rollback_reason,
            )
            final_status = rollback_info["to_status"]
        else:
            final_status = final_status_for_success(True)
            final_status = update_issue_status(
                issue_id=issue_id,
                status=final_status,
                fallback=FAILURE_STATUS,
                cwd=repo_root,
            )

        log_path = write_artifacts_safe(
            logs_dir=logs_dir,
            issue_id=issue_id,
            issue_title=issue_title,
            command_result=result,
            selected_issue_status=selected_status,
            final_issue_status=final_status,
            success=success,
            gate_profile=gate_profile,
            ulw_iterations=ulw_executed_iterations,
            ulw_attempts=ulw_attempts,
            post_review=post_review,
            rollback=rollback_info,
            issue_status_journey=issue_status_journey,
            verify_command=verify_command,
            verify_command_source=verify_command_source,
        )

        output = {
            "issue_id": issue_id,
            "selected_status": selected_status,
            "final_status": final_status,
            "success": success,
            "return_code": result.returncode,
            "ulw_executed_iterations": ulw_executed_iterations,
            "ulw_state_drift": ulw_state_drift,
            "post_review": post_review,
            "rollback": rollback_info,
            "gate_profile": asdict(gate_profile),
            "ulw_config": {
                "max_iterations": max_iterations,
                "verify_command": verify_command,
                "verify_command_source": verify_command_source,
            },
            "log_path": str(log_path) if log_path else None,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if success else 1

    except KeyboardInterrupt:
        print("dispatcher interrupted", file=sys.stderr)
        return 130
    except DispatchError as exc:
        final_status = final_status_for_success(False)
        persist_artifacts(final_status)
        print(f"dispatcher error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        final_status = final_status_for_success(False)
        persist_artifacts(final_status)
        print(f"dispatcher error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
