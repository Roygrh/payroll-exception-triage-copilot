"""Command line entry point: `uv run ptc <command>` from backend/."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from payroll_triage.corpus.render import check_agreement, write_agreement


def _cmd_render_agreement(_: argparse.Namespace) -> int:
    out = write_agreement()
    print(f"rendered {out}")
    return 0


def _cmd_check(_: argparse.Namespace) -> int:
    problems: list[str] = []
    problems.extend(check_agreement())
    for extra in _extra_checks():
        problems.extend(extra())
    if problems:
        for p in problems:
            print(f"STALE: {p}")
        return 1
    print("all committed outputs are current")
    return 0


def _extra_checks():
    """Staleness checks for the generated data and the eval manifest."""
    from payroll_triage.data.generator import check_generated
    from payroll_triage.evals.manifest import check_manifest

    return [check_generated, check_manifest]


def _cmd_generate_data(_: argparse.Namespace) -> int:
    from payroll_triage.data.generator import write_generated

    for path in write_generated():
        print(f"wrote {path}")
    return 0


def _cmd_build_manifest(_: argparse.Namespace) -> int:
    from payroll_triage.evals.manifest import write_manifest

    print(f"wrote {write_manifest()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ptc", description="Payroll Exception Triage Copilot tools"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "render-agreement", help="render the agreement from the template and the YAML"
    ).set_defaults(func=_cmd_render_agreement)
    sub.add_parser(
        "generate-data", help="write data/generated from data/scenarios.yaml"
    ).set_defaults(func=_cmd_generate_data)
    sub.add_parser("build-manifest", help="write evals/cases/manifest.yaml").set_defaults(
        func=_cmd_build_manifest
    )
    sub.add_parser("check", help="verify committed outputs equal regenerated outputs").set_defaults(
        func=_cmd_check
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    from jinja2 import TemplateNotFound

    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, TemplateNotFound, FileNotFoundError) as exc:
        # ParameterError, ScenarioError, DealMemoError and construction
        # mismatches all derive from ValueError.
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
