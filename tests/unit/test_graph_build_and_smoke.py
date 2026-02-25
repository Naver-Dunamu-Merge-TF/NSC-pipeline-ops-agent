from __future__ import annotations

import graph.graph as graph_module
from graph.graph import END, START, build_graph


def test_build_graph_contains_required_edges_and_branches() -> None:
    graph = build_graph()

    assert (START, "detect") in graph.edges
    assert ("analyze", "triage") in graph.edges
    assert ("propose", "interrupt") in graph.edges
    assert ("execute", "verify") in graph.edges
    assert ("report_only", END) in graph.edges
    assert ("rollback", END) in graph.edges
    assert ("postmortem", END) in graph.edges

    assert graph.conditional_edges["detect"] == {
        "end": END,
        "report_only": "report_only",
        "collect": "collect",
    }
    assert graph.conditional_edges["collect"] == {
        "triage": "triage",
        "analyze": "analyze",
    }
    assert graph.conditional_edges["triage"] == {
        "report_only": "report_only",
        "propose": "propose",
    }
    assert graph.conditional_edges["interrupt"] == {
        "approve": "execute",
        "reject": "report_only",
        "modify": "propose",
        "timeout": END,
    }
    assert graph.conditional_edges["verify"] == {
        "postmortem": "postmortem",
        "rollback": "rollback",
        "end": END,
    }


def test_graph_smoke_invoke_no_issues_returns_without_error() -> None:
    graph = build_graph()

    result = graph.invoke(
        {
            "incident_id": "inc-1",
            "pipeline": "pipeline_silver",
            "run_id": "run-1",
            "detected_at": "2026-02-23T00:00:00+00:00",
            "fingerprint": "fp-1",
        }
    )

    assert result["detected_issues"] == []
    assert result["pipeline_states"] == {}


def test_graph_smoke_cutoff_delay_routes_to_report_only() -> None:
    graph = build_graph()

    result = graph.invoke(
        {
            "incident_id": "inc-cutoff-1",
            "pipeline": "pipeline_silver",
            "run_id": "run-cutoff-1",
            "detected_at": "2026-02-18T15:40:00+00:00",
            "fingerprint": "fp-cutoff-1",
            "pipeline_states": {
                "pipeline_silver": {
                    "status": "success",
                    "last_success_ts": "2026-02-18T15:09:59+00:00",
                }
            },
            "dq_status": [],
            "exception_ledger": [],
        }
    )

    assert [issue["type"] for issue in result["detected_issues"]] == ["cutoff_delay"]
    assert result["final_status"] == "reported"


def test_graph_smoke_duplicate_fingerprint_skips_collect_path() -> None:
    graph = build_graph()

    result = graph.invoke(
        {
            "incident_id": "inc-dup-1",
            "pipeline": "pipeline_silver",
            "run_id": "run-dup-1",
            "detected_at": "2026-02-18T15:40:00+00:00",
            "fingerprint": "fp-dup-1",
            "fingerprint_duplicate": True,
            "pipeline_states": {
                "pipeline_silver": {
                    "status": "failure",
                    "last_success_ts": "2026-02-18T14:00:00+00:00",
                }
            },
            "dq_status": [
                {
                    "severity": "CRITICAL",
                    "dq_tag": "SOURCE_STALE",
                }
            ],
            "exception_ledger": [{"domain": "dq", "severity": "CRITICAL"}],
        }
    )

    assert result["detected_issues"] == []


def test_build_graph_uses_langgraph_adapter_path(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "graph.graph.importlib.util.find_spec",
        lambda name: object() if name == "langgraph.graph" else None,
    )
    monkeypatch.setattr(
        graph_module, "_build_langgraph", lambda *_args, **_kwargs: object()
    )

    graph = graph_module.build_graph()

    assert graph.backend == "langgraph"
