from __future__ import annotations

from contextlib import contextmanager
import sqlite3
from pathlib import Path
from typing import Any
import json

import pytest

import runtime.agent_runner as agent_runner_module
from runtime.agent_runner import AgentRunner, _status_value


class _SpyGraph:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def invoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((dict(state), dict(config)))
        return {
            **state,
            "final_status": "resolved",
        }


class _PersistentCheckpointGraph:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def invoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        thread_id = config["configurable"]["thread_id"]
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_checkpoint (
                    thread_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            row = conn.execute(
                "SELECT payload FROM graph_checkpoint WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            current_state: dict[str, Any]
            if row is None:
                current_state = {}
            else:
                current_state = json.loads(row[0])

            current_state.update(state)
            conn.execute(
                """
                INSERT INTO graph_checkpoint(thread_id, payload)
                VALUES (?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET payload = excluded.payload
                """,
                (thread_id, json.dumps(current_state, sort_keys=True)),
            )
            return current_state


class _IncidentOverrideGraph:
    def __init__(self, override_incident_id: str) -> None:
        self._override_incident_id = override_incident_id

    def invoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        _ = config
        return {
            **state,
            "incident_id": self._override_incident_id,
            "final_status": "resolved",
        }


class _FinalStatusGraph:
    def __init__(self, final_status: str | None) -> None:
        self._final_status = final_status

    def invoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        _ = config
        if self._final_status is None:
            return dict(state)
        return {
            **state,
            "final_status": self._final_status,
        }


def _graph_factory_for_spy(graph: _SpyGraph):
    def _factory(*, checkpointer: object) -> _SpyGraph:
        _ = checkpointer
        return graph

    return _factory


def test_agent_runner_uses_incident_id_as_thread_id_for_invoke_and_resume(
    tmp_path: Path,
) -> None:
    graph = _SpyGraph()
    runner = AgentRunner(
        checkpoint_db_path=str(tmp_path / "checkpoints" / "agent.db"),
        graph_factory=_graph_factory_for_spy(graph),
        checkpointer_factory=lambda _path: object(),
    )

    runner.invoke(
        {
            "incident_id": "inc-001",
            "pipeline": "pipeline_silver",
            "detected_at": "2026-02-23T00:00:00+00:00",
            "fingerprint": "fp-001",
        }
    )
    runner.resume("inc-001", {"human_decision": "approve"})

    assert graph.calls[0][1] == {"configurable": {"thread_id": "inc-001"}}
    assert graph.calls[1][1] == {"configurable": {"thread_id": "inc-001"}}


def test_agent_runner_persists_incident_registry_minimal_metadata(
    tmp_path: Path,
) -> None:
    graph = _SpyGraph()
    db_path = tmp_path / "checkpoints" / "agent.db"
    runner = AgentRunner(
        checkpoint_db_path=str(db_path),
        graph_factory=_graph_factory_for_spy(graph),
        checkpointer_factory=lambda _path: object(),
    )

    runner.invoke(
        {
            "incident_id": "inc-200",
            "pipeline": "pipeline_silver",
            "detected_at": "2026-02-23T00:00:00+00:00",
            "fingerprint": "fp-200",
        }
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT incident_id, pipeline, detected_at, fingerprint, status
            FROM incident_registry
            WHERE incident_id = ?
            """,
            ("inc-200",),
        ).fetchone()

    assert row == (
        "inc-200",
        "pipeline_silver",
        "2026-02-23T00:00:00+00:00",
        "fp-200",
        "resolved",
    )


def test_agent_runner_resume_smoke_after_process_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "checkpoints" / "agent.db"

    checkpointer_factory = lambda path: Path(path)
    graph_factory = lambda *, checkpointer: _PersistentCheckpointGraph(checkpointer)

    first_runner = AgentRunner(
        checkpoint_db_path=str(db_path),
        graph_factory=graph_factory,
        checkpointer_factory=checkpointer_factory,
    )

    first_runner.invoke(
        {
            "incident_id": "inc-restart-1",
            "pipeline": "pipeline_silver",
            "detected_at": "2026-02-23T00:00:00+00:00",
            "fingerprint": "fp-restart-1",
            "action_plan": {"action": "skip_and_report"},
        }
    )

    second_runner = AgentRunner(
        checkpoint_db_path=str(db_path),
        graph_factory=graph_factory,
        checkpointer_factory=checkpointer_factory,
    )
    resumed = second_runner.resume("inc-restart-1", {"human_decision": "approve"})

    assert resumed["incident_id"] == "inc-restart-1"
    assert resumed["action_plan"] == {"action": "skip_and_report"}
    assert resumed["human_decision"] == "approve"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT incident_id, pipeline, detected_at, fingerprint, status
            FROM incident_registry
            WHERE incident_id = ?
            """,
            ("inc-restart-1",),
        ).fetchone()

    assert row == (
        "inc-restart-1",
        "pipeline_silver",
        "2026-02-23T00:00:00+00:00",
        "fp-restart-1",
        "resumed",
    )


def test_agent_runner_initializes_sqlite_saver_from_checkpoint_db_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, str] = {}

    class _FakeSqliteSaver:
        @staticmethod
        def from_conn_string(value: str) -> object:
            captured["path"] = value
            return object()

    monkeypatch.setattr(
        "runtime.agent_runner._load_sqlite_saver",
        lambda: _FakeSqliteSaver,
    )

    db_path = tmp_path / "checkpoints" / "agent.db"
    AgentRunner(
        checkpoint_db_path=str(db_path),
        graph_factory=lambda *, checkpointer: _SpyGraph(),
    )

    assert captured["path"] == str(db_path)


def test_agent_runner_uses_entered_checkpointer_when_factory_returns_context_manager(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lifecycle: dict[str, Any] = {
        "entered": False,
        "exited": False,
    }
    entered_checkpointer = object()

    class _FakeSqliteSaver:
        @staticmethod
        def from_conn_string(value: str) -> Any:
            _ = value

            @contextmanager
            def _checkpointer_cm():
                lifecycle["entered"] = True
                try:
                    yield entered_checkpointer
                finally:
                    lifecycle["exited"] = True

            return _checkpointer_cm()

    captured: dict[str, Any] = {}

    def _graph_factory(*, checkpointer: object) -> _SpyGraph:
        captured["checkpointer"] = checkpointer
        return _SpyGraph()

    monkeypatch.setattr(
        "runtime.agent_runner._load_sqlite_saver",
        lambda: _FakeSqliteSaver,
    )

    db_path = tmp_path / "checkpoints" / "agent.db"
    runner = AgentRunner(
        checkpoint_db_path=str(db_path),
        graph_factory=_graph_factory,
    )

    assert lifecycle["entered"] is True
    assert captured["checkpointer"] is entered_checkpointer

    runner.close()

    assert lifecycle["exited"] is True


def test_agent_runner_invoke_with_memory_checkpoint_path_keeps_registry_available() -> (
    None
):
    runner = AgentRunner(
        checkpoint_db_path=":memory:",
        graph_factory=lambda *, checkpointer: _SpyGraph(),
        checkpointer_factory=lambda _path: object(),
    )

    result = runner.invoke(
        {
            "incident_id": "inc-memory-1",
            "pipeline": "pipeline_silver",
            "detected_at": "2026-02-23T00:00:00+00:00",
            "fingerprint": "fp-memory-1",
        }
    )

    assert result["incident_id"] == "inc-memory-1"


def test_agent_runner_invoke_keeps_input_incident_id_when_graph_overrides_it(
    tmp_path: Path,
) -> None:
    runner = AgentRunner(
        checkpoint_db_path=str(tmp_path / "checkpoints" / "agent.db"),
        graph_factory=lambda *, checkpointer: _IncidentOverrideGraph("inc-overridden"),
        checkpointer_factory=lambda _path: object(),
    )

    result = runner.invoke(
        {
            "incident_id": "inc-stable-1",
            "pipeline": "pipeline_silver",
            "detected_at": "2026-02-23T00:00:00+00:00",
            "fingerprint": "fp-stable-1",
        }
    )

    assert result["incident_id"] == "inc-stable-1"


def test_agent_runner_resume_keeps_requested_incident_id_when_graph_overrides_it(
    tmp_path: Path,
) -> None:
    runner = AgentRunner(
        checkpoint_db_path=str(tmp_path / "checkpoints" / "agent.db"),
        graph_factory=lambda *, checkpointer: _IncidentOverrideGraph("inc-overridden"),
        checkpointer_factory=lambda _path: object(),
    )

    result = runner.resume("inc-stable-2", {"human_decision": "approve"})

    assert result["incident_id"] == "inc-stable-2"


def test_agent_runner_registry_status_keeps_terminal_status_when_resume_has_no_final_status(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "checkpoints" / "agent.db"

    resolved_runner = AgentRunner(
        checkpoint_db_path=str(db_path),
        graph_factory=lambda *, checkpointer: _FinalStatusGraph("resolved"),
        checkpointer_factory=lambda _path: object(),
    )
    resolved_runner.invoke({"incident_id": "inc-terminal-1"})

    resumed_runner = AgentRunner(
        checkpoint_db_path=str(db_path),
        graph_factory=lambda *, checkpointer: _FinalStatusGraph(None),
        checkpointer_factory=lambda _path: object(),
    )
    resumed_runner.resume("inc-terminal-1", {})

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM incident_registry WHERE incident_id = ?",
            ("inc-terminal-1",),
        ).fetchone()

    assert row == ("resolved",)


def test_agent_runner_registry_status_falls_back_to_default_for_unknown_final_status(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "checkpoints" / "agent.db"

    runner = AgentRunner(
        checkpoint_db_path=str(db_path),
        graph_factory=lambda *, checkpointer: _FinalStatusGraph("unknown"),
        checkpointer_factory=lambda _path: object(),
    )

    runner.invoke({"incident_id": "inc-status-unknown"})

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM incident_registry WHERE incident_id = ?",
            ("inc-status-unknown",),
        ).fetchone()

    assert row == ("running",)


def test_agent_runner_registry_status_update_is_atomic_against_terminal_regression(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "checkpoints" / "agent.db"
    incident_id = "inc-race-1"

    runner = AgentRunner(
        checkpoint_db_path=str(db_path),
        graph_factory=lambda *, checkpointer: _FinalStatusGraph(None),
        checkpointer_factory=lambda _path: object(),
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO incident_registry (
                incident_id,
                pipeline,
                detected_at,
                fingerprint,
                status,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id,
                None,
                None,
                None,
                "running",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()

    def _status_value_with_interleaving(
        value: Any,
        *,
        default: str,
        current: str | None = None,
    ) -> str:
        _ = (value, default, current)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE incident_registry SET status = ? WHERE incident_id = ?",
                ("resolved", incident_id),
            )
            conn.commit()
        return "running"

    monkeypatch.setattr(
        agent_runner_module,
        "_status_value",
        _status_value_with_interleaving,
    )

    runner.invoke({"incident_id": incident_id})

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM incident_registry WHERE incident_id = ?",
            (incident_id,),
        ).fetchone()

    assert row == ("resolved",)


@pytest.mark.parametrize(
    ("final_status", "default", "expected"),
    [
        ("resolved", "running", "resolved"),
        ("unknown", "running", "running"),
        (None, "resumed", "resumed"),
        ("failed", "resumed", "failed"),
    ],
)
def test_status_value_boundary_rules(
    final_status: str | None,
    default: str,
    expected: str,
) -> None:
    assert _status_value(final_status, default=default) == expected
