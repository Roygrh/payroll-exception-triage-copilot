"""Assemble the state machine (architecture overview, section 4). A checkpointer is
mandatory: without one the human checkpoint could not be resumed (ADR-013)."""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from payroll_triage.graph import nodes
from payroll_triage.graph.state import CaseState

NODE_NAMES = (
    "detect",
    "retrieve",
    "explain",
    "propose",
    "draft",
    "validate",
    "needs_human_review",
    "human_checkpoint",
    "execute",
    "audit",
)


def _after_detect(state: CaseState) -> str:
    return "retrieve" if state.get("route") == "findings" else END


def _ok_or_review(next_node: str):
    def route(state: CaseState) -> str:
        return next_node if state.get("route") == "ok" else "needs_human_review"

    return route


def build_graph(deps: nodes.Deps, checkpointer: BaseCheckpointSaver):
    g: StateGraph = StateGraph(CaseState)
    g.add_node("detect", nodes.make_detect(deps))
    g.add_node("retrieve", nodes.make_retrieve(deps))
    g.add_node("explain", nodes.make_explain(deps))
    g.add_node("propose", nodes.make_propose(deps))
    g.add_node("draft", nodes.make_draft(deps))
    g.add_node("validate", nodes.make_validate(deps))
    g.add_node("needs_human_review", nodes.make_needs_human_review(deps))
    g.add_node("human_checkpoint", nodes.make_human_checkpoint(deps))
    g.add_node("execute", nodes.make_execute(deps))
    g.add_node("audit", nodes.make_audit(deps))

    g.add_edge(START, "detect")
    g.add_conditional_edges("detect", _after_detect, ["retrieve", END])
    g.add_conditional_edges("retrieve", _ok_or_review("explain"), ["explain", "needs_human_review"])
    g.add_conditional_edges("explain", _ok_or_review("propose"), ["propose", "needs_human_review"])
    g.add_conditional_edges("propose", _ok_or_review("draft"), ["draft", "needs_human_review"])
    g.add_conditional_edges("draft", _ok_or_review("validate"), ["validate", "needs_human_review"])
    g.add_conditional_edges(
        "validate", _ok_or_review("human_checkpoint"), ["human_checkpoint", "needs_human_review"]
    )
    g.add_edge("needs_human_review", "human_checkpoint")
    g.add_edge("human_checkpoint", "execute")
    g.add_edge("execute", "audit")
    g.add_edge("audit", END)
    return g.compile(checkpointer=checkpointer)
