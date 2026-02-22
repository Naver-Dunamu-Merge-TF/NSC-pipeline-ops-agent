from __future__ import annotations

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
