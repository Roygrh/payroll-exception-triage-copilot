"""Chunk the rendered agreement and the deal memos into citable passages.

One chunk per anchored heading of the agreement (the heading carries the
citation key in brackets, see the template) and one chunk per deal memo whose
citation key is the memo id. Pure functions: no database, no model.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

from payroll_triage.corpus.deal_memos import DealMemo
from payroll_triage.corpus.render import agreement_output_path
from payroll_triage.params import RuleParameters

_HEADING = re.compile(
    r"^(?P<hashes>#{1,3}) (?P<title>.*?) "
    r"\[(?P<key>[A-Z]{2,8}-\d{4}\.\d+-(?:\d{1,2}\.\d{1,2}|SCH-[A-Z]))\]\s*$"
)
_DEAL_MEMO_KEY = re.compile(r"^DM-[A-Z0-9]+$")


@dataclass(frozen=True)
class Chunk:
    source_type: str  # "agreement" | "deal_memo"
    citation_key: str
    agreement_code: str | None
    version: str
    section: str
    heading: str
    body: str
    effective_from: dt.date
    effective_to: dt.date | None

    @property
    def text(self) -> str:
        return f"{self.heading}\n\n{self.body}".strip()

    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "citation_key": self.citation_key,
            "version": self.version,
            "section": self.section,
            "heading": self.heading,
            "body": self.body,
        }


def is_deal_memo_key(key: str) -> bool:
    return bool(_DEAL_MEMO_KEY.match(key))


def chunk_agreement(text: str, params: RuleParameters) -> list[Chunk]:
    a = params.agreement
    prefix = a.citation_prefix + "-"
    chunks: list[Chunk] = []
    current: dict | None = None
    body_lines: list[str] = []

    def flush() -> None:
        if current is None:
            return
        body = "\n".join(body_lines).strip()
        chunks.append(
            Chunk(
                source_type="agreement",
                citation_key=current["key"],
                agreement_code=a.code,
                version=a.version,
                section=current["section"],
                heading=current["title"],
                body=body,
                effective_from=a.effective_from,
                effective_to=a.effective_to,
            )
        )

    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            flush()
            key = m.group("key")
            if not key.startswith(prefix):
                raise ValueError(f"citation key {key} does not match prefix {prefix}")
            current = {"key": key, "title": m.group("title").strip(), "section": key[len(prefix) :]}
            body_lines = []
        elif current is not None:
            body_lines.append(line)
    flush()
    keys = [c.citation_key for c in chunks]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate citation keys in the agreement")
    return chunks


def deal_memo_passage(memo: DealMemo, params: RuleParameters) -> str:
    """A readable passage for a deal memo; the numbers are the memo's own values."""
    scale = params.scale_for(memo.occupation_code)
    verification = (
        f"completed on {memo.eligibility_completed_on.isoformat()}"
        if memo.eligibility_completed_on
        else "pending (not completed)"
    )
    allowances = (
        "; ".join(f"{x.type} {x.amount_usd:.2f} USD per {x.period}" for x in memo.allowances)
        or "none"
    )
    conditions = "; ".join(memo.conditions) or "none"
    return (
        f"Deal memo {memo.id} for {memo.employee_name} (employee {memo.employee_id}), "
        f"{memo.occupation_title} (occupation code {memo.occupation_code}), department "
        f"{memo.department}, on the production {memo.production_title} season {memo.season} "
        f"({memo.employer}). Guild: {memo.guild}. Hourly rate {memo.hourly_rate_usd:.2f} USD, "
        f"stated as {memo.scale_relationship} the Schedule A scale of "
        f"{scale.hourly_scale_usd:.2f} USD for that code. Allowances: {allowances}. "
        f"Hire state {memo.hire_state} ({memo.hire_city}); "
        f"work state {memo.work_state} ({memo.primary_work_city}). Start date "
        f"{memo.start_date.isoformat()}. Employment eligibility verification: {verification}. "
        f"Conditions: {conditions}."
    )


def chunk_deal_memo(memo: DealMemo, params: RuleParameters) -> Chunk:
    return Chunk(
        source_type="deal_memo",
        citation_key=memo.id,
        agreement_code=None,
        version=memo.id,
        section=memo.id,
        heading=f"Deal memo {memo.id}: {memo.employee_name}, {memo.occupation_title}",
        body=deal_memo_passage(memo, params),
        effective_from=memo.start_date,
        effective_to=None,
    )


def load_agreement_text(params: RuleParameters, path: Path | None = None) -> str:
    path = path or agreement_output_path(params)
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def build_corpus(
    params: RuleParameters, memos: dict[str, DealMemo], agreement_text: str | None = None
) -> list[Chunk]:
    text = agreement_text if agreement_text is not None else load_agreement_text(params)
    chunks = chunk_agreement(text, params)
    for memo in sorted(memos.values(), key=lambda m: m.id):
        chunks.append(chunk_deal_memo(memo, params))
    return chunks
