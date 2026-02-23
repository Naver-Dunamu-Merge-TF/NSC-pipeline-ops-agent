from __future__ import annotations

import importlib.util

import pytest

import graph.graph as graph_module


def test_build_graph_raises_when_langgraph_is_present_but_backend_compile_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "graph.graph.importlib.util.find_spec",
        lambda name: object() if name == "langgraph.graph" else None,
    )

    def _raise_import_error(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        raise ImportError("broken langgraph runtime")

    monkeypatch.setattr(graph_module, "_build_langgraph", _raise_import_error)

    with pytest.raises(ImportError, match="broken langgraph runtime"):
        graph_module.build_graph()


def test_build_graph_uses_fallback_shim_when_langgraph_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        "graph.graph.importlib.util.find_spec",
        lambda name: None if name == "langgraph.graph" else real_find_spec(name),
    )

    graph = graph_module.build_graph()

    assert type(graph).__name__ == "_CompiledGraphShim"


def test_build_graph_uses_fallback_shim_when_find_spec_raises_module_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_find_spec = importlib.util.find_spec

    def _find_spec(name: str) -> object | None:
        if name == "langgraph.graph":
            raise ModuleNotFoundError("No module named 'langgraph'")
        return real_find_spec(name)

    monkeypatch.setattr("graph.graph.importlib.util.find_spec", _find_spec)

    graph = graph_module.build_graph()

    assert type(graph).__name__ == "_CompiledGraphShim"
