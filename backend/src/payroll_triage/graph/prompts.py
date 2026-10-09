"""Prompts and structured output schemas for the explain, propose and draft nodes.

Rules baked into every prompt (ADR-008, ADR-009): the model uses only the
facts and passages it is given, never calculates, cites by citation key, and
proposes an action that code will compare with the policy action. Prompt
templates live here with the graph, not in the adapter (ADR-002).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from payroll_triage.engine.facts import FACTS_MODELS
from payroll_triage.policy import POLICY_ROW_TEXT, SEVERITY, Situation

PROMPT_VERSION = "2026-10-08.2"


class ExplainOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str = Field(
        description="Plain-language explanation of each finding for the approver, in English, "
        "with inline citation keys in square brackets after the sentence they support."
    )
    citation_keys: list[str] = Field(
        description="Every citation key used in the explanation, from the passages provided."
    )


class ProposeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_action: Literal["approve", "return", "escalate"] = Field(
        description="The action you propose for this timecard."
    )
    justification: str = Field(
        description="Why this action follows from the findings, the facts, the policy table and "
        "the cited passages, with citation keys in square brackets."
    )
    requested_correction: str = Field(
        description="For a return: exactly what the employee or department head must correct or "
        "confirm. Empty string for approve or escalate."
    )
    citation_keys: list[str] = Field(description="Citation keys used in the justification.")


class DraftOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_role: Literal["employee", "department_head"] = Field(
        description="Who the message is addressed to."
    )
    subject: str = Field(description="Short subject line.")
    body: str = Field(
        description="The message, in English, addressed to the recipient by name: what was found "
        "on which day, what the recipient must do (or that nothing is needed), by when, and the "
        "agreement section involved, with citation keys in square brackets."
    )
    citation_keys: list[str] = Field(description="Citation keys used in the body.")


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema with every property required and no additional properties (strict mode)."""
    schema = model.model_json_schema()

    def tighten(node: Any) -> None:
        if isinstance(node, dict):
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
    "You are the explanation assistant inside a payroll exception triage copilot for "
    "entertainment production payroll. A deterministic rule engine has already detected the "
    "findings on a crew timecard and computed every fact. A retrieval step has selected "
    "passages from the collective agreement and from the crew member's deal memo.\n\n"
    "Rules you must follow:\n"
    "1. Use only the facts and passages provided in the user message. Do not use outside "
    "knowledge about any real agreement.\n"
    "2. Never calculate, convert, round, count or estimate. Every number you write must "
    "appear verbatim in the facts or in a provided passage (hours stay in decimal hours, "
    "minutes stay in minutes, amounts stay in USD with two decimals).\n"
    "3. Cite only with the citation keys of the provided passages, written in square "
    "brackets, for example [<agreement citation key>] or [<deal memo id>] exactly as given in "
    "the passages. Do not invent keys. Cite the "
    "agreement section that defines the rule and the deal memo of the crew member where it "
    "is relevant.\n"
    "4. Refer to facts by their names when useful (for example hours to meal or penalty "
    "amount).\n"
    "5. The action policy is owned by code. Code has already determined the policy action; "
    "your proposal must follow from the facts and the policy table.\n"
    "6. Write in clear, professional English for a production accountant. No markdown "
    "headings.\n"
    "7. Return only the JSON object requested."
)


def _facts_descriptions(rule_id: str) -> dict[str, str]:
    model = FACTS_MODELS[rule_id]
    return {name: (f.description or "") for name, f in model.model_fields.items()}


def _severity_order_text() -> str:
    return " over ".join(sorted(SEVERITY, key=lambda action: -SEVERITY[action]))


def _policy_table_text() -> list[str]:
    return [f"{row.value}: {POLICY_ROW_TEXT[row]}" for row in Situation]


def case_context(case: dict[str, Any]) -> dict[str, Any]:
    """The case fields every prompt shows (no computation, values as recorded)."""
    return {
        "case_id": case["case_id"],
        "timecard_id": case["timecard_id"],
        "employee_name": case["employee_name"],
        "employee_id": case["employee_id"],
        "occupation_title": case["occupation_title"],
        "occupation_code": case["occupation_code"],
        "department": case["department"],
        "deal_memo_id": case["deal_memo_id"],
        "week_ending": case["week_ending"],
        "payroll_cutoff_date": case["payroll_cutoff_date"],
        "agreement_version_in_force": case["version_in_force"],
        "days_with_findings": case["days_with_findings"],
    }


def _findings_block(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for f in findings:
        out.append(
            {
                "rule_id": f["rule_id"],
                "agreement_section": f["section"],
                "citation_keys_for_this_rule": f["citation_keys"],
                "day_date": f["day_date"],
                "policy_row": f["situation"],
                "policy_action": f["policy_action"],
                "facts": f["facts"],
                "facts_meaning": _facts_descriptions(f["rule_id"]),
            }
        )
    return out


def _passages_block(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "citation_key": c["citation_key"],
            "source": c["source_type"],
            "version": c["version"],
            "heading": c["heading"],
            "text": c["body"],
        }
        for c in chunks
    ]


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=True)


def explain_prompt(case: dict[str, Any], findings: list[dict], chunks: list[dict]) -> str:
    return (
        "Explain the findings on this timecard to the approver.\n\n"
        "CASE:\n" + _dump(case_context(case)) + "\n\n"
        "FINDINGS (facts computed by the rule engine):\n"
        + _dump(_findings_block(findings))
        + "\n\n"
        "PASSAGES (the only citable sources):\n" + _dump(_passages_block(chunks)) + "\n\n"
        "Write one short paragraph per finding: what the agreement requires (cite the section), "
        "what the timecard shows (use the facts by name and value), and what follows (the penalty "
        "or the correction), citing the deal memo for the crew member's rate or terms when "
        "relevant. Then return the JSON object."
    )


def propose_prompt(
    case: dict[str, Any], findings: list[dict], chunks: list[dict], policy_action: str
) -> str:
    return (
        "Propose the resolution for this timecard and justify it.\n\n"
        "CASE:\n" + _dump(case_context(case)) + "\n\n"
        "FINDINGS:\n" + _dump(_findings_block(findings)) + "\n\n"
        "POLICY TABLE (owned by code; several findings take the most severe action, "
        + _severity_order_text()
        + "):\n"
        + _dump(_policy_table_text())
        + "\n\n"
        f"POLICY ACTION DETERMINED BY CODE FOR THIS TIMECARD: {policy_action}\n\n"
        "PASSAGES:\n" + _dump(_passages_block(chunks)) + "\n\n"
        "State the action you propose, justify it from the facts, the policy row and the cited "
        "passages, and for a return describe precisely what must be corrected or confirmed. "
        "Return the JSON object."
    )


def draft_prompt(
    case: dict[str, Any], findings: list[dict], chunks: list[dict], proposal: dict[str, Any]
) -> str:
    return (
        "Draft the message that the approver will send about this timecard.\n\n"
        "CASE:\n" + _dump(case_context(case)) + "\n\n"
        "FINDINGS:\n" + _dump(_findings_block(findings)) + "\n\n"
        "PROPOSED RESOLUTION:\n" + _dump(proposal) + "\n\n"
        "PASSAGES:\n" + _dump(_passages_block(chunks)) + "\n\n"
        "For a return: tell the recipient what is wrong on which day, what to correct or confirm, "
        "that the correction is due before the payroll cut-off date given in the case, and which "
        "agreement section applies. For an approve: inform the recipient of the finding and that "
        "the premium is being added, nothing to do. For an escalate: inform that a payroll "
        "specialist will review and the timecard is unchanged for now. Keep it to a short "
        "message of two or three paragraphs. "
        "Return the JSON object."
    )
