"""Fake LLM adapter for unit tests only (hard constraint 7: never used at runtime).

It implements the v1 interface and returns scripted structured outputs per
node kind (the `schema_name` of the request: `explain_propose` or `draft`), or
raises `LLMError` when told to fail, so the graph's failure paths can be
exercised without a provider.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from payroll_triage.llm.v1 import ADAPTER_VERSION, LLMError, LLMRequest, LLMResponse, Usage

Scripted = dict[str, Any] | Callable[[LLMRequest], dict[str, Any]]

_CHOSEN = re.compile(r'"approver_chose":"(\w+)"')
RECIPIENT = {"return": "employee", "escalate": "payroll_specialist"}


def chosen_action(request: LLMRequest) -> str:
    """The approver's choice as written in a draft prompt."""
    match = _CHOSEN.search(request.messages[0].content)
    assert match, "not a draft prompt"
    return match.group(1)


class FakeAdapter:
    provider = "fake"
    model = "fake-model"

    def __init__(self, outputs: dict[str, Scripted], fail: set[str] | None = None) -> None:
        self.outputs = outputs
        self.fail = fail or set()
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        kind = request.schema_name
        if kind in self.fail:
            raise LLMError(f"fake failure for {kind}", retryable=False, status=503)
        scripted = self.outputs[kind]
        parsed = scripted(request) if callable(scripted) else dict(scripted)
        return LLMResponse(
            text="",
            parsed=parsed,
            provider=self.provider,
            model=self.model,
            adapter_version=ADAPTER_VERSION,
            usage=Usage(input_tokens=10, output_tokens=5),
            latency_ms=1,
        )

    def kinds(self) -> list[str]:
        return [r.schema_name for r in self.requests]


def good_draft(section_key: str) -> Callable[[LLMRequest], dict[str, Any]]:
    """A valid draft written for the action named in the draft prompt."""

    def draft(request: LLMRequest) -> dict[str, Any]:
        action = chosen_action(request)
        return {
            "for_action": action,
            "recipient_role": RECIPIENT[action],
            "subject": "Timecard review",
            "body": f"Your timecard shows a meal finding under the agreement [{section_key}].",
            "citation_keys": [section_key],
        }

    return draft


def good_outputs(section_key: str, memo_key: str, policy_action: str) -> dict[str, Scripted]:
    """Outputs that validate: real keys, no numbers outside the facts, proposal equals policy,
    and a draft for the approver's chosen action."""
    return {
        "explain_propose": {
            "explanation": {
                "explanation": (
                    f"The first meal began after the deadline [{section_key}]; the deal memo "
                    f"gives the crew member's terms [{memo_key}]."
                ),
                "citation_keys": [section_key, memo_key],
            },
            "proposal": {
                "proposed_action": policy_action,
                "justification": f"The policy row applies [{section_key}].",
                "requested_correction": (
                    "" if policy_action != "return" else "Confirm the meal times."
                ),
                "citation_keys": [section_key],
            },
        },
        "draft": good_draft(section_key),
    }


def with_explanation(outputs: dict[str, Scripted], **changes: Any) -> dict[str, Scripted]:
    base = dict(outputs["explain_propose"])  # type: ignore[arg-type]
    return {
        **outputs,
        "explain_propose": {**base, "explanation": {**base["explanation"], **changes}},
    }


def with_proposal(outputs: dict[str, Scripted], **changes: Any) -> dict[str, Scripted]:
    base = dict(outputs["explain_propose"])  # type: ignore[arg-type]
    return {**outputs, "explain_propose": {**base, "proposal": {**base["proposal"], **changes}}}
