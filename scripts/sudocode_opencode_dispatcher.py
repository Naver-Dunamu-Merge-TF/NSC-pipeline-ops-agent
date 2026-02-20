#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
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


class DispatchError(RuntimeError):
    pass


def normalize_command(command: str) -> str:
    normalized = (command or "").strip()
    if normalized.startswith("/"):
        normalized = normalized[1:]
    return normalized.strip()


def final_status_for_success(success: bool) -> str:
    return SUCCESS_STATUS if success else FAILURE_STATUS


@dataclass
class CommandResult:
    args: List[str]
    returncode: int
    stdout: str
    stderr: str


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

    logs_dir = repo_root / ".sudocode" / "logs"

    issue_id = ""
    issue_title = ""
    issue: Dict[str, Any] = {}
    current_status = "open"
    selected_status = current_status
    final_status = current_status
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
        )

    try:
        ensure_binary_exists("sudocode")
        ensure_binary_exists("opencode")

        issue_id = args.issue_id or pick_ready_issue(repo_root)
        issue = show_issue(issue_id=issue_id, cwd=repo_root)

        current_status = str(issue.get("status") or "open")
        issue_title = str(issue.get("title") or "")

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
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

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

        result = run_opencode(
            command=normalized_command,
            message=message,
            cwd=repo_root,
            agent=args.agent,
            model=args.model,
        )
        command_result = result

        success = classify_success(result)
        final_status = final_status_for_success(success)
        final_status = update_issue_status(
            issue_id=issue_id,
            status=final_status,
            fallback=FAILURE_STATUS if success else None,
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
        )

        output = {
            "issue_id": issue_id,
            "selected_status": selected_status,
            "final_status": final_status,
            "success": success,
            "return_code": result.returncode,
            "log_path": str(log_path) if log_path else None,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if success else 1

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
    except KeyboardInterrupt:
        print("dispatcher interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
