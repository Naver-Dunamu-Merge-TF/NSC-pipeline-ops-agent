from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from sudocode_orchestrator import merge_close_daemon as MOD
from sudocode_orchestrator.merge_closer import MergeCloseResult


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _load_merged_prs() -> list[dict[str, object]]:
    raw = (FIXTURES_DIR / "github_prs_merged.json").read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert isinstance(payload, list)
    return payload


def _make_apply_calls() -> tuple[list[str], object]:
    calls: list[str] = []

    def _fake_apply(*, gateway: object, payload: object) -> MergeCloseResult:
        del gateway
        merge_sha = getattr(payload, "merge_sha")
        calls.append(merge_sha)
        return MergeCloseResult(
            applied=True,
            reason="ok",
            feedback_marker="MERGE_CLOSE_APPLIED",
        )

    return calls, _fake_apply


def _make_rejecting_apply_calls() -> tuple[list[str], object]:
    calls: list[str] = []

    def _reject_apply(*, gateway: object, payload: object) -> MergeCloseResult:
        del gateway
        merge_sha = getattr(payload, "merge_sha")
        calls.append(merge_sha)
        return MergeCloseResult(
            applied=False,
            reason="close allowed only from needs_review",
            feedback_marker="MERGE_CLOSE_REJECTED",
        )

    return calls, _reject_apply


def _read_checkpoint(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _completed(command: list[str], payload: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=command,
        returncode=0,
        stdout=f"{json.dumps(payload)}\n",
        stderr="",
    )


def test_new_merged_pr_dispatched_once_and_heartbeat_advances(tmp_path: Path) -> None:
    prs = _load_merged_prs()
    calls, apply_fn = _make_apply_calls()
    timestamps = iter(
        [
            "2026-02-22T12:00:00Z",
            "2026-02-22T12:00:30Z",
            "2026-02-22T12:01:00Z",
        ]
    )

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=tmp_path / "checkpoint.json",
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=lambda _since: [prs[0]],
        apply_fn=apply_fn,
        now_fn=lambda: next(timestamps),
    )

    first = daemon.poll_once()
    second = daemon.poll_once()

    assert first.safe_mode is False
    assert second.safe_mode is False
    assert calls == ["sha-a"]
    heartbeat = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["updated_at"] == "2026-02-22T12:01:00Z"
    checkpoint = _read_checkpoint(tmp_path / "checkpoint.json")
    assert checkpoint["window"]["watermark_merged_at"] == "2026-02-22T10:00:00Z"


def test_already_checkpointed_merge_is_skipped(tmp_path: Path) -> None:
    prs = _load_merged_prs()
    calls, apply_fn = _make_apply_calls()
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "safe_mode": False,
                "processed": {
                    "acme/repo#101#sha-a": {
                        "pr_number": 101,
                        "merged_at": "2026-02-22T10:00:00Z",
                    }
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=checkpoint_path,
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=lambda _since: [prs[0]],
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T12:00:00Z",
    )

    daemon.poll_once()

    assert calls == []


def test_invalid_canonical_field_is_skipped_without_mutation(tmp_path: Path) -> None:
    calls, apply_fn = _make_apply_calls()

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=tmp_path / "checkpoint.json",
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=lambda _since: [
            {
                "number": 301,
                "url": "https://github.com/acme/repo/pull/301",
                "mergedAt": "2026-02-22T13:00:00Z",
                "body": "No canonical line",
                "mergeCommit": {"oid": "sha-invalid"},
            }
        ],
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T13:01:00Z",
    )

    daemon.poll_once()

    checkpoint = _read_checkpoint(tmp_path / "checkpoint.json")
    assert calls == []
    assert checkpoint["processed"] == {}


def test_successful_dispatch_advances_checkpoint(tmp_path: Path) -> None:
    prs = _load_merged_prs()
    calls, apply_fn = _make_apply_calls()

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=tmp_path / "checkpoint.json",
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=lambda _since: [prs[0]],
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T14:00:00Z",
    )

    daemon.poll_once()

    checkpoint = _read_checkpoint(tmp_path / "checkpoint.json")
    assert calls == ["sha-a"]
    key = "acme/repo#101#sha-a"
    assert checkpoint["processed"][key]["pr_number"] == 101
    assert checkpoint["processed"][key]["merged_at"] == "2026-02-22T10:00:00Z"


def test_gh_failures_retry_with_bound_and_do_not_mutate_state(tmp_path: Path) -> None:
    calls, apply_fn = _make_apply_calls()
    attempts = 0
    sleeps: list[float] = []

    def _failing_fetch(_: str) -> list[dict[str, object]]:
        nonlocal attempts
        attempts += 1
        raise MOD.GhCommandError("gh command failed", returncode=1)

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=tmp_path / "checkpoint.json",
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=_failing_fetch,
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T15:00:00Z",
        retry_attempts=3,
        retry_backoff_seconds=1.0,
        sleep_fn=lambda seconds: sleeps.append(seconds),
    )

    cycle = daemon.poll_once()

    checkpoint = _read_checkpoint(tmp_path / "checkpoint.json")
    assert cycle.poll_ok is False
    assert attempts == 3
    assert sleeps == [1.0, 2.0]
    assert calls == []
    assert checkpoint["processed"] == {}


def test_malformed_record_is_skipped_without_crash(tmp_path: Path) -> None:
    prs = _load_merged_prs()
    calls, apply_fn = _make_apply_calls()

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=tmp_path / "checkpoint.json",
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=lambda _since: [
            {
                "number": "bad",
                "url": "https://github.com/acme/repo/pull/bad",
                "mergedAt": None,
                "body": "Sudocode-Issue: i-aa11",
                "mergeCommit": {},
            },
            prs[0],
        ],
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T16:00:00Z",
    )

    cycle = daemon.poll_once()

    assert cycle.poll_ok is True
    assert calls == ["sha-a"]


def test_dispatch_failure_is_skipped_and_does_not_crash(tmp_path: Path) -> None:
    prs = _load_merged_prs()
    calls: list[str] = []

    def _raise_apply(*, gateway: object, payload: object) -> MergeCloseResult:
        del gateway
        calls.append(getattr(payload, "merge_sha"))
        raise RuntimeError("Issue not found")

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=tmp_path / "checkpoint.json",
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=lambda _since: [prs[0]],
        apply_fn=_raise_apply,
        now_fn=lambda: "2026-02-22T16:10:00Z",
    )

    cycle = daemon.poll_once()

    checkpoint = _read_checkpoint(tmp_path / "checkpoint.json")
    assert cycle.poll_ok is True
    assert cycle.dispatched == 0
    assert cycle.skipped == 1
    assert calls == ["sha-a"]
    assert checkpoint["processed"] == {}


def test_multiple_sudocode_issue_lines_is_skipped_without_mutation(
    tmp_path: Path,
) -> None:
    calls, apply_fn = _make_apply_calls()

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=tmp_path / "checkpoint.json",
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=lambda _since: [
            {
                "number": 302,
                "url": "https://github.com/acme/repo/pull/302",
                "mergedAt": "2026-02-22T13:05:00Z",
                "body": "Sudocode-Issue: i-aa11\nSudocode-Issue: i-bb22\n",
                "mergeCommit": {"oid": "sha-multiple"},
            }
        ],
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T13:06:00Z",
    )

    cycle = daemon.poll_once()

    checkpoint = _read_checkpoint(tmp_path / "checkpoint.json")
    assert cycle.poll_ok is True
    assert calls == []
    assert checkpoint["processed"] == {}


def test_restart_replay_dispatches_only_new_merge_sha(tmp_path: Path) -> None:
    prs = _load_merged_prs()
    calls, apply_fn = _make_apply_calls()
    checkpoint_path = tmp_path / "checkpoint.json"

    first = MOD.MergeCloseDaemon(
        checkpoint_path=checkpoint_path,
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=lambda _since: [prs[0]],
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T17:00:00Z",
    )
    first.poll_once()

    second = MOD.MergeCloseDaemon(
        checkpoint_path=checkpoint_path,
        lock_path=tmp_path / "daemon2.lock",
        heartbeat_path=tmp_path / "heartbeat2.json",
        gateway=object(),
        gh_fetch=lambda _since: [prs[0], prs[1]],
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T17:01:00Z",
    )
    second.poll_once()

    assert calls == ["sha-a", "sha-b"]


def test_replay_identity_key_uses_repo_pr_and_sha(tmp_path: Path) -> None:
    calls, apply_fn = _make_apply_calls()

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=tmp_path / "checkpoint.json",
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=lambda _since: [
            {
                "number": 101,
                "url": "https://github.com/acme/repo/pull/101",
                "mergedAt": "2026-02-22T10:00:00Z",
                "body": "Sudocode-Issue: i-aa11\n",
                "mergeCommit": {"oid": "sha-same"},
            },
            {
                "number": 500,
                "url": "https://github.com/other/repo/pull/500",
                "mergedAt": "2026-02-22T10:10:00Z",
                "body": "Sudocode-Issue: i-cc33\n",
                "mergeCommit": {"oid": "sha-same"},
            },
        ],
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T17:30:00Z",
    )

    daemon.poll_once()

    checkpoint = _read_checkpoint(tmp_path / "checkpoint.json")
    assert calls == ["sha-same", "sha-same"]
    assert "acme/repo#101#sha-same" in checkpoint["processed"]
    assert "other/repo#500#sha-same" in checkpoint["processed"]


def test_corrupt_checkpoint_enters_safe_mode(tmp_path: Path) -> None:
    calls, apply_fn = _make_apply_calls()
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text("{not-json", encoding="utf-8")
    fetch_calls = 0

    def _fetch(_: str) -> list[dict[str, object]]:
        nonlocal fetch_calls
        fetch_calls += 1
        return []

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=checkpoint_path,
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=_fetch,
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T18:00:00Z",
    )

    cycle = daemon.poll_once()

    assert cycle.safe_mode is True
    assert fetch_calls == 0
    assert calls == []
    heartbeat = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["safe_mode"] is True
    assert isinstance(heartbeat.get("safe_mode_reason"), str)
    assert "operator fallback" in heartbeat.get("operator_action", "")


def test_issue_not_needs_review_is_not_checkpointed(tmp_path: Path) -> None:
    prs = _load_merged_prs()
    calls, apply_fn = _make_rejecting_apply_calls()

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=tmp_path / "checkpoint.json",
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=lambda _since: [prs[0]],
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T18:30:00Z",
    )

    cycle = daemon.poll_once()

    checkpoint = _read_checkpoint(tmp_path / "checkpoint.json")
    assert calls == ["sha-a"]
    assert cycle.dispatched == 0
    assert cycle.skipped == 1
    assert checkpoint["processed"] == {}


def test_checkpoint_window_watermark_drives_effective_fetch_since(
    tmp_path: Path,
) -> None:
    calls, apply_fn = _make_apply_calls()
    requested_since: list[str] = []
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "safe_mode": False,
                "processed": {},
                "window": {"watermark_merged_at": "2026-02-22T12:00:00Z"},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    def _fetch(since_merged_at: str) -> list[dict[str, object]]:
        requested_since.append(since_merged_at)
        return []

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=checkpoint_path,
        lock_path=tmp_path / "daemon.lock",
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=_fetch,
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T12:10:00Z",
        lookback_seconds=60,
    )

    daemon.poll_once()

    assert calls == []
    assert requested_since == ["2026-02-22T11:59:00Z"]


def test_file_lock_guard_rejects_live_owner_pid(tmp_path: Path) -> None:
    lock_path = tmp_path / "daemon.lock"
    lock_path.write_text("12345\n", encoding="utf-8")
    guard = MOD.FileLockGuard(lock_path)

    original = MOD._pid_is_alive
    MOD._pid_is_alive = lambda _pid: True
    try:
        with pytest.raises(RuntimeError, match="already running"):
            guard.acquire()
    finally:
        MOD._pid_is_alive = original


def test_file_lock_guard_replaces_stale_lock_owner(tmp_path: Path) -> None:
    lock_path = tmp_path / "daemon.lock"
    lock_path.write_text("12345\n", encoding="utf-8")
    guard = MOD.FileLockGuard(lock_path)

    original = MOD._pid_is_alive
    MOD._pid_is_alive = lambda _pid: False
    try:
        guard.acquire()
        assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())
        guard.release()
        assert lock_path.exists() is False
    finally:
        MOD._pid_is_alive = original


def test_run_once_with_lock_rejects_live_owner_pid(tmp_path: Path) -> None:
    lock_path = tmp_path / "daemon.lock"
    lock_path.write_text("12345\n", encoding="utf-8")
    calls, apply_fn = _make_apply_calls()

    daemon = MOD.MergeCloseDaemon(
        checkpoint_path=tmp_path / "checkpoint.json",
        lock_path=lock_path,
        heartbeat_path=tmp_path / "heartbeat.json",
        gateway=object(),
        gh_fetch=lambda _since: [],
        apply_fn=apply_fn,
        now_fn=lambda: "2026-02-22T19:00:00Z",
    )

    original = MOD._pid_is_alive
    MOD._pid_is_alive = lambda _pid: True
    try:
        with pytest.raises(RuntimeError, match="already running"):
            daemon.run_once_with_lock()
    finally:
        MOD._pid_is_alive = original

    assert calls == []


def test_gh_cli_poller_paginates_and_sorts_out_of_order_records(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def _run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        command = args[0]
        assert isinstance(command, list)
        calls.append(command)

        if command[1:3] == ["repo", "view"]:
            return _completed(command, {"nameWithOwner": "acme/repo"})

        if command[1:3] == ["api", "graphql"]:
            has_after = any(
                isinstance(arg, str) and arg == "after=cursor-1" for arg in command
            )
            if not has_after:
                return _completed(
                    command,
                    {
                        "data": {
                            "repository": {
                                "pullRequests": {
                                    "nodes": [
                                        {
                                            "number": 200,
                                            "url": "https://github.com/acme/repo/pull/200",
                                            "mergedAt": "2026-02-22T12:05:00Z",
                                            "body": "Sudocode-Issue: i-bb22",
                                            "mergeCommit": {"oid": "sha-200"},
                                        }
                                    ],
                                    "pageInfo": {
                                        "hasNextPage": True,
                                        "endCursor": "cursor-1",
                                    },
                                }
                            }
                        }
                    },
                )

            return _completed(
                command,
                {
                    "data": {
                        "repository": {
                            "pullRequests": {
                                "nodes": [
                                    {
                                        "number": 101,
                                        "url": "https://github.com/acme/repo/pull/101",
                                        "mergedAt": "2026-02-22T12:01:00Z",
                                        "body": "Sudocode-Issue: i-aa11",
                                        "mergeCommit": {"oid": "sha-101"},
                                    }
                                ],
                                "pageInfo": {
                                    "hasNextPage": False,
                                    "endCursor": None,
                                },
                            }
                        }
                    }
                },
            )

        raise AssertionError(f"unexpected gh command: {command}")

    poller = MOD.GhCliPoller(repo_dir=tmp_path, gh_bin="gh", per_page=1, run_fn=_run)

    records = poller("2026-02-22T12:00:00Z")

    assert [record["number"] for record in records] == [101, 200]
    assert any(arg == "after=cursor-1" for arg in calls[2])


def test_gh_cli_poller_does_not_drop_newer_records_on_later_pages(
    tmp_path: Path,
) -> None:
    graphql_calls = 0

    def _run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal graphql_calls
        del kwargs
        command = args[0]
        assert isinstance(command, list)

        if command[1:3] == ["repo", "view"]:
            return _completed(command, {"nameWithOwner": "acme/repo"})

        if command[1:3] == ["api", "graphql"]:
            graphql_calls += 1
            has_after = any(
                isinstance(arg, str) and arg == "after=cursor-older" for arg in command
            )
            if not has_after:
                return _completed(
                    command,
                    {
                        "data": {
                            "repository": {
                                "pullRequests": {
                                    "nodes": [
                                        {
                                            "number": 90,
                                            "url": "https://github.com/acme/repo/pull/90",
                                            "mergedAt": "2026-02-22T11:58:00Z",
                                            "body": "Sudocode-Issue: i-old1",
                                            "mergeCommit": {"oid": "sha-old"},
                                        }
                                    ],
                                    "pageInfo": {
                                        "hasNextPage": True,
                                        "endCursor": "cursor-older",
                                    },
                                }
                            }
                        }
                    },
                )

            return _completed(
                command,
                {
                    "data": {
                        "repository": {
                            "pullRequests": {
                                "nodes": [
                                    {
                                        "number": 120,
                                        "url": "https://github.com/acme/repo/pull/120",
                                        "mergedAt": "2026-02-22T12:02:00Z",
                                        "body": "Sudocode-Issue: i-new1",
                                        "mergeCommit": {"oid": "sha-new"},
                                    }
                                ],
                                "pageInfo": {
                                    "hasNextPage": False,
                                    "endCursor": None,
                                },
                            }
                        }
                    }
                },
            )

        raise AssertionError(f"unexpected gh command: {command}")

    poller = MOD.GhCliPoller(repo_dir=tmp_path, gh_bin="gh", per_page=1, run_fn=_run)

    records = poller("2026-02-22T12:00:00Z")

    assert graphql_calls == 2
    assert [record["number"] for record in records] == [120]
