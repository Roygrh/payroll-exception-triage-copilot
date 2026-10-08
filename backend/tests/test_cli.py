"""Smoke tests for the ptc command line."""

from __future__ import annotations

import payroll_triage.cli as cli
from payroll_triage.cli import main


def test_check_passes_on_committed_outputs(capsys):
    assert main(["check"]) == 0
    assert "current" in capsys.readouterr().out


def test_errors_are_reported_not_raised(monkeypatch, capsys):
    def boom(_):
        raise ValueError("synthetic failure")

    monkeypatch.setattr(cli, "_cmd_check", boom)
    assert main(["check"]) == 2
    assert "synthetic failure" in capsys.readouterr().err
