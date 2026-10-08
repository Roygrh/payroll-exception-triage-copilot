"""Evaluation case manifest builder (P1.I1.S6).

One case per scenario (EV-NN for SC-NN): expected rule ids, sections, citation
keys, policy action and the engine facts by construction. Clean weeks are
negative cases. Filler crew are not cases (they exist to make the queue look
real); the generator tests assert they raise nothing.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from payroll_triage.corpus.deal_memos import DealMemo, load_deal_memos
from payroll_triage.data.generator import GeneratedData, generate
from payroll_triage.data.scenarios import Catalog, load_catalog
from payroll_triage.evals.expectations import combined_action, expected_findings
from payroll_triage.params import RuleParameters, get_parameters
from payroll_triage.paths import manifest_path

MANIFEST_VERSION = 1


def _case_id(scenario_id: str) -> str:
    return "EV-" + scenario_id.split("-", 1)[1]


def build_manifest(
    catalog: Catalog | None = None,
    data: GeneratedData | None = None,
    params: RuleParameters | None = None,
    memos: dict[str, DealMemo] | None = None,
) -> dict[str, Any]:
    catalog = catalog or load_catalog()
    params = params or get_parameters()
    memos = memos or load_deal_memos()
    data = data or generate(catalog, memos, params)
    by_scenario = {t.scenario_id: t for t in data.timecards}
    work_day_type = catalog.labels["day_type"]["work"]

    cases: list[dict[str, Any]] = []
    for scenario in catalog.scenarios:
        tc = by_scenario[scenario.id]
        memo = memos[scenario.deal_memo]
        findings = expected_findings(
            tc, memo, params, catalog.as_of_date, catalog.holidays, work_day_type
        )
        action = combined_action(findings)
        rules = sorted({f.rule_id for f in findings})
        if rules != sorted(set(scenario.expected_rules)) or action != scenario.expected_action:
            raise ValueError(
                f"{scenario.id}: construction yields {rules} / {action} but the catalog "
                f"expects {sorted(scenario.expected_rules)} / {scenario.expected_action}"
            )
        cases.append(
            {
                "id": _case_id(scenario.id),
                "scenario_id": scenario.id,
                "description": scenario.description,
                "category": scenario.category,
                "timecard_id": tc.id,
                "deal_memo_id": memo.id,
                "employee_id": memo.employee_id,
                "week_ending": tc.week_ending.isoformat(),
                "agreement_version_in_force": params.agreement.version,
                "negative": not findings,
                "expected_action": action,
                "expected_rules": rules,
                "expected_citation_keys": sorted({k for f in findings for k in f.citation_keys}),
                "expected_findings": [
                    {
                        **asdict(f),
                        "citation_keys": list(f.citation_keys),
                        "day_date": f.day_date.isoformat() if f.day_date else None,
                    }
                    for f in findings
                ],
            }
        )

    positives = sum(1 for c in cases if not c["negative"])
    return {
        "manifest_version": MANIFEST_VERSION,
        "generated_by": "payroll_triage.evals.manifest (uv run ptc build-manifest)",
        "agreement": {
            "code": params.agreement.code,
            "version": params.agreement.version,
            "citation_prefix": params.agreement.citation_prefix,
            "effective_from": params.agreement.effective_from.isoformat(),
            "effective_to": params.agreement.effective_to.isoformat(),
        },
        "as_of_date": catalog.as_of_date.isoformat(),
        "seed": data.seed,
        "counts": {"cases": len(cases), "positive": positives, "negative": len(cases) - positives},
        "quality_rubrics": "added in Iteration 3 (ADR-003 tier 2)",
        "cases": cases,
    }


def _dump(doc: dict[str, Any]) -> str:
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False, width=100)


def write_manifest(doc: dict[str, Any] | None = None) -> Path:
    doc = doc or build_manifest()
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Evaluation case manifest. Generated: do not edit by hand.\n"
        "# Regenerate with `uv run ptc build-manifest` (from backend/) after changing\n"
        "# data/rule-parameters.yaml, data/scenarios.yaml or the deal memos.\n"
    )
    path.write_text(header + _dump(doc), encoding="utf-8", newline="\n")
    return path


def check_manifest(doc: dict[str, Any] | None = None) -> list[str]:
    doc = doc or build_manifest()
    path = manifest_path()
    if not path.is_file():
        return [f"manifest missing: {path}"]
    committed = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    body = "\n".join(line for line in committed.split("\n") if not line.startswith("#"))
    if body.lstrip("\n") != _dump(doc):
        return [f"manifest is stale: {path}"]
    return []


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    path = path or manifest_path()
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
