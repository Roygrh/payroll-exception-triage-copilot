from payroll_triage import __version__
from payroll_triage.paths import repo_root


def test_package_imports() -> None:
    assert __version__


def test_repo_root_has_docs() -> None:
    assert (repo_root() / "docs").is_dir()
