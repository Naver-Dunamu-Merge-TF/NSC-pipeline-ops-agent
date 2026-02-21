from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sudocode_orchestrator.merge_close_daemon import (  # noqa: E402
    GhCliPoller,
    MergeCloseDaemon,
)
from sudocode_close_on_merge import SudocodeCliGateway  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/sudocode_merge_close_daemon.py",
        description="Run WSL merge-close polling daemon",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=REPO_ROOT / ".runtime" / "merge-close-checkpoint.json",
        help="Checkpoint state file path",
    )
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=REPO_ROOT / ".runtime" / "merge-close-daemon.lock",
        help="Single-instance lock file path",
    )
    parser.add_argument(
        "--heartbeat",
        type=Path,
        default=REPO_ROOT / ".runtime" / "merge-close-heartbeat.json",
        help="Heartbeat output file path",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=30.0,
        help="Polling loop interval in seconds",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=3,
        help="Maximum gh polling attempts per cycle",
    )
    parser.add_argument(
        "--retry-backoff-seconds",
        type=float,
        default=1.0,
        help="Base retry backoff for gh failures",
    )
    parser.add_argument(
        "--gh-limit",
        type=int,
        default=100,
        help="Maximum merged PR records fetched per page",
    )
    parser.add_argument(
        "--gh-bin",
        default="gh",
        help="GitHub CLI binary/path",
    )
    parser.add_argument(
        "--sudocode-bin",
        default="sudocode",
        help="Sudocode CLI binary/path",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional Sudocode DB path",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one poll cycle and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    poller = GhCliPoller(
        repo_dir=REPO_ROOT,
        gh_bin=args.gh_bin,
        per_page=args.gh_limit,
    )
    gateway = SudocodeCliGateway(
        working_dir=REPO_ROOT,
        sudocode_bin=args.sudocode_bin,
        db_path=args.db_path,
    )
    daemon = MergeCloseDaemon(
        checkpoint_path=args.checkpoint,
        lock_path=args.lock_file,
        heartbeat_path=args.heartbeat,
        gateway=gateway,
        gh_fetch=poller,
        retry_attempts=args.retry_attempts,
        retry_backoff_seconds=args.retry_backoff_seconds,
    )
    if args.once:
        daemon.run_once_with_lock()
    else:
        daemon.run_forever(poll_interval_seconds=args.poll_interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
