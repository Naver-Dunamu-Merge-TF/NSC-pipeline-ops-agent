from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys
from typing import Callable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sudocode_orchestrator.close_on_merge_runtime import (  # noqa: E402
    CloseSource,
    DispatchOutcome,
    build_operator_payload,
    dispatch_merge_close,
    preview_from_event,
)


def resolve_shared_sudocode_dir(
    working_dir: Path,
    *,
    run_fn: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Path:
    command = ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"]
    completed = run_fn(
        command,
        cwd=working_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        common_dir = completed.stdout.strip()
        if common_dir:
            candidate = Path(common_dir).parent / ".sudocode"
            return candidate.resolve()
    return (working_dir / ".sudocode").resolve()


def default_sudocode_db_path(
    working_dir: Path,
    *,
    run_fn: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    sudocode_dir = resolve_shared_sudocode_dir(working_dir, run_fn=run_fn)
    return str((sudocode_dir / "cache.db").resolve())


class SudocodeCliGateway:
    def __init__(
        self,
        *,
        working_dir: Path,
        sudocode_bin: str = "sudocode",
        db_path: str | None = None,
        sudocode_dir: Path | None = None,
        run_fn: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self._working_dir = working_dir
        self._sudocode_bin = sudocode_bin
        self._run_fn = run_fn
        if sudocode_dir is not None:
            self._sudocode_dir = sudocode_dir.resolve()
        elif db_path is None:
            self._sudocode_dir = resolve_shared_sudocode_dir(working_dir, run_fn=run_fn)
        else:
            self._sudocode_dir = (working_dir / ".sudocode").resolve()
        self._db_path = db_path or str((self._sudocode_dir / "cache.db").resolve())
        self._bootstrapped = False

    def show_issue(self, issue_id: str) -> object:
        try:
            return self._run_json("issue", "show", issue_id)
        except RuntimeError as exc:
            if "Issue not found" not in str(exc):
                raise
            self._bootstrap_from_jsonl()
            return self._run_json("issue", "show", issue_id)

    def set_issue_status(self, issue_id: str, status: str) -> None:
        self._run_json("issue", "update", issue_id, "--status", status)

    def add_feedback(self, issue_id: str, content: str) -> None:
        self._run_json("feedback", "add", issue_id, issue_id, "--content", content)

    def _bootstrap_from_jsonl(self) -> None:
        if self._bootstrapped:
            return
        command = [self._sudocode_bin]
        if self._db_path:
            command.extend(["--db", self._db_path])
        command.extend(["import", "-i", str(self._sudocode_dir)])
        completed = self._run_fn(
            command,
            cwd=self._working_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            details = stderr or stdout or "no output"
            raise RuntimeError(f"sudocode bootstrap import failed: {details}")
        self._bootstrapped = True

    def _run_json(self, *args: str) -> object:
        command = [self._sudocode_bin]
        if self._db_path:
            command.extend(["--db", self._db_path])
        command.append("--json")
        command.extend(args)
        completed = self._run_fn(
            command,
            cwd=self._working_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            details = stderr or stdout or "no output"
            raise RuntimeError(f"sudocode command failed ({' '.join(args)}): {details}")
        output = completed.stdout.strip()
        if not output:
            return {}
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("sudocode command returned non-JSON output") from exc


def _load_event_file(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"event file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"event file is not valid JSON: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("event file must contain a JSON object")
    return payload


def _serialize_outcome(outcome: DispatchOutcome, *, dry_run: bool) -> dict[str, object]:
    payload = asdict(outcome.payload) if outcome.payload is not None else None
    result = asdict(outcome.result) if outcome.result is not None else None
    serialized = {
        "invoked": outcome.invoked,
        "reason": outcome.reason,
        "payload": payload,
        "result": result,
    }
    if dry_run:
        serialized["would_invoke_merge_closer"] = payload is not None
    return serialized


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/sudocode_close_on_merge.py",
        description="Apply review-gated Sudocode issue closure on PR merge",
    )
    parser.add_argument(
        "--event-file",
        type=Path,
        help="Path to GitHub pull_request event payload JSON",
    )
    parser.add_argument("--issue-id", help="Sudocode issue ID for operator mode")
    parser.add_argument("--pr-url", help="Merged PR URL for operator mode")
    parser.add_argument("--merge-sha", help="Merge commit SHA for operator mode")
    parser.add_argument(
        "--merged-at", help="Merge timestamp (ISO-8601 UTC) for operator mode"
    )
    parser.add_argument(
        "--source",
        choices=("daemon", "workflow", "operator"),
        default=None,
        help="Merge-close event source",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate payload and print dispatch plan without state mutation",
    )
    parser.add_argument(
        "--sudocode-bin",
        default="sudocode",
        help="Sudocode CLI binary name/path (default: sudocode)",
    )
    parser.add_argument(
        "--db-path",
        default=default_sudocode_db_path(REPO_ROOT),
        help="Sudocode database path (default: shared repo .sudocode/cache.db)",
    )
    return parser


def _resolve_mode(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    has_event = args.event_file is not None
    operator_values = [args.issue_id, args.pr_url, args.merge_sha, args.merged_at]
    has_any_operator = any(value is not None for value in operator_values)
    has_all_operator = all(
        isinstance(value, str) and value.strip() for value in operator_values
    )

    if has_event and has_any_operator:
        parser.error("--event-file cannot be combined with operator mode fields")
    if has_event:
        return "event"

    if not has_all_operator:
        parser.error(
            "provide --event-file or all operator fields: "
            "--issue-id --pr-url --merge-sha --merged-at"
        )
    return "operator"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    mode = _resolve_mode(args, parser)

    source: CloseSource
    if args.source is None:
        source = "workflow" if mode == "event" else "operator"
    else:
        source = args.source

    if mode == "event" and not args.dry_run:
        parser.error("--event-file mode requires --dry-run")

    if mode == "operator" and source == "workflow":
        parser.error("operator mode cannot use --source workflow")

    if mode == "event":
        shared_sudocode_dir = resolve_shared_sudocode_dir(REPO_ROOT)
        event = _load_event_file(args.event_file)
        outcome = preview_from_event(event=event, source=source)
        if args.dry_run:
            print(json.dumps(_serialize_outcome(outcome, dry_run=True), sort_keys=True))
            return 0
        if outcome.payload is None:
            print(
                json.dumps(_serialize_outcome(outcome, dry_run=False), sort_keys=True)
            )
            return 0
        gateway = SudocodeCliGateway(
            working_dir=REPO_ROOT,
            sudocode_bin=args.sudocode_bin,
            db_path=args.db_path,
            sudocode_dir=shared_sudocode_dir,
        )
        outcome = dispatch_merge_close(payload=outcome.payload, gateway=gateway)
        print(json.dumps(_serialize_outcome(outcome, dry_run=False), sort_keys=True))
        return 0

    payload = build_operator_payload(
        issue_id=args.issue_id,
        pr_url=args.pr_url,
        merge_sha=args.merge_sha,
        merged_at=args.merged_at,
        source=source,
    )
    if args.dry_run:
        outcome = DispatchOutcome(
            invoked=False,
            reason="dry-run: merge closer invocation skipped",
            payload=payload,
            result=None,
        )
        print(json.dumps(_serialize_outcome(outcome, dry_run=True), sort_keys=True))
        return 0

    shared_sudocode_dir = resolve_shared_sudocode_dir(REPO_ROOT)
    gateway = SudocodeCliGateway(
        working_dir=REPO_ROOT,
        sudocode_bin=args.sudocode_bin,
        db_path=args.db_path,
        sudocode_dir=shared_sudocode_dir,
    )
    outcome = dispatch_merge_close(payload=payload, gateway=gateway)
    print(json.dumps(_serialize_outcome(outcome, dry_run=False), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
