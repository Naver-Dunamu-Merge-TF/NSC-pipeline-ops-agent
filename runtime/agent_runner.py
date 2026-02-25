from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, ExitStack
from datetime import datetime, timezone
import importlib
from pathlib import Path
import sqlite3
from typing import Any

from graph.graph import build_graph


_ALLOWED_REGISTRY_STATUSES = {
    "running",
    "resumed",
    "resolved",
    "failed",
    "escalated",
    "reported",
}


def _load_sqlite_saver() -> type[Any]:
    module = importlib.import_module("langgraph.checkpoint.sqlite")
    return module.SqliteSaver


def _ensure_parent_dir(checkpoint_db_path: str) -> None:
    if checkpoint_db_path == ":memory:":
        return
    Path(checkpoint_db_path).expanduser().resolve().parent.mkdir(
        parents=True,
        exist_ok=True,
    )


def create_sqlite_checkpointer(checkpoint_db_path: str) -> Any:
    _ensure_parent_dir(checkpoint_db_path)
    sqlite_saver = _load_sqlite_saver()
    return sqlite_saver.from_conn_string(checkpoint_db_path)


def _enter_checkpointer_if_context_manager(
    candidate: Any,
    resources: ExitStack,
) -> Any:
    if isinstance(candidate, AbstractContextManager):
        return resources.enter_context(candidate)
    return candidate


class AgentRunner:
    def __init__(
        self,
        checkpoint_db_path: str,
        graph_factory: Callable[..., Any] = build_graph,
        checkpointer_factory: Callable[[str], Any] = create_sqlite_checkpointer,
    ) -> None:
        self._checkpoint_db_path = checkpoint_db_path
        _ensure_parent_dir(checkpoint_db_path)
        self._resources = ExitStack()
        self._closed = False

        try:
            checkpointer = checkpointer_factory(checkpoint_db_path)
            if checkpointer_factory is create_sqlite_checkpointer:
                self._checkpointer = _enter_checkpointer_if_context_manager(
                    checkpointer,
                    self._resources,
                )
            else:
                self._checkpointer = checkpointer
            self._graph = graph_factory(checkpointer=self._checkpointer)
            self._registry_conn = sqlite3.connect(self._checkpoint_db_path)
            self._resources.callback(self._registry_conn.close)
            self._init_registry_table()
        except Exception:
            self._resources.close()
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._resources.close()

    def invoke(self, initial_state: Mapping[str, Any]) -> dict[str, Any]:
        incident_id = self._require_incident_id(initial_state)
        payload = dict(initial_state)
        result = self._graph.invoke(payload, config=self._thread_config(incident_id))
        merged = dict(payload)
        if isinstance(result, Mapping):
            merged.update(result)
        merged["incident_id"] = incident_id
        self._upsert_incident_registry(merged, default_status="running")
        return merged

    def resume(
        self,
        incident_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = {} if payload is None else dict(payload)
        result = self._graph.invoke(state, config=self._thread_config(incident_id))
        merged = dict(state)
        if isinstance(result, Mapping):
            merged.update(result)
        merged["incident_id"] = incident_id
        self._upsert_incident_registry(merged, default_status="resumed")
        return merged

    def _thread_config(self, incident_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": incident_id}}

    def _require_incident_id(self, state: Mapping[str, Any]) -> str:
        incident_id = state.get("incident_id")
        if not isinstance(incident_id, str) or not incident_id:
            raise ValueError("incident_id is required")
        return incident_id

    def _init_registry_table(self) -> None:
        self._registry_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incident_registry (
                incident_id TEXT PRIMARY KEY,
                pipeline TEXT,
                detected_at TEXT,
                fingerprint TEXT,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._registry_conn.commit()

    def _upsert_incident_registry(
        self,
        state: Mapping[str, Any],
        *,
        default_status: str,
    ) -> None:
        incident_id = self._require_incident_id(state)
        now = datetime.now(timezone.utc).isoformat()
        self._registry_conn.execute(
            """
            INSERT INTO incident_registry (
                incident_id,
                pipeline,
                detected_at,
                fingerprint,
                status,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(incident_id) DO UPDATE SET
                pipeline = COALESCE(excluded.pipeline, incident_registry.pipeline),
                detected_at = COALESCE(excluded.detected_at, incident_registry.detected_at),
                fingerprint = COALESCE(excluded.fingerprint, incident_registry.fingerprint),
                status = CASE
                    WHEN incident_registry.status IN ('resolved', 'failed', 'escalated', 'reported')
                        AND excluded.status IN ('running', 'resumed')
                    THEN incident_registry.status
                    ELSE excluded.status
                END,
                updated_at = excluded.updated_at
            """,
            (
                incident_id,
                _optional_text(state.get("pipeline")),
                _optional_text(state.get("detected_at")),
                _optional_text(state.get("fingerprint")),
                _status_value(state.get("final_status"), default=default_status),
                now,
            ),
        )
        self._registry_conn.commit()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _status_value(value: Any, *, default: str) -> str:
    if isinstance(value, str) and value in _ALLOWED_REGISTRY_STATUSES:
        return value
    return default
