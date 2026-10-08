# ADR-006: Sources naming real organizations stay in the gitignored private folder

Status: Accepted
Date: 2026-10-07

## Context

The author's inputs (the original brief, domain research from public vendor pages, notes on the target role) name real companies, products, unions, a staffing firm and people, and contain personal data. The repository must be brand-free and must not contain personal data, yet the project needs those inputs to stay grounded (ADR-001) and the evidence trail needs to be honest about where knowledge came from.

## Decision

- Raw sources that name real organizations or people live only in a folder at the repository root that is excluded by `.gitignore` and is never referenced from any committed file other than `.gitignore`.
- In-repo evidence (`docs/evidence/sources.md`) describes each source generically: what kind of document it is, what was learned from it, and what was deliberately not carried over. No names, URLs that reveal a vendor, phone numbers, compensation figures or personal details.
- The author keeps a list of forbidden terms (brand names, product names, organization names, person names) in the same private folder and scans the repository against it before every commit. Agents may not read or cite that list in committed files; the domain consistency validator uses general knowledge instead and the author's scan is the exact check.
- Technology vendors that are part of the stack and named in accepted ADRs (LLM provider, tracing vendor, databases, frameworks, cloud provider) are not subject to this rule.

## Consequences

- Anyone cloning the repository can understand the evidence basis without seeing the private sources.
- A new private source is added by dropping it in the private folder and adding a generic entry to `sources.md`.
- If the private folder is missing on a machine, the bootstrap documents are still sufficient to continue; only re-grounding against the raw sources requires it.
