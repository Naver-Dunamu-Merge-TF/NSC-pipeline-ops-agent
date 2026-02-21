from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import subprocess
import time
from typing import Callable, Mapping

from . import close_on_merge_runtime as runtime
from .merge_closer import MergeCloseResult, apply_merge_close

SCHEMA_VERSION = 1
DEFAULT_WATERMARK = "1970-01-01T00:00:00Z"

ApplyFn = Callable[..., MergeCloseResult]
GhFetchFn = Callable[[str], list[dict[str, object]]]
NowFn = Callable[[], str]
SleepFn = Callable[[float], None]


class GhCommandError(RuntimeError):
    def __init__(self, message: str, *, returncode: int | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode


@dataclass(frozen=True)
class PollCycleOutcome:
    safe_mode: bool
    poll_ok: bool
    dispatched: int
    skipped: int
    retries: int


class FileLockGuard:
    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._acquired = False

    def __enter__(self) -> FileLockGuard:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb
        self.release()

    def acquire(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        pid = os.getpid()
        try:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            existing_pid = _read_pid(self._lock_path)
            if existing_pid is not None and _pid_is_alive(existing_pid):
                raise RuntimeError(
                    f"merge-close daemon already running with pid {existing_pid}"
                )
            self._lock_path.unlink(missing_ok=True)
            fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"{pid}\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._acquired = True

    def release(self) -> None:
        if not self._acquired:
            return
        self._lock_path.unlink(missing_ok=True)
        self._acquired = False


class GhCliPoller:
    def __init__(
        self,
        *,
        repo_dir: Path,
        gh_bin: str = "gh",
        per_page: int = 100,
        run_fn: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self._repo_dir = repo_dir
        self._gh_bin = gh_bin
        self._per_page = max(1, per_page)
        self._run_fn = run_fn
        self._repo_slug: str | None = None

    def __call__(self, since_merged_at: str) -> list[dict[str, object]]:
        since_dt = _parse_iso8601(since_merged_at)
        repo_slug = self._resolve_repo_slug()
        owner, name = _split_repo_slug(repo_slug)

        records: list[dict[str, object]] = []
        cursor: str | None = None
        while True:
            payload = self._run_json(self._graphql_command(owner, name, cursor))
            if not isinstance(payload, Mapping):
                raise GhCommandError("gh graphql response must be an object")
            data = payload.get("data")
            if not isinstance(data, Mapping):
                raise GhCommandError("gh graphql response missing data")
            repository = data.get("repository")
            if not isinstance(repository, Mapping):
                raise GhCommandError("gh graphql response missing repository")
            pull_requests = repository.get("pullRequests")
            if not isinstance(pull_requests, Mapping):
                raise GhCommandError("gh graphql response missing pullRequests")
            nodes = pull_requests.get("nodes")
            if not isinstance(nodes, list):
                raise GhCommandError("gh graphql response missing pull request nodes")

            if not nodes:
                break

            for item in nodes:
                if not isinstance(item, Mapping):
                    continue
                merged_at_raw = item.get("mergedAt")
                if not isinstance(merged_at_raw, str) or not merged_at_raw.strip():
                    continue
                try:
                    merged_dt = _parse_iso8601(merged_at_raw)
                except ValueError:
                    continue
                if merged_dt < since_dt:
                    continue

                number = item.get("number")
                pr_url = item.get("url")
                merge_commit = item.get("mergeCommit")
                merge_sha = (
                    merge_commit.get("oid")
                    if isinstance(merge_commit, Mapping)
                    else None
                )
                if not isinstance(number, int):
                    continue
                if not isinstance(pr_url, str) or not pr_url.strip():
                    continue
                if not isinstance(merge_sha, str) or not merge_sha.strip():
                    continue

                body_raw = item.get("body")
                body = body_raw if isinstance(body_raw, str) else ""
                records.append(
                    {
                        "number": number,
                        "url": pr_url,
                        "mergedAt": _format_iso8601(merged_dt),
                        "body": body,
                        "mergeCommit": {"oid": merge_sha},
                    }
                )

            page_info = pull_requests.get("pageInfo")
            if not isinstance(page_info, Mapping):
                break
            has_next_page = page_info.get("hasNextPage") is True
            end_cursor = page_info.get("endCursor")
            if not has_next_page:
                break
            if not isinstance(end_cursor, str) or not end_cursor:
                break
            cursor = end_cursor

        records.sort(
            key=lambda record: (
                str(record.get("mergedAt", "")),
                _sort_number(record.get("number")),
            )
        )
        return records

    def _resolve_repo_slug(self) -> str:
        if self._repo_slug is not None:
            return self._repo_slug
        payload = self._run_json(
            [
                self._gh_bin,
                "repo",
                "view",
                "--json",
                "nameWithOwner",
            ]
        )
        if not isinstance(payload, Mapping):
            raise GhCommandError("gh repo view response must be JSON object")
        slug = payload.get("nameWithOwner")
        if not isinstance(slug, str) or not slug.strip():
            raise GhCommandError("gh repo view missing nameWithOwner")
        self._repo_slug = slug
        return slug

    def _run_json(self, command: list[str]) -> object:
        completed = self._run_fn(
            command,
            cwd=self._repo_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            details = (
                completed.stderr.strip() or completed.stdout.strip() or "no output"
            )
            raise GhCommandError(details, returncode=completed.returncode)
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise GhCommandError("gh returned non-JSON output") from exc

    def _graphql_command(self, owner: str, name: str, cursor: str | None) -> list[str]:
        query = (
            "query($owner: String!, $name: String!, $first: Int!, $after: String) {"
            " repository(owner: $owner, name: $name) {"
            "  pullRequests(states: MERGED, first: $first, after: $after, "
            "orderBy: {field: UPDATED_AT, direction: DESC}) {"
            "   nodes { number url mergedAt body mergeCommit { oid } }"
            "   pageInfo { hasNextPage endCursor }"
            "  }"
            " }"
            "}"
        )
        command = [
            self._gh_bin,
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"first={self._per_page}",
        ]
        if cursor:
            command.extend(["-F", f"after={cursor}"])
        return command


class MergeCloseDaemon:
    def __init__(
        self,
        *,
        checkpoint_path: Path,
        lock_path: Path,
        heartbeat_path: Path,
        gateway: object,
        gh_fetch: GhFetchFn,
        apply_fn: ApplyFn = apply_merge_close,
        now_fn: NowFn = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        sleep_fn: SleepFn = time.sleep,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 1.0,
        lookback_seconds: int = 3600,
    ) -> None:
        self._checkpoint_path = checkpoint_path
        self._lock = FileLockGuard(lock_path)
        self._heartbeat_path = heartbeat_path
        self._gateway = gateway
        self._gh_fetch = gh_fetch
        self._apply_fn = apply_fn
        self._now_fn = now_fn
        self._sleep_fn = sleep_fn
        self._retry_attempts = max(1, retry_attempts)
        self._retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self._lookback_seconds = max(0, lookback_seconds)

        self._safe_mode = False
        self._processed: dict[str, dict[str, object]] = {}
        self._safe_mode_reason = ""
        self._watermark_merged_at = DEFAULT_WATERMARK
        self._load_checkpoint()
        if not self._safe_mode:
            self._save_checkpoint()

    def run_forever(self, *, poll_interval_seconds: float) -> None:
        with self._lock:
            while True:
                self.poll_once()
                self._sleep_fn(poll_interval_seconds)

    def run_once_with_lock(self) -> PollCycleOutcome:
        with self._lock:
            return self.poll_once()

    def poll_once(self) -> PollCycleOutcome:
        dispatched = 0
        skipped = 0
        retries = 0
        poll_ok = True
        try:
            if self._safe_mode:
                return PollCycleOutcome(
                    safe_mode=True,
                    poll_ok=False,
                    dispatched=0,
                    skipped=0,
                    retries=0,
                )

            records, retries, poll_ok = self._fetch_with_retry()
            max_seen_merged_at = self._watermark_merged_at

            if poll_ok:
                for record in records:
                    merged_at = record.get("mergedAt")
                    if isinstance(merged_at, str) and _is_newer_iso(
                        merged_at, max_seen_merged_at
                    ):
                        max_seen_merged_at = _format_iso8601(_parse_iso8601(merged_at))

                    event = _record_to_event(record)
                    if event is None:
                        skipped += 1
                        continue

                    preview = runtime.preview_from_event(event=event, source="daemon")
                    if preview.payload is None:
                        skipped += 1
                        continue

                    replay_key = _replay_identity_key(
                        pr_url=preview.payload.pr_url,
                        pr_number=record.get("number"),
                        merge_sha=preview.payload.merge_sha,
                    )
                    if replay_key in self._processed:
                        skipped += 1
                        continue

                    try:
                        outcome = runtime.dispatch_merge_close(
                            payload=preview.payload,
                            gateway=self._gateway,
                            apply_fn=self._apply_fn,
                        )
                    except Exception:
                        skipped += 1
                        continue
                    if (
                        outcome.invoked
                        and outcome.result is not None
                        and not outcome.result.applied
                        and outcome.result.reason
                        == "close allowed only from needs_review"
                    ):
                        skipped += 1
                        continue

                    if outcome.invoked:
                        self._processed[replay_key] = {
                            "pr_number": record.get("number"),
                            "merged_at": preview.payload.merged_at,
                            "pr_url": preview.payload.pr_url,
                            "issue_id": preview.payload.issue_id,
                            "merge_sha": preview.payload.merge_sha,
                            "replay_key": replay_key,
                            "processed_at": self._now_fn(),
                        }
                        dispatched += 1

                self._watermark_merged_at = max_seen_merged_at

            self._save_checkpoint()
            return PollCycleOutcome(
                safe_mode=self._safe_mode,
                poll_ok=poll_ok,
                dispatched=dispatched,
                skipped=skipped,
                retries=retries,
            )
        finally:
            self._write_heartbeat(poll_ok=poll_ok)

    def _fetch_with_retry(self) -> tuple[list[dict[str, object]], int, bool]:
        retries = 0
        since_merged_at = _subtract_lookback(
            self._watermark_merged_at,
            self._lookback_seconds,
        )
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return self._gh_fetch(since_merged_at), retries, True
            except GhCommandError:
                if attempt == self._retry_attempts:
                    return [], retries, False
                delay = self._retry_backoff_seconds * (2 ** (attempt - 1))
                retries += 1
                self._sleep_fn(delay)
        return [], retries, False

    def _load_checkpoint(self) -> None:
        if not self._checkpoint_path.exists():
            self._processed = {}
            self._watermark_merged_at = DEFAULT_WATERMARK
            return
        try:
            payload = json.loads(self._checkpoint_path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("checkpoint payload must be an object")
            if payload.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("unsupported checkpoint schema")

            processed = payload.get("processed")
            if not isinstance(processed, Mapping):
                raise ValueError("checkpoint processed must be an object")
            loaded: dict[str, dict[str, object]] = {}
            for key, value in processed.items():
                if isinstance(key, str) and isinstance(value, Mapping):
                    loaded[key] = dict(value)
            self._processed = loaded

            window = payload.get("window")
            if window is None:
                self._watermark_merged_at = DEFAULT_WATERMARK
                return
            if not isinstance(window, Mapping):
                raise ValueError("checkpoint window must be an object")
            watermark = window.get("watermark_merged_at")
            if not isinstance(watermark, str) or not watermark.strip():
                raise ValueError("checkpoint watermark must be a non-empty string")
            self._watermark_merged_at = _format_iso8601(_parse_iso8601(watermark))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            self._safe_mode = True
            self._safe_mode_reason = str(exc)

    def _save_checkpoint(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "safe_mode": self._safe_mode,
            "safe_mode_reason": self._safe_mode_reason,
            "window": {
                "watermark_merged_at": self._watermark_merged_at,
            },
            "processed": self._processed,
        }
        _atomic_write_json(self._checkpoint_path, payload)

    def _write_heartbeat(self, *, poll_ok: bool) -> None:
        operator_action = ""
        if self._safe_mode:
            operator_action = (
                "repair checkpoint file and restart daemon; use operator fallback "
                "for missed merge events"
            )
        heartbeat = {
            "updated_at": self._now_fn(),
            "safe_mode": self._safe_mode,
            "safe_mode_reason": self._safe_mode_reason,
            "operator_action": operator_action,
            "poll_ok": poll_ok,
        }
        _atomic_write_json(self._heartbeat_path, heartbeat)


def _record_to_event(record: Mapping[str, object]) -> dict[str, object] | None:
    number = record.get("number")
    pr_url = record.get("url")
    merged_at = record.get("mergedAt")
    body_value = record.get("body")
    merge_commit = record.get("mergeCommit")
    merge_sha = merge_commit.get("oid") if isinstance(merge_commit, Mapping) else None

    if not isinstance(number, int):
        return None
    if not isinstance(pr_url, str) or not pr_url.strip():
        return None
    if not isinstance(merged_at, str) or not merged_at.strip():
        return None
    if not isinstance(merge_sha, str) or not merge_sha.strip():
        return None

    body = body_value if isinstance(body_value, str) else ""
    return {
        "pull_request": {
            "merged": True,
            "html_url": pr_url,
            "merge_commit_sha": merge_sha,
            "merged_at": merged_at,
            "body": body,
        }
    }


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _read_pid(lock_path: Path) -> int | None:
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _parse_iso8601(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_iso8601(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _subtract_lookback(value: str, lookback_seconds: int) -> str:
    base = _parse_iso8601(value)
    result = base - timedelta(seconds=max(0, lookback_seconds))
    return _format_iso8601(result)


def _is_newer_iso(candidate: str, baseline: str) -> bool:
    return _parse_iso8601(candidate) > _parse_iso8601(baseline)


def _split_repo_slug(slug: str) -> tuple[str, str]:
    owner, sep, name = slug.partition("/")
    if not sep or not owner or not name:
        raise GhCommandError(f"invalid repository slug: {slug}")
    return owner, name


def _sort_number(value: object) -> int:
    return value if isinstance(value, int) else 0


def _replay_identity_key(*, pr_url: str, pr_number: object, merge_sha: str) -> str:
    if not isinstance(pr_number, int):
        raise ValueError("pr number must be an int")
    repo_slug = _repo_slug_from_pr_url(pr_url)
    return f"{repo_slug}#{pr_number}#{merge_sha}"


def _repo_slug_from_pr_url(pr_url: str) -> str:
    parsed = urlparse(pr_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        raise ValueError("invalid pull request url")
    owner, repo = path_parts[0], path_parts[1]
    if not owner or not repo:
        raise ValueError("invalid pull request url")
    return f"{owner}/{repo}"
