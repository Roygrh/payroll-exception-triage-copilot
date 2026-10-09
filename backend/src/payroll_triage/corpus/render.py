"""Render the synthetic agreement from its template and the rule parameters (ADR-007).

The rendered markdown is committed for readability; `check_agreement` verifies
that the committed file equals a fresh render so the two cannot drift.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from payroll_triage.params import RuleParameters, get_parameters
from payroll_triage.paths import corpus_dir, templates_dir

TEMPLATE_NAME = "cgma.md.j2"

_HEADING_KEY = re.compile(
    r"^#{1,3} .*\[(?P<key>[A-Z]{2,8}-\d{4}\.\d+-(?:\d{1,2}\.\d{1,2}|SCH-[A-Z]))\]\s*$"
)


def _fmt_decimal_min_one_place(value: float | Decimal) -> str:
    """Lossless decimal text with at least one decimal place (6 -> 6.0, 6.25 -> 6.25)."""
    d = Decimal(str(value)).normalize()
    text = format(d, "f")
    if "." not in text:
        text += ".0"
    return text


def _fmt_hours(value: float) -> str:
    return _fmt_decimal_min_one_place(value)


def _fmt_multiplier(value: float) -> str:
    return _fmt_decimal_min_one_place(value)


def _fmt_money(value: Decimal | float) -> str:
    return f"{Decimal(str(value)):.2f}"


_ORDINALS = {
    1: "First",
    2: "Second",
    3: "Third",
    4: "Fourth",
    5: "Fifth",
    6: "Sixth",
    7: "Seventh",
    8: "Eighth",
    9: "Ninth",
    10: "Tenth",
}


def _ordinal(n: int) -> str:
    try:
        return _ORDINALS[n]
    except KeyError as exc:
        raise ValueError(f"ordinal table covers 1 to {len(_ORDINALS)}, got {n}") from exc


def _environment(template_dir: Path | None = None) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(template_dir or templates_dir())),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    env.filters["hours"] = _fmt_hours
    env.filters["multiplier"] = _fmt_multiplier
    env.filters["money"] = _fmt_money
    env.filters["ordinal"] = _ordinal
    return env


def agreement_output_path(params: RuleParameters | None = None) -> Path:
    params = params or get_parameters()
    return corpus_dir() / f"{params.agreement.code.lower()}-{params.agreement.version}.md"


def render_agreement(params: RuleParameters | None = None, template_dir: Path | None = None) -> str:
    params = params or get_parameters()
    env = _environment(template_dir)
    template = env.get_template(TEMPLATE_NAME)
    a = params.agreement
    context = {
        "agreement": {
            "code": a.code,
            "name": a.name,
            "version": a.version,
            "effective_from": a.effective_from.isoformat(),
            "effective_to": a.effective_to.isoformat(),
            "guild": a.guild,
            "employers": a.employers,
            "citation_prefix": a.citation_prefix,
        },
        "payroll": params.payroll,
        "meal": params.meal,
        "extended_day": params.extended_day,
        "rest": params.rest,
        "eligibility": params.eligibility,
        "overtime": params.overtime,
        "plausibility": params.plausibility,
        "schedule_a": params.schedule_a,
        "rules": params.rules,
        "key": a.citation_key,
    }
    text = template.render(**context)
    if not text.endswith("\n"):
        text += "\n"
    return text


def write_agreement(params: RuleParameters | None = None) -> Path:
    params = params or get_parameters()
    out = agreement_output_path(params)
    out.write_text(render_agreement(params), encoding="utf-8", newline="\n")
    return out


def check_agreement(params: RuleParameters | None = None) -> list[str]:
    """Return a list of problems; empty when the committed file is current."""
    params = params or get_parameters()
    out = agreement_output_path(params)
    if not out.is_file():
        return [f"rendered agreement missing: {out}"]
    committed = out.read_text(encoding="utf-8").replace("\r\n", "\n")
    fresh = render_agreement(params)
    if committed != fresh:
        return [f"rendered agreement is stale: {out} differs from a fresh render"]
    return []


def citation_keys_in(text: str) -> list[str]:
    """Citation keys found in section headings, in document order."""
    keys: list[str] = []
    for line in text.splitlines():
        m = _HEADING_KEY.match(line)
        if m:
            keys.append(m.group("key"))
    return keys


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))
