from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable, Literal, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sudocode_orchestrator.merge_closer import (  # noqa: E402
    MergeClosePayload,
    MergeCloseResult,
    apply_merge_close,
)

ISSUE_FIELD_RE = re.compile(r"^Sudocode-Issue:\s*(i-[a-z0-9]+)\s*$", re.MULTILINE)
CloseSource = Literal["daemon", "workflow", "operator"]
ApplyFn = Callable[..., MergeCloseResult]


@dataclass(frozen=True)
class DispatchOutcome:
    invoked: bool
    reason: str
    payload: MergeClosePayload | None
    result: MergeCloseResult | None


class SudocodeCliGateway:
    def __init__(
        self,
        *,
        working_dir: Path,
        sudocode_bin: str = "sudocode",
        db_path: str | None = None,
    ) -> None:
        self._working_dir = working_dir
        self._sudocode_bin = sudocode_bin
        self._db_path = db_path

    def show_issue(self, issue_id: str) -> object:
        return self._run_json("issue", "show", issue_id)

    def set_issue_status(self, issue_id: str, status: str) -> None:
        self._run_json("issue", "update", issue_id, "--status", status)

    def add_feedback(self, issue_id: str, content: str) -> None:
        self._run_json("feedback", "add", issue_id, issue_id, "--content", content)

    def _run_json(self, *args: str) -> object:
        command = [self._sudocode_bin]
        if self._db_path:
            command.extend(["--db", self._db_path])
        command.append("--json")
        command.extend(args)
        completed = subprocess.run(
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


def extract_sudocode_issue_id(pr_body: str) -> str:
    matches = ISSUE_FIELD_RE.findall(pr_body)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError("missing canonical Sudocode-Issue line in PR body")
    raise ValueError("multiple Sudocode-Issue lines found in PR body")


def build_payload_from_event(
    event: Mapping[str, object],
    *,
    source: CloseSource = "workflow",
) -> MergeClosePayload:
    pull_request = _as_mapping(event.get("pull_request"), "pull_request")
    merged = pull_request.get("merged") is True
    if not merged:
        raise ValueError("pull_request.merged must be true")

    body_raw = pull_request.get("body")
    body = body_raw if isinstance(body_raw, str) else ""
    issue_id = extract_sudocode_issue_id(body)

    return MergeClosePayload(
        issue_id=issue_id,
        pr_url=_required_str(pull_request, "html_url", "pull_request.html_url"),
        merge_sha=_required_str(
            pull_request,
            "merge_commit_sha",
            "pull_request.merge_commit_sha",
        ),
        merged_at=_required_str(pull_request, "merged_at", "pull_request.merged_at"),
        merged=merged,
        source=source,
    )


def build_operator_payload(
    *,
    issue_id: str,
    pr_url: str,
    merge_sha: str,
    merged_at: str,
    source: CloseSource = "operator",
) -> MergeClosePayload:
    return MergeClosePayload(
        issue_id=issue_id.strip(),
        pr_url=pr_url.strip(),
        merge_sha=merge_sha.strip(),
        merged_at=merged_at.strip(),
        merged=True,
        source=source,
    )


def dispatch_from_event(
    *,
    event: Mapping[str, object],
    gateway: object,
    source: CloseSource = "workflow",
    apply_fn: ApplyFn = apply_merge_close,
) -> DispatchOutcome:
    try:
        payload = build_payload_from_event(event, source=source)
    except ValueError as exc:
        return DispatchOutcome(
            invoked=False,
            reason=str(exc),
            payload=None,
            result=None,
        )
    return dispatch_merge_close(payload=payload, gateway=gateway, apply_fn=apply_fn)


def dispatch_merge_close(
    *,
    payload: MergeClosePayload,
    gateway: object,
    apply_fn: ApplyFn = apply_merge_close,
) -> DispatchOutcome:
    result = apply_fn(gateway=gateway, payload=payload)
    return DispatchOutcome(
        invoked=True,
        reason="merge closer invoked",
        payload=payload,
        result=result,
    )


def preview_from_event(
    *,
    event: Mapping[str, object],
    source: CloseSource = "workflow",
) -> DispatchOutcome:
    try:
        payload = build_payload_from_event(event, source=source)
    except ValueError as exc:
        return DispatchOutcome(
            invoked=False,
            reason=str(exc),
            payload=None,
            result=None,
        )
    return DispatchOutcome(
        invoked=False,
        reason="dry-run: merge closer invocation skipped",
        payload=payload,
        result=None,
    )


def _as_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _required_str(mapping: Mapping[str, object], key: str, field_name: str) -> str:
    value = mapping.get(key)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"{field_name} must be a non-empty string")


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
        "--db-path", default=None, help="Optional sudocode database path"
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

    if mode == "event":
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

    gateway = SudocodeCliGateway(
        working_dir=REPO_ROOT,
        sudocode_bin=args.sudocode_bin,
        db_path=args.db_path,
    )
    outcome = dispatch_merge_close(payload=payload, gateway=gateway)
    print(json.dumps(_serialize_outcome(outcome, dry_run=False), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
