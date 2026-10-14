"""Assemble the state machine (architecture overview, section 4; ADR-018). A checkpointer is
mandatory: without one the human checkpoints could not be resumed (ADR-013)."""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from payroll_triage.graph import nodes
from payroll_triage.graph.execute import MESSAGE_ACTIONS
from payroll_triage.graph.state import CaseState

NODE_NAMES = (
    "detect",
    "retrieve",
    "explain_propose",
    "validate",
    "needs_human_review",
    "human_checkpoint",
    "draft",
    "validate_draft",
    "message_checkpoint",
    "execute",
    "audit",
)


def _after_detect(state: CaseState) -> str:
    return "retrieve" if state.get("route") == "findings" else END


def _ok_or_review(next_node: str):
    def route(state: CaseState) -> str:
        return next_node if state.get("route") == "ok" else "needs_human_review"

    return route


def _after_choice(state: CaseState) -> str:
    """Approve executes; return and escalate draft the message for the human's choice."""
    return "draft" if (state.get("decision") or {}).get("action") in MESSAGE_ACTIONS else "execute"


def _after_message(state: CaseState) -> str:
    return "human_checkpoint" if state.get("route") == "cancel" else "execute"


def build_graph(deps: nodes.Deps, checkpointer: BaseCheckpointSaver):
    g: StateGraph = StateGraph(CaseState)
    g.add_node("detect", nodes.make_detect(deps))
    g.add_node("retrieve", nodes.make_retrieve(deps))
    g.add_node("explain_propose", nodes.make_explain_propose(deps))
    g.add_node("validate", nodes.make_validate(deps))
    g.add_node("needs_human_review", nodes.make_needs_human_review(deps))
    g.add_node("human_checkpoint", nodes.make_human_checkpoint(deps))
    g.add_node("draft", nodes.make_draft(deps))
    g.add_node("validate_draft", nodes.make_validate_draft(deps))
    g.add_node("message_checkpoint", nodes.make_message_checkpoint(deps))
    g.add_node("execute", nodes.make_execute(deps))
    g.add_node("audit", nodes.make_audit(deps))

    g.add_edge(START, "detect")
    g.add_conditional_edges("detect", _after_detect, ["retrieve", END])
    g.add_conditional_edges(
        "retrieve", _ok_or_review("explain_propose"), ["explain_propose", "needs_human_review"]
    )
    g.add_conditional_edges(
        "explain_propose", _ok_or_review("validate"), ["validate", "needs_human_review"]
    )
    g.add_conditional_edges(
        "validate", _ok_or_review("human_checkpoint"), ["human_checkpoint", "needs_human_review"]
    )
    g.add_edge("needs_human_review", "human_checkpoint")
    g.add_conditional_edges("human_checkpoint", _after_choice, ["draft", "execute"])
    g.add_edge("draft", "validate_draft")
    g.add_edge("validate_draft", "message_checkpoint")
    g.add_conditional_edges("message_checkpoint", _after_message, ["human_checkpoint", "execute"])
    g.add_edge("execute", "audit")
    g.add_edge("audit", END)
    return g.compile(checkpointer=checkpointer)
