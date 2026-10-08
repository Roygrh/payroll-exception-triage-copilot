"""Repository paths shared by every module.

The repository root is resolved relative to this file so that commands work
from any working directory. An environment variable override exists for
containers where the source tree is mounted elsewhere.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_ROOT = "PTC_REPO_ROOT"


def repo_root() -> Path:
    override = os.environ.get(_ENV_ROOT)
    if override:
        return Path(override).resolve()
    # src/payroll_triage/paths.py -> backend/ -> repository root
    return Path(__file__).resolve().parents[3]


def data_dir() -> Path:
    return repo_root() / "data"


def generated_dir() -> Path:
    return data_dir() / "generated"


def corpus_dir() -> Path:
    return repo_root() / "corpus"


def templates_dir() -> Path:
    return corpus_dir() / "templates"


def deal_memos_dir() -> Path:
    return corpus_dir() / "deal-memos"


def evals_dir() -> Path:
    return repo_root() / "evals"


def rule_parameters_path() -> Path:
    return data_dir() / "rule-parameters.yaml"


def rule_parameters_schema_path() -> Path:
    return data_dir() / "rule-parameters.schema.json"


def scenarios_path() -> Path:
    return data_dir() / "scenarios.yaml"


def manifest_path() -> Path:
    return evals_dir() / "cases" / "manifest.yaml"
