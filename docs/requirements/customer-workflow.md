# Customer workflow: the approver's week

A generic description of how an approver or production accountant works inside an entertainment payroll platform, reconstructed from public product documentation of vendors in this category (described generically per ADR-006). It explains where the copilot plugs in. Nothing here names a vendor.

## 1. Actors

| Actor | Role in the workflow |
| --- | --- |
| Crew member (employee) | Records daily workday events on a timecard; signs offers; completes eligibility paperwork |
| Department head | First reviewer of the department's timecards |
| Approver 1, 2, 3 | Configurable approval levels (production accountant, production manager, studio finance) |
| Payroll coordinator / specialist | Resolves escalations: rate conflicts, compliance blocks, grievances |
| Payroll processor | The payroll company's processing team; receives submitted timecards, issues invoices, pays |

## 2. Onboarding (before the first workday)

1. Production creates the crew member record (individually or by bulk upload). A person may exist without an account and without offers.
2. Production creates an offer (start packet) with structured terms: season, union, occupation code and title, work schedule, department, hire state and city, work state and primary work city, start date, rate, allowances. Offers can be loaded from templates and reused for rehire.
3. Internal approvals of the offer.
4. The offer is sent; the crew member reviews and signs from any device.
5. Eligibility documentation review (employment eligibility verification form). Status is tracked per offer and overdue items are shown with a day counter.
6. Onboarding complete; the deal memo becomes the per-person source of truth for pay rules.

Role-based permissions restrict who can see rates and allowances.

## 3. Time capture (each workday)

A timecard covers one payroll week per employee and lists per day: day type (work, travel, holiday, idle), work location, call time, meal 1 out, meal 1 in, wrap. The platform derives hours, overtime, penalties and gross pay from these events using the union agreement and the deal memo, and codes the result to accounts (automatic coding is available).

The week is viewed from two perspectives, the producer's week and the employee's week; in the normal case they coincide.

## 4. Approval chain (statuses)

```
Draft -> Ready for employee -> Ready for dept head -> Ready for approver 1 -> Ready for approver 2 -> Ready for approver 3 -> Submitted -> Processing -> Paid
   \-> Incomplete                         \-> Rejected (returned for correction, re-enters at Draft)
```

- Each approver has a personal queue ("ready for me") plus filters by week ending, department, employee, union, account and batch.
- Bulk edit and bulk approval exist for the easy cases.
- A rejected timecard carries a message explaining what to fix and goes back to the employee or department head.

## 5. Invoicing and payment (after submission)

Submitted timecards are grouped into invoices with their own statuses: Processing, Review, Edits, Revisions, Resubmitted, Hold, Future Release, Invoice Approved, Paid. Invoices reference the number of timecards they contain and the accounting folder they post to.

## 6. Where the pain is (hypothesis, ADR-001)

Calculation is automated. The time goes into the exception queue: timecards that are incomplete, rejected, trip an agreement rule, conflict with the deal memo, or sit behind an overdue compliance item. For each one the approver has to:

1. Find the applicable rule in the agreement and the person's deal memo.
2. Work out what happened from the events (how late was the meal, how long was the rest).
3. Decide: approve with the premium, return for correction, or escalate.
4. Write a message to the employee or department head.
5. Do it before the payroll cut-off, in priority order.

Volumes and minutes per exception are unknown and must be measured in discovery.

## 7. Where the copilot plugs in

| Approver step | Copilot contribution | Who decides |
| --- | --- | --- |
| Find the rule | Retrieval over the agreement and deal memo; explanation with clickable citations (LLM) | n/a |
| Work out what happened | Rule engine facts: hours, minutes late, increments, amounts (code) | n/a |
| Decide | Policy action from code; LLM proposal with justification; both shown | Human |
| Write the message | Draft return message (LLM), edited by the human | Human |
| Prioritize | Queue ordered by amount, days late and payroll-run proximity (code) | n/a |
| Record | Append-only audit of suggestions, decisions and actions (code) | n/a |

The copilot reads timecards in `Ready for approver 1`, pauses at the human checkpoint, and executes only the human's decision under the human's identity.

## 8. Demo persona

"Sam Verhoeven" (fictitious), production accountant on "Northlight Harbor", approver 1 for the Camera, Production, Property and Transportation departments, working the queue on Monday 2026-03-16 for week ending 2026-03-14, one business day before the payroll run.
