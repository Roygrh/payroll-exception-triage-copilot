# ADR-010: Normal overtime is calculated, never an exception

Status: Accepted
Date: 2026-10-07

## Context

The brief lists daily and weekly overtime among the rules the engine detects. In practice, overtime beyond 8 hours a day or 40 hours a week is routine on productions; it is paid automatically and nobody investigates it. Treating it as an exception would flood the queue with cases that need no decision and would make the demo less credible.

## Decision

- Daily overtime (over 8.0 hours at 1.5x) and weekly overtime (over 40.0 hours at 1.5x) are calculated by the engine and shown in the pay summary, but never create a finding or a case.
- Only a workday over 12.0 hours raises a finding, EXTENDED_DAY (section 6.2, 2.0x for hours over the threshold), with policy action approve when the data is complete and plausible.
- Scenario SC-02 (clean week with 10-hour days) is a negative case: the gate verifies that no case is created.

## Consequences

- The rule set has six rules instead of the brief's "overtime daily and weekly" entries; the parameters for normal overtime remain in the YAML because the pay summary uses them.
- The queue contains only items that need a human decision, which matches the product thesis.
- If a future customer wants an "excessive overtime" rule (for example weekly over 60 hours), it is added as a new rule with an ADR.
