import { describe, expect, it } from "vitest";
import { auditTime, factText, factTiles } from "./format";
import { href, parseHash } from "./router";
import { caseDetail } from "./test/fixtures";

describe("fact tiles", () => {
  const detail = caseDetail();
  const finding = detail.case.findings[0]!;
  const tiles = factTiles(finding.rule_id, finding.facts, detail.fact_units!.MEAL_PERIOD);
  const byLabel = Object.fromEntries(tiles.map((t) => [t.label, t.value]));

  it("labels facts with their units and the agreement limit", () => {
    expect(byLabel["Meal duration"]).toBe("24 min, minimum 30 min");
    expect(byLabel["Call to meal out"]).toBe("5.0 hours, deadline 6.0 hours");
    expect(byLabel["Meal penalty"]).toBe("$0.00");
    expect(byLabel["Short meal"]).toBe("Yes");
  });

  it("shows every fact exactly once", () => {
    const shown = tiles.flatMap((t) => t.facts).sort();
    expect(shown).toEqual(Object.keys(finding.facts).sort());
  });

  it("shows the values as given, never recomputed", () => {
    expect(factText("meal_minutes", 24, "minutes")).toBe("24 min");
    expect(factText("hours_late", 0.5, "hours")).toBe("0.5 hours");
    expect(factText("increments", 1)).toBe("1");
  });

  it("falls back to every fact for a rule without a layout", () => {
    const other = factTiles("EXTENDED_DAY", { hours_over: 1.5, premium_usd: "12.00" }, { hours_over: "hours" });
    expect(other.map((t) => t.value)).toEqual(["1.5 hours", "$12.00"]);
  });
});

describe("router", () => {
  it("round-trips every route", () => {
    for (const route of [
      { name: "queue" as const },
      { name: "case" as const, id: "CASE-EMP-1002-20260314" },
      { name: "message" as const, id: "CASE-EMP-1002-20260314" },
      { name: "audit" as const, id: "CASE-EMP-1002-20260314" },
    ]) {
      expect(parseHash(href(route))).toEqual(route);
    }
    expect(parseHash("")).toEqual({ name: "queue" });
  });
});

it("prints audit times in UTC", () => {
  expect(auditTime("2026-10-22T04:36:03.291513+00:00")).toBe("2026-10-22 04:36:03 UTC");
});
