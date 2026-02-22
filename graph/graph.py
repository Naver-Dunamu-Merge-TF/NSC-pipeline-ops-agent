from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import importlib
from typing import Any, cast

from graph.nodes import (
    analyze,
    collect,
    detect,
    execute,
    postmortem,
    propose,
    report_only,
    rollback,
    triage,
    verify,
)
from graph.state import AgentState

START = "__start__"
END = "__end__"

NodeFn = Callable[[AgentState], dict[str, Any]]
RouteFn = Callable[[AgentState], str]


@dataclass(frozen=True)
class _GraphDefinition:
    nodes: dict[str, NodeFn]
    edges: set[tuple[str, str]]
    conditional_edges: dict[str, dict[str, str]]
    routers: dict[str, RouteFn]


class _CompiledGraphShim:
    def __init__(self, definition: _GraphDefinition):
        self.edges = definition.edges
        self.conditional_edges = definition.conditional_edges
        self._nodes = definition.nodes
        self._routers = definition.routers
        self._linear_edges = {
            source: target
            for source, target in definition.edges
            if source not in definition.conditional_edges
        }

    def invoke(
        self, state: AgentState, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        _ = config
        next_node = self._linear_edges[START]
        current_state: dict[str, Any] = dict(state)

        for _ in range(100):
            updates = self._nodes[next_node](cast(AgentState, current_state))
            if updates:
                current_state.update(updates)

            if next_node in self.conditional_edges:
                route_key = self._routers[next_node](cast(AgentState, current_state))
                next_node = self.conditional_edges[next_node][route_key]
            else:
                next_node = self._linear_edges[next_node]

            if next_node == END:
                return current_state

        raise RuntimeError("graph execution exceeded maximum steps")


class _CompiledGraphAdapter:
    def __init__(self, compiled: Any, definition: _GraphDefinition):
        self._compiled = compiled
        self.edges = definition.edges
        self.conditional_edges = definition.conditional_edges

    def invoke(
        self, state: AgentState, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if config is None:
            return self._compiled.invoke(state)
        return self._compiled.invoke(state, config=config)


def _interrupt_node(state: AgentState) -> dict[str, Any]:
    _ = state
    return {}


def _issue_kind(issue: Any) -> str:
    if isinstance(issue, dict):
        value = issue.get("type") or issue.get("kind")
        if isinstance(value, str):
            return value
    if isinstance(issue, str):
        return issue
    return ""


def _route_detect(state: AgentState) -> str:
    issues = state.get("detected_issues") or []
    if not issues:
        return "end"

    if all(_issue_kind(issue) == "cutoff_delay" for issue in issues):
        return "report_only"

    return "collect"


def _route_collect(state: AgentState) -> str:
    pipeline_states = state.get("pipeline_states") or {}
    exceptions = state.get("exceptions") or []
    dq_tags = state.get("dq_tags") or []

    has_pipeline_failure = any(
        isinstance(value, dict) and value.get("status") == "failure"
        for value in pipeline_states.values()
    )

    if dq_tags and not has_pipeline_failure and not exceptions:
        return "triage"

    return "analyze"


def _route_triage(state: AgentState) -> str:
    action_plan = state.get("action_plan") or {}
    if isinstance(action_plan, dict) and action_plan.get("action") == "skip_and_report":
        return "report_only"
    return "propose"


def _route_interrupt(state: AgentState) -> str:
    decision = state.get("human_decision")
    if decision in {"approve", "reject", "modify", "timeout"}:
        return decision
    return "timeout"


def _route_verify(state: AgentState) -> str:
    if state.get("final_status") == "resolved":
        return "postmortem"
    if state.get("final_status") == "failed":
        return "end"
    if state.get("rollback_required"):
        return "rollback"
    return "end"


def _build_definition() -> _GraphDefinition:
    nodes: dict[str, NodeFn] = {
        "detect": detect.run,
        "collect": collect.run,
        "analyze": analyze.run,
        "triage": triage.run,
        "propose": propose.run,
        "interrupt": _interrupt_node,
        "execute": execute.run,
        "verify": verify.run,
        "rollback": rollback.run,
        "report_only": report_only.run,
        "postmortem": postmortem.run,
    }

    edges = {
        (START, "detect"),
        ("analyze", "triage"),
        ("propose", "interrupt"),
        ("execute", "verify"),
        ("report_only", END),
        ("rollback", END),
        ("postmortem", END),
    }

    conditional_edges = {
        "detect": {
            "end": END,
            "report_only": "report_only",
            "collect": "collect",
        },
        "collect": {
            "triage": "triage",
            "analyze": "analyze",
        },
        "triage": {
            "report_only": "report_only",
            "propose": "propose",
        },
        "interrupt": {
            "approve": "execute",
            "reject": "report_only",
            "modify": "propose",
            "timeout": END,
        },
        "verify": {
            "postmortem": "postmortem",
            "rollback": "rollback",
            "end": END,
        },
    }

    routers: dict[str, RouteFn] = {
        "detect": _route_detect,
        "collect": _route_collect,
        "triage": _route_triage,
        "interrupt": _route_interrupt,
        "verify": _route_verify,
    }

    return _GraphDefinition(
        nodes=nodes,
        edges=edges,
        conditional_edges=conditional_edges,
        routers=routers,
    )


def _build_langgraph(definition: _GraphDefinition, checkpointer: Any | None) -> Any:
    module = importlib.import_module("langgraph.graph")
    LG_END = module.END
    LG_START = module.START
    StateGraph = module.StateGraph

    builder = StateGraph(AgentState)
    for node_name, node_fn in definition.nodes.items():
        builder.add_node(node_name, node_fn)

    for source, target in definition.edges:
        actual_source = LG_START if source == START else source
        actual_target = LG_END if target == END else target
        builder.add_edge(actual_source, actual_target)

    for source, route_map in definition.conditional_edges.items():
        mapped = {
            route_key: (LG_END if target == END else target)
            for route_key, target in route_map.items()
        }

        def _route(state: AgentState, node: str = source) -> str:
            return definition.routers[node](state)

        builder.add_conditional_edges(source, _route, mapped)

    if checkpointer is None:
        return builder.compile()
    return builder.compile(checkpointer=checkpointer)


def build_graph(checkpointer: Any | None = None) -> Any:
    definition = _build_definition()

    try:
        compiled = _build_langgraph(definition, checkpointer=checkpointer)
        return _CompiledGraphAdapter(compiled, definition)
    except ImportError:
        return _CompiledGraphShim(definition)
