import type { Action, CaseStatus, FactValue, OutputStatus, RecipientRole } from "./api/types";

// Display only. Every number shown comes from the API as is (ADR-008: amounts, hours and
// minutes are computed by the rule engine); the UI adds units and labels, never arithmetic on
// domain values.

export const ACTION_LABEL: Record<Action, string> = {
  approve: "Approve",
  return: "Return",
  escalate: "Escalate",
};

export const STATUS_LABEL: Record<CaseStatus, string> = {
  detected: "Detected",
  awaiting_decision: "Awaiting decision",
  needs_human_review: "Needs human review",
  approved: "Approved",
  returned: "Returned",
  escalated: "Escalated",
};

export const OUTPUT_STATUS_LABEL: Record<OutputStatus, string> = {
  valid: "Validated",
  invalid: "Failed validation",
  not_validated: "Not validated",
  missing: "No output",
};

export const RECIPIENT_LABEL: Record<RecipientRole, string> = {
  employee: "Crew member",
  department_head: "Department head",
  payroll_specialist: "Payroll specialist",
};

export const EVENT_LABEL: Record<string, string> = {
  call: "Call",
  meal_out: "Meal out",
  meal_in: "Meal in",
  wrap: "Wrap",
};

export function usd(amount: string | null | undefined): string {
  return amount == null ? "" : `$${amount}`;
}

export function humanize(name: string): string {
  const text = name.replace(/_usd$/, "").replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** A fact value with its unit: "24 min", "5.0 hours", "$8.25", "Yes". */
export function factText(name: string, value: FactValue | undefined, unit?: string): string {
  if (value === undefined) return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (name.endsWith("_usd")) return usd(String(value));
  if (unit === "minutes") return `${value} min`;
  // Hours are tenths from the engine; show the tenth even when it is zero (6 is "6.0").
  if (unit === "hours") return `${typeof value === "number" ? value.toFixed(1) : value} hours`;
  return String(value);
}

export interface FactTile {
  label: string;
  value: string;
  facts: string[];
}

// Labelled tiles per rule: a measured fact next to the agreement limit it is compared with.
const TILE_LAYOUT: Record<string, { label: string; fact: string; limit?: [string, string] }[]> = {
  MEAL_PERIOD: [
    { label: "Meal duration", fact: "meal_minutes", limit: ["min_duration_minutes", "minimum"] },
    { label: "Call to meal out", fact: "hours_to_meal", limit: ["deadline_hours", "deadline"] },
    { label: "Meal out past the deadline", fact: "minutes_late" },
    { label: "Penalty increments", fact: "increments", limit: ["increment_minutes", "increment"] },
    { label: "Meal penalty", fact: "penalty_usd" },
    { label: "Late meal", fact: "is_late" },
    { label: "Short meal", fact: "is_short" },
  ],
};

export function factTiles(
  ruleId: string,
  facts: Record<string, FactValue>,
  units: Record<string, string> = {},
): FactTile[] {
  const used = new Set<string>();
  const tiles: FactTile[] = [];
  for (const spec of TILE_LAYOUT[ruleId] ?? []) {
    if (!(spec.fact in facts)) continue;
    let value = factText(spec.fact, facts[spec.fact], units[spec.fact]);
    const names = [spec.fact];
    if (spec.limit && spec.limit[0] in facts) {
      const [limit, word] = spec.limit;
      value += `, ${word} ${factText(limit, facts[limit], units[limit])}`;
      names.push(limit);
    }
    names.forEach((n) => used.add(n));
    tiles.push({ label: spec.label, value, facts: names });
  }
  // Facts not in the layout (other rules, new facts) still show, with their unit.
  for (const [name, raw] of Object.entries(facts)) {
    if (used.has(name)) continue;
    tiles.push({ label: humanize(name), value: factText(name, raw, units[name]), facts: [name] });
  }
  return tiles;
}

/** An audit timestamp as UTC time of day, independent of the viewer's time zone. */
export function auditTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.toISOString().slice(0, 10)} ${date.toISOString().slice(11, 19)} UTC`;
}

export function tokenTotal(input: number | null, output: number | null): number | null {
  if (input == null && output == null) return null;
  return (input ?? 0) + (output ?? 0);
}
