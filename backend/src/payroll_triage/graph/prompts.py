"""Prompts and structured output schemas for the LLM nodes (ADR-018).

Two calls at most per case: `explain_propose` (one call returning the explanation and the
proposal) before the human checkpoint, and `draft` after it, only when the human chose return
or escalate, for the action the human chose.

Rules baked into every prompt (ADR-008, ADR-009): the model uses only the facts and passages it
is given, never calculates or converts units, cites by citation key in square brackets and uses
square brackets for nothing else, and proposes an action that code compares with the policy
action. Inputs are serialized compactly (ADR-018): one line of JSON per block, passages as plain
text, and only the passages of the finding's own sections plus the case's deal memo.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from payroll_triage.engine.facts import FACTS_MODELS
from payroll_triage.policy import POLICY_ROW_TEXT, SEVERITY, Situation

PROMPT_VERSION = "2026-10-10.1"


class ExplainOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str = Field(
        description="One short paragraph per finding for the approver, with citation keys in "
        "square brackets after the sentence they support."
    )
    citation_keys: list[str] = Field(description="Every citation key used in the explanation.")


class ProposeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_action: Literal["approve", "return", "escalate"]
    justification: str = Field(
        description="Why the action follows from the facts, the policy row and the passages, "
        "with citation keys in square brackets."
    )
    requested_correction: str = Field(
        description="For a return: what must be corrected or confirmed. Otherwise empty."
    )
    citation_keys: list[str] = Field(description="Every citation key used in the justification.")


class ExplainProposeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: ExplainOutput
    proposal: ProposeOutput


class DraftOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    for_action: Literal["return", "escalate"] = Field(
        description="The approver's choice this message is written for."
    )
    recipient_role: Literal["employee", "department_head", "payroll_specialist"]
    subject: str = Field(description="Short subject line.")
    body: str = Field(
        description="The message, with citation keys in square brackets after the sentence "
        "they support."
    )
    citation_keys: list[str] = Field(description="Every citation key used in the body.")


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema with every property required and no additional properties (strict mode)."""
    schema = model.model_json_schema()

    def tighten(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("title", None)  # titles are not used by the model; they only cost tokens
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for value in node.values():
                tighten(value)
        elif isinstance(node, list):
            for value in node:
                tighten(value)

    tighten(schema)
    return schema


SYSTEM_PROMPT = (
    "You assist a production accountant who triages payroll exceptions on entertainment "
    "production crew timecards. A rule engine found the findings and computed every fact; code "
    "owns the action policy.\n"
    "Rules:\n"
    "1. Use only the facts and passages given. No outside knowledge of any real agreement.\n"
    "2. Never calculate, convert units, round, count or estimate. Copy every number exactly as "
    "it appears in the facts, the case or a passage, with the unit of that fact (minutes_late "
    "in minutes, hours_late in hours). Write no other number.\n"
    "3. Cite only with the citation keys of the given passages, in square brackets, for example "
    "[<citation key>]. Square brackets are for citation keys only: never put fact names, notes "
    "or anything else in square brackets, and never write a citation key outside them.\n"
    "4. Clear, professional English. No markdown headings.\n"
    "5. Return only the requested JSON object."
)


def _dump(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


def _severity_order_text() -> str:
    return " over ".join(sorted(SEVERITY, key=lambda action: -SEVERITY[action]))


def _policy_table_text() -> str:
    return "\n".join(f"- {row.value}: {POLICY_ROW_TEXT[row]}" for row in Situation)


def case_context(case: dict[str, Any]) -> dict[str, Any]:
    """The case fields the prompts show (values as recorded, no computation). The stray-number
    check allows exactly the numbers in this context, the facts and the passages (ADR-008)."""
    return {
        "employee_name": case["employee_name"],
        "occupation": case["occupation_title"],
        "department": case["department"],
        "deal_memo_id": case["deal_memo_id"],
        "week_ending": case["week_ending"],
        "payroll_cutoff_date": case["payroll_cutoff_date"],
        "agreement_version": case["version_in_force"],
        "timecard_days_with_findings": case["days_with_findings"],
    }


def _findings_block(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": f["rule_id"],
            "section": f["section"],
            "citation_keys": f["citation_keys"],
            "day_date": f["day_date"],
            "policy_row": f["situation"],
            "policy_action": f["policy_action"],
            "facts": f["facts"],
        }
        for f in findings
    ]


def _fact_names_block(findings: list[dict[str, Any]]) -> str:
    """What each fact means, once per rule (not repeated per finding)."""
    lines = []
    for rule_id in dict.fromkeys(f["rule_id"] for f in findings):
        model = FACTS_MODELS.get(rule_id)
        if model is None:
            continue
        for name, field in model.model_fields.items():
            lines.append(f"- {rule_id}.{name}: {field.description or ''}")
    return "\n".join(lines)


def passages_for_model(
    findings: list[dict[str, Any]], chunks: list[dict[str, Any]], deal_memo_id: str
) -> list[dict[str, Any]]:
    """The passages sent to the model (ADR-018): the finding's own sections and the case's deal
    memo, in that order. Other retrieved passages are recorded but not sent."""
    by_key = {c["citation_key"]: c for c in chunks}
    keys = [k for f in findings for k in f["citation_keys"]] + [deal_memo_id]
    return [by_key[k] for k in dict.fromkeys(keys) if k in by_key]


def _passages_block(passages: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"[{c['citation_key']}] ({c['source_type']}, version {c['version']}) {c['heading']}\n"
        + c["body"].strip()
        for c in passages
    )


def _common_blocks(case: dict[str, Any], findings: list[dict], passages: list[dict]) -> str:
    return (
        "CASE:\n" + _dump(case_context(case)) + "\n\n"
        "FINDINGS (facts computed by the rule engine):\n"
        + _dump(_findings_block(findings))
        + "\n\n"
        "FACT NAMES:\n" + _fact_names_block(findings) + "\n\n"
        "PASSAGES (the only citable sources):\n" + _passages_block(passages)
    )


def explain_propose_prompt(
    case: dict[str, Any], findings: list[dict], passages: list[dict], policy_action: str
) -> str:
    return (
        "Explain the findings on this timecard to the approver, then propose the resolution.\n\n"
        + _common_blocks(case, findings, passages)
        + "\n\nPOLICY TABLE (owned by code; several findings take the most severe action, "
        + _severity_order_text()
        + "):\n"
        + _policy_table_text()
        + f"\n\nPOLICY ACTION DETERMINED BY CODE: {policy_action}\n\n"
        "explanation: one short paragraph per finding: what the agreement requires (cite the "
        "section), what the timecard shows (facts by name and value), and what follows (the "
        "penalty or the correction); cite the deal memo where the crew member's terms matter.\n"
        "proposal: the action, its justification from the facts, the policy row and the cited "
        "passages, and for a return exactly what must be corrected or confirmed."
    )


_DRAFT_GUIDANCE = {
    "return": (
        "Write the return message to the crew member (recipient_role employee) or to the "
        "department head: what is wrong on which day, what to correct or confirm, that the "
        "correction is due before the payroll cut-off date in the case, and which agreement "
        "section applies."
    ),
    "escalate": (
        "Write the escalation note to the payroll specialist (recipient_role "
        "payroll_specialist): what was found on which day, what the specialist must review, "
        "and that the timecard stays unchanged until then; cite the sections involved."
    ),
}


def draft_prompt(
    case: dict[str, Any],
    findings: list[dict],
    passages: list[dict],
    policy_action: str,
    chosen_action: str,
    explanation: str | None,
    requested_correction: str | None,
) -> str:
    """The message for the action the human chose (ADR-018), never for the proposal."""
    if chosen_action not in _DRAFT_GUIDANCE:
        raise ValueError(f"no message is drafted for {chosen_action!r}")
    context = {
        "approver_chose": chosen_action,
        "policy_action": policy_action,
        "validated_explanation": explanation or "(none: write from the facts and passages)",
    }
    if requested_correction:
        context["requested_correction"] = requested_correction
    return (
        "The approver has decided this timecard. Draft the message for the approver's choice, "
        "which may differ from the policy action.\n\n"
        + _common_blocks(case, findings, passages)
        + "\n\nDECISION:\n"
        + _dump(context)
        + "\n\n"
        + _DRAFT_GUIDANCE[chosen_action]
        + " Address the recipient by name where known. Two or three short paragraphs."
    )
