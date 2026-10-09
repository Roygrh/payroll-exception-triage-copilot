"""Command line entry point: `uv run ptc <command>` from backend/."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from payroll_triage.corpus.render import check_agreement, write_agreement
from payroll_triage.llm.v1.interface import LLMError


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


def _cmd_migrate(_: argparse.Namespace) -> int:
    from payroll_triage.config import get_settings
    from payroll_triage.db.migrate import migrate

    settings = get_settings()
    applied = migrate(settings.database_url)
    print(f"applied migrations: {applied or 'none (up to date)'}; checkpoint tables ready")
    return 0


def _cmd_seed(args: argparse.Namespace) -> int:
    from payroll_triage.config import get_settings
    from payroll_triage.db.connection import app_pool
    from payroll_triage.db.seed import seed

    pool = app_pool(get_settings().database_url)
    try:
        counts = seed(pool, reset=bool(args.reset))
    finally:
        pool.close()
    print(f"seeded {counts['deal_memos']} deal memos and {counts['timecards']} timecards")
    return 0


def _cmd_ingest_corpus(_: argparse.Namespace) -> int:
    from payroll_triage.config import get_settings
    from payroll_triage.db.connection import app_pool
    from payroll_triage.db.seed import all_deal_memos
    from payroll_triage.params import get_parameters
    from payroll_triage.retrieval.embeddings import get_embedder
    from payroll_triage.retrieval.index import ingest_corpus

    pool = app_pool(get_settings().database_url)
    try:
        embedder = get_embedder()
        count = ingest_corpus(pool, get_parameters(), all_deal_memos(), embedder)
    finally:
        pool.close()
    print(f"ingested {count} chunks with {embedder.model_name} ({embedder.dim} dimensions)")
    return 0


def _cmd_smoke_llm(_: argparse.Namespace) -> int:
    """One minimal structured call through the configured adapter; prints rate limit headers."""
    from payroll_triage.config import get_settings
    from payroll_triage.llm.v1 import LLMRequest, Message, build_adapter

    settings = get_settings()
    print(f"settings: {settings.redacted()}")
    adapter = build_adapter(settings)
    request = LLMRequest(
        system="Return JSON only.",
        messages=(Message("user", 'Return the object {"ok": true}.'),),
        response_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        schema_name="smoke",
        max_output_tokens=64,
    )
    response = adapter.complete(request)
    print(f"response: {response.parsed} summary: {response.summary()}")
    print(f"rate limit headers: {response.rate_limit}")
    return 0 if response.parsed == {"ok": True} else 1


def _cmd_showcase(args: argparse.Namespace) -> int:
    from payroll_triage.data.scenarios import load_catalog
    from payroll_triage.runtime import build_runtime
    from payroll_triage.showcase import run_showcase

    actor = args.actor or load_catalog().demo_approver
    runtime = build_runtime()
    try:
        run_showcase(runtime.service, args.scenario, actor, args.decision, args.message)
    finally:
        runtime.close()
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("payroll_triage.api.app:app", host=args.host, port=args.port, reload=False)
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
    sub.add_parser(
        "migrate", help="apply SQL migrations and create checkpoint tables"
    ).set_defaults(func=_cmd_migrate)
    seed = sub.add_parser("seed", help="load generated timecards and deal memos into the database")
    seed.add_argument(
        "--reset",
        action="store_true",
        help="demo reset: erase cases, suggestions, decisions, the audit log and checkpoints",
    )
    seed.set_defaults(func=_cmd_seed)
    sub.add_parser(
        "ingest-corpus", help="chunk, embed and index the agreement and deal memos"
    ).set_defaults(func=_cmd_ingest_corpus)
    sub.add_parser(
        "smoke-llm", help="one minimal real call through the configured adapter"
    ).set_defaults(func=_cmd_smoke_llm)
    show = sub.add_parser("showcase", help="run one scenario end to end with the real LLM")
    show.add_argument("--scenario", default="SC-03")
    show.add_argument("--actor", default=None, help="human identity (default: demo_approver)")
    show.add_argument(
        "--decision",
        choices=["approve", "return", "escalate"],
        required=True,
        help="the human's decision at the checkpoint (never defaulted by code)",
    )
    show.add_argument(
        "--message",
        default=None,
        help="message to send on a return (default: the validated draft verbatim)",
    )
    show.set_defaults(func=_cmd_showcase)
    serve = sub.add_parser("serve", help="run the API with uvicorn")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_cmd_serve)
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
    except RuntimeError as exc:
        # ConfigError (missing key, unknown provider) and service errors.
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except LLMError as exc:
        # A provider failure is reported, never worked around (constraint 7).
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
