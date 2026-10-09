# Domain model

Everything in this document is fictitious except where marked. Numeric values are authoritative only in `data/rule-parameters.yaml` (ADR-007); this document records the agreed design values and must be kept equal to the YAML.

## 1. The agreement

| Attribute | Value |
| --- | --- |
| Name | Crew Guild Master Agreement |
| Code | CGMA |
| Version | 2026.1 |
| Effective | 2026-01-01 to 2026-12-31 |
| Parties (fictitious) | The Crew Guild and the Alliance of Independent Production Employers (no local number; OD-08 closed in Iteration 2) |
| Citation key format | `CGMA-2026.1-<section>`, for example `CGMA-2026.1-8.2`; schedules cite as `CGMA-2026.1-SCH-A` and `CGMA-2026.1-SCH-B` |

### Outline (15 to 20 pages when rendered)

| Article | Title | Notes |
| --- | --- | --- |
| 1 | Definitions | Call, wrap, meal period, rest period, workday, workweek, scale, deal memo, hire state, work state |
| 2 | Scope and jurisdiction | Applies to covered productions; where hire state and work state differ, the provision more favorable to the employee applies (no Phase 1 rule depends on this) |
| 3 | Offers and deal memos | 3.2 a deal memo may improve on scale and conditions; it may never reduce them (basis for SCALE_RATE, cited with 5.1 and Schedule A) |
| 4 | Workweek and payroll period | Payroll week Sunday to Saturday; week ending is Saturday; producer week starts Sunday |
| 5 | Wage scales | 5.1 minimum hourly scale by occupation code per Schedule A |
| 6 | Hours and overtime | 6.1 daily overtime after 8.0 h at 1.5x; 6.2 extended day over 12.0 h at 2.0x; 6.3 weekly overtime after 40.0 h at 1.5x |
| 7 | Time reporting | 7.4 required entries for a work day: call, meal out, meal in, wrap; entries must be chronological |
| 8 | Meal periods | 8.2 first meal within 6.0 h of call and at least 30 min long; 8.3 meal penalties per Schedule B |
| 9 | Rest periods | 9.1 minimum 10.0 h between wrap and next call; 9.2 invasion pay at 2.0x for invaded hours |
| 10 | Allowances | Kit rental and similar; informational in Phase 1 |
| 11 | Timecard corrections and approvals | Return for correction, resubmission, approver levels |
| 12 | Holidays | Informational in Phase 1 |
| 13 | Grievances | Escalation route; informational |
| 14 | Eligibility documentation | 14.2 employment eligibility verification must be completed within 3 business days of the start date |
| Schedule A | Occupation codes and hourly scale | Five codes (section 4) |
| Schedule B | Meal penalty table | 30-minute increments: 8.25, 11.00, 13.75 USD (third and later increments at the last value) |

## 2. Rule parameters (design values)

All fictitious except the eligibility deadline.

| Parameter | Value | Used by |
| --- | --- | --- |
| `meal.deadline_hours` | 6.0 | MEAL_PERIOD |
| `meal.min_duration_minutes` | 30 | MEAL_PERIOD |
| `meal.penalty_increment_minutes` | 30 | MEAL_PERIOD (premium calculation) |
| `meal.penalty_schedule_usd` | [8.25, 11.00, 13.75] | MEAL_PERIOD; third and later increments use the last value |
| `extended_day.threshold_hours` | 12.0 | EXTENDED_DAY |
| `extended_day.multiplier` | 2.0 | EXTENDED_DAY |
| `rest.min_hours` | 10.0 | REST_PERIOD |
| `rest.invasion_multiplier` | 2.0 | REST_PERIOD |
| `eligibility.deadline_business_days` | 3 | ELIGIBILITY_DOC (mirrors the public government rule; verified 2026-10-07, see `docs/evidence/sources.md`) |
| `overtime.daily_after_hours` | 8.0 | calculation only (ADR-010) |
| `overtime.daily_multiplier` | 1.5 | calculation only |
| `overtime.weekly_after_hours` | 40.0 | calculation only |
| `overtime.weekly_multiplier` | 1.5 | calculation only |
| `plausibility.max_day_hours` | 20.0 | MEAL_PERIOD, EXTENDED_DAY and REST_PERIOD plausibility (approve versus return); agreement 7.7 |
| `payroll.time_unit_hours` | 0.1 | timecard recording unit (tenths of an hour); agreement 1.3 |
| `queue.urgency_business_days` | 1 | queue priority: the payroll run within this many business days is urgent |
| `queue.urgency_weight` | 3 | queue priority weight of urgency |
| `queue.severity_weight` | 2 | queue priority weight of the severity rank |
| `queue.amount_tier_thresholds_usd` | [25.00, 100.00] | queue priority amount tiers (0 below the first, 1 below the second, 2 otherwise) |
| `queue.max_days_late_points` | 5 | queue priority cap on business days since the week ending |

## 3. Exception rules

| Rule id | Section | Detects | Facts computed by code | Policy action |
| --- | --- | --- | --- | --- |
| MEAL_PERIOD | 8.2 (penalty amounts from 8.3 and Schedule B) | First meal out later than 6.0 h after call; or meal duration under 30 min | hours to meal, minutes late, increments, penalty amount; meal duration | Late meal with complete, plausible data: approve (code adds the premium line). Meal under 30 min: return (implausible or mis-punched meal; employee or department head confirms) |
| EXTENDED_DAY | 6.2 | Hours worked in a day over 12.0 | hours worked, hours over threshold, premium at 2.0x | approve (code adds the premium line) |
| REST_PERIOD | 9.1 (pay from 9.2) | Under 10.0 h between wrap and the next day's call | rest hours, invaded hours, invasion pay at 2.0x | approve (code adds the premium line) |
| TIME_ENTRY_COMPLETENESS | 7.4 | Missing call, meal out, meal in or wrap on a work day; wrap before call; meal in before meal out | which entries are missing or out of order | return |
| SCALE_RATE | 5.1 and Schedule A (with 3.2) | Deal memo hourly rate below the scale for the occupation code | scale, deal rate, shortfall per hour | escalate (source conflict: the system shows both sources, never resolves silently) |
| ELIGIBILITY_DOC | 14.2 | Employment eligibility verification not completed within 3 business days of the start date | deadline date, days overdue | escalate (compliance block) |

### Severity and combination (ADR-009)

- Severity order: escalate > return > approve.
- A timecard with several findings takes the most severe policy action; the explanation covers all findings.
- Normal overtime (daily over 8.0 h, weekly over 40.0 h) is calculated and shown in the pay summary but never creates a finding (ADR-010).

### Derived quantities

- Times are decimal hours from midnight of the shift date, recorded in tenths of an hour (6-minute units, `payroll.time_unit_hours` in the YAML); a value above 24.0 means the next calendar day. Scenario values are therefore multiples of 0.1 h.
- Meal duration = meal in minus meal out (hours, converted to minutes for the 30-minute test).
- Hours to first meal = meal out minus call.
- Hours worked = (wrap minus call) minus meal duration when the meal lasted at least 30 minutes; a meal shorter than 30 minutes is not deducted.
- Rest hours = (next day's call plus 24.0) minus wrap.
- Meal penalty increments = ceiling((meal out minus call minus 6.0) hours times 60 divided by 30); amount = sum of the schedule values, the last value repeating.
- Premium lines (extended day, rest invasion) are the full pay for the affected hours at the multiplied rate (hours x hourly rate x multiplier); they replace, and are not added to, the base pay for those hours (agreement 6.2 and 6.5). The pay summary built in Iteration 2 must honor this so the manifest facts `premium_usd` and `invasion_pay_usd` keep their meaning. Meal penalties are flat amounts added on top (agreement 8.3).
- Plausibility (for approve versus return, applied to MEAL_PERIOD, EXTENDED_DAY and REST_PERIOD): a premium finding is plausible when all four entries exist, are chronological, the meal lasted at least 30 minutes and the elapsed day is not above 20.0 hours (`plausibility.max_day_hours`); otherwise the day is returned.

### Queue priority (code-owned business rule, implemented in Iteration 2 with its weights in the YAML `queue` block; OD-01 confirmation pending)

Priority score = urgency_weight x payroll-run urgency (1 if the run is within `urgency_business_days` of the queue date, else 0) + severity_weight x severity rank (escalate 3, return 2, approve 1) + amount tier (0 below the first threshold, 1 below the second, 2 otherwise) + min(business days since the week ending, max_days_late_points). Higher is worked first; ties break by week ending (older first). Implementation: `backend/src/payroll_triage/engine/priority.py`.

## 4. Schedule A (fictitious hourly scale)

| Code | Occupation | Scale (USD/h) |
| --- | --- | --- |
| 4110 | CAMERA OPERATOR | 58.40 |
| 4125 | CAMERA ASSISTANT | 44.10 |
| 5210 | PRODUCTION COORDINATOR | 39.75 |
| 6305 | PROPERTY ASSISTANT | 36.20 |
| 7020 | SET DISPATCHER | 33.90 |

## 5. Production and crew (fictitious)

| Attribute | Value |
| --- | --- |
| Production | "Northlight Harbor", season 2, episodic drama |
| Employer of record | Harborline Productions LLC (fictitious) |
| Guild | Crew Guild (fictitious) |
| Demo week | Week ending 2026-03-14 (producer week 2026-03-08) |
| Payroll run | Tuesday 2026-03-17 (for queue urgency) |
| Departments | Camera, Production, Property, Transportation |

### Deal memos

Fields: id, employee, occupation code, guild, hourly rate, allowances, season, department, hire state, work state, start date, eligibility verification completed on.

| Id | Employee | Code | Rate | Versus scale | Allowances | Department | Hire / work state | Start date | Eligibility completed | Scenario role |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DM-01 | Avery Lindqvist | 4110 | 62.00 | above | none | Camera | same | 2026-01-12 | 2026-01-13 | late meal (approve) |
| DM-02 | Jordan Okafor | 4125 | 44.10 | at scale | kit rental 75.00/week | Camera | same | 2026-01-12 | 2026-01-14 | short meal (return) |
| DM-03 | Priya Castellanos | 5210 | 42.00 | above | none | Production | same | 2026-01-05 | 2026-01-06 | extended day (approve) |
| DM-04 | Marcus Thibodeaux | 6305 | 34.00 | BELOW (scale 36.20) | none | Property | different | 2026-02-23 | 2026-02-24 | rate below scale (escalate) |
| DM-05 | Rin Takahashi-Moore | 7020 | 33.90 | at scale | none | Transportation | same | 2026-03-02 | not completed | eligibility overdue (escalate) |
| DM-06 | Dana Whitcombe | 4110 | 58.40 | at scale | none | Camera | same | 2026-01-12 | 2026-01-13 | rest invasion (approve) |

Names are invented for this project and appear in no source material. Each deal memo is one crew member on the production. DM-05 starts on 2026-03-02 (a Monday) so that two payroll weeks exist for it; its verification deadline is 2026-03-05 and it is 7 business days overdue on the demo date 2026-03-16.

**Filler crew (decided in Iteration 1):** the generator adds four filler crew members (employees EMP-2001 to EMP-2004 with generated at-scale deal memos DM-F01 to DM-F04) and clean weeks for the demo week ending, so the ingested batch looks like a real week. They are listed in the scenario catalog as SC-F01 to SC-F04, category clean, and never produce a case.

## 6. Timecard model

| Field | Notes |
| --- | --- |
| timecard id, employee, deal memo id | |
| week ending | Saturday, ISO date |
| producer week | Sunday that starts the week |
| approval status | one of: Draft, Incomplete, Rejected, Ready for employee, Ready for dept head, Ready for approver 1, Ready for approver 2, Ready for approver 3, Submitted, Processing, Paid |
| days (up to 7) | each with: date, day type, work location, call time, meal 1 out, meal 1 in, wrap |
| day type | `1-Work`, `2-Travel`, `3-Holiday`, `4-Idle` (only `1-Work` is evaluated by the rules) |
| work location | `S-Stage`, `L-Local location`, `D-Distant location` |

The exception queue consumes timecards in status `Ready for approver 1` (the approver's personal queue). A return moves the timecard to `Rejected` with a message; an approve adds the premium lines and moves it to `Ready for approver 2`; an escalate keeps the status and opens an escalation record for a specialist.

## 7. Scenario catalog (18)

| Scenario | Deal memo | Description | Expected rule(s) | Section | Expected action |
| --- | --- | --- | --- | --- | --- |
| SC-01 | DM-01 | Clean week, five standard days | none | none | none (no exception) |
| SC-02 | DM-06 | Clean week with daily overtime (10 h days) | none (overtime calculated only) | none | none |
| SC-03 | DM-01 | First meal at 6.5 h from call, complete punches | MEAL_PERIOD | 8.2 | approve |
| SC-04 | DM-01 | First meal at 7.2 h from call on two days | MEAL_PERIOD | 8.2 | approve |
| SC-05 | DM-02 | Meal of 24 minutes (0.4 h) | MEAL_PERIOD | 8.2 | return |
| SC-06 | DM-02 | Missing wrap on one day | TIME_ENTRY_COMPLETENESS | 7.4 | return |
| SC-07 | DM-03 | Missing meal in on one day | TIME_ENTRY_COMPLETENESS | 7.4 | return |
| SC-08 | DM-06 | Wrap before call (punch error) | TIME_ENTRY_COMPLETENESS | 7.4 | return |
| SC-09 | DM-03 | 13.5 h workday | EXTENDED_DAY | 6.2 | approve |
| SC-10 | DM-03 | 12.5 h workday with a compliant meal | EXTENDED_DAY | 6.2 | approve |
| SC-11 | DM-06 | 8.5 h rest between wrap and next call | REST_PERIOD | 9.1 | approve |
| SC-12 | DM-06 | 9.5 h rest after a late wrap past midnight | REST_PERIOD | 9.1 | approve |
| SC-13 | DM-04 | Clean punches, deal rate below scale | SCALE_RATE | 5.1 | escalate |
| SC-14 | DM-04 | Below scale plus late meal (6.8 h) | SCALE_RATE, MEAL_PERIOD | 5.1, 8.2 | escalate (most severe) |
| SC-15 | DM-05 | Clean punches, eligibility overdue | ELIGIBILITY_DOC | 14.2 | escalate |
| SC-16 | DM-05 | Eligibility overdue plus 12.5 h day | ELIGIBILITY_DOC, EXTENDED_DAY | 14.2, 6.2 | escalate (most severe) |
| SC-17 | DM-01 | Late meal (approve) plus missing meal out on another day (return) | MEAL_PERIOD, TIME_ENTRY_COMPLETENESS | 8.2, 7.4 | return (most severe) |
| SC-18 | DM-06 | Rest invasion (approve) plus short meal (return) | REST_PERIOD, MEAL_PERIOD | 9.1, 8.2 | return (most severe) |

Counts: clean week 2; late meal complete 2; meal under 30 min 1; missing punch 3; workday over 12 h 2; rest under 10 h 2; rate below scale 2; eligibility overdue 2; multiple findings 2.

SC-13 and SC-14 are the "source conflict" cases of demo step 4: the deal memo and the agreement disagree and both are shown.

**Week assignment (decided in Iteration 1).** An employee has at most one timecard per week ending, so the scenarios of one deal memo are spread over consecutive week endings counting back from the demo week 2026-03-14, never earlier than the deal memo's start date. The showcase scenario of each employee (SC-03, SC-05, SC-09, SC-11, SC-13, SC-15) and the filler crew are on the demo week; the others are on 2026-03-07, 2026-02-28, 2026-02-21 and 2026-02-14. All of them sit in `Ready for approver 1` on the demo date, which gives the queue a realistic spread of days late. The exact assignment is in `data/scenarios.yaml`.

## 8. Evaluation case manifest (Iteration 1 artifact)

One eval case per scenario with a finding (SC-03 to SC-18, 16 cases) plus the two clean weeks as negative cases (no exception may be raised). Each case records: scenario id, timecard id, expected rule ids, expected citation keys (`CGMA-2026.1-8.2` and so on), expected policy action, and the structured facts the engine must produce (for deterministic comparison). Quality rubrics (explanation faithfulness, return-message completeness) are added in Iteration 3.

## 9. Glossary

- **Call**: start of the workday. **Wrap**: end of the workday.
- **Meal out / meal in**: start and end of the first meal period.
- **Premium line**: an added pay line produced by code for a meal penalty, extended-day hours or rest invasion.
- **Return**: send the timecard back for correction with a message.
- **Escalate**: route to a payroll specialist without changing the timecard.
- **Needs human review**: the LLM output could not be validated; the approver sees facts only.
