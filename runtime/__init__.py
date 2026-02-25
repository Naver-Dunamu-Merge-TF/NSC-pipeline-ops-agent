from __future__ import annotations

from typing import Any

__all__ = ["AgentRunner", "create_sqlite_checkpointer"]


def __getattr__(name: str) -> Any:
    if name in {"AgentRunner", "create_sqlite_checkpointer"}:
        from runtime.agent_runner import AgentRunner, create_sqlite_checkpointer

        return {
            "AgentRunner": AgentRunner,
            "create_sqlite_checkpointer": create_sqlite_checkpointer,
        }[name]
    raise AttributeError(f"module 'runtime' has no attribute {name!r}")
