"""Citation validation (code, constraint 7 and ADR-003 tier 1).

A citation key is valid when it resolves to a corpus chunk and, for agreement
keys, the chunk's version is the version in force for the case's week ending;
a deal memo key must be the memo of the case. The validator never rewrites or
drops a citation silently: the result lists every key with its status and the
caller routes any failure to "needs human review".
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from payroll_triage.retrieval.chunker import Chunk, is_deal_memo_key

Lookup = Callable[[str], Chunk | None]


@dataclass(frozen=True)
class CitationCheck:
    key: str
    status: str  # "valid" | "unknown_key" | "wrong_version" | "wrong_deal_memo"
    detail: str = ""


@dataclass(frozen=True)
class CitationValidation:
    valid: bool
    checks: tuple[CitationCheck, ...] = field(default_factory=tuple)
    required_missing: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "checks": [c.__dict__ for c in self.checks],
            "required_missing": list(self.required_missing),
        }


def validate_citations(
    keys: Iterable[str],
    lookup: Lookup,
    *,
    version_in_force: str,
    deal_memo_id: str | None,
    required_keys: Iterable[str] = (),
) -> CitationValidation:
    checks: list[CitationCheck] = []
    seen: list[str] = []
    for key in keys:
        if key in seen:
            continue
        seen.append(key)
        chunk = lookup(key)
        if chunk is None:
            checks.append(CitationCheck(key, "unknown_key", "no passage with this citation key"))
        elif is_deal_memo_key(key):
            if deal_memo_id is not None and key != deal_memo_id:
                checks.append(
                    CitationCheck(key, "wrong_deal_memo", f"the case's deal memo is {deal_memo_id}")
                )
            else:
                checks.append(CitationCheck(key, "valid"))
        elif chunk.version != version_in_force:
            checks.append(
                CitationCheck(
                    key,
                    "wrong_version",
                    f"passage version {chunk.version}, version in force {version_in_force}",
                )
            )
        else:
            checks.append(CitationCheck(key, "valid"))
    missing = tuple(k for k in required_keys if k not in seen)
    valid = bool(seen) and all(c.status == "valid" for c in checks) and not missing
    return CitationValidation(valid=valid, checks=tuple(checks), required_missing=missing)
