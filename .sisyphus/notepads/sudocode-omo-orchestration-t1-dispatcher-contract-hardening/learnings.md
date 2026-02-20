## Dispatcher hardening learnings

- Task used command normalization as an early step for `args.command`, ensuring both `/ulw-loop` and `ulw-loop` paths are handled consistently across dry-run and execution.
- Hardening kept status progression deterministic through `open -> in_progress -> needs_review|open` by computing final status from execution success only.
- Empty command output is now explicitly treated as execution failure in `classify_success`.
- Added resilient artifact persistence (`write_artifacts_safe`) and attempts to persist artifacts on `DispatchError`/unexpected errors when issue context is available.
- Logs and metadata are now written to `.sudocode/logs/` by default via the hardened path in `main`.
- Verified with `py_compile`, `--help`, and dry-run command path (command normalization prints `ulw-loop` for `/ulw-loop`).
