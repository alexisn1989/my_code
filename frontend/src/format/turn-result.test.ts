/**
 * Gate 4A3 UX-2 (U4): the wording and the routine rule for turn-result drivers, tested where they
 * live. Every params object below uses the engine's REAL param names (`phases.py`), so a renamed
 * param fails here rather than silently falling back to the generic label in play.
 */

import { describe, expect, it } from "vitest";

import { SECTOR_LABEL, driverSentence, isRoutineDriver } from "./format";

const LABOR = {
  effective_labor_force: 1_000_000,
  total_employment: 948_000,
  unemployed_workers: 52_000,
  unfilled_jobs: 1_200,
  unemployment_rate_bps: 520,
};

const EXTRACTION = {
  deposits_active: 4,
  deposits_depleted: 0,
  total_extraction_workers: 9_000,
  unassigned_resource_workers: 0,
  extraction_sector_real_output: 10,
  extraction_sector_potential_output: 10,
};

describe("routine driver sentences", () => {
  it.each([
    [0, "0.00%"],
    [520, "5.20%"],
    [10_000, "100.00%"],
  ])("renders unemployment_rate_bps %i as %s, never the raw integer", (bps, shown) => {
    const sentence = driverSentence(
      "labor_market_resolved",
      { ...LABOR, unemployment_rate_bps: bps },
      "fallback",
    );
    expect(sentence).toBe(`Labour market: 948,000 employed, ${shown} unemployment, 1,200 unfilled jobs.`);
  });

  it("states production, tax bases and the turn from their own params", () => {
    expect(
      driverSentence(
        "production_summary",
        {
          total_employment: 948_000,
          total_gross_output: 12_345_678,
          sectors_capacity_constrained: 3,
          sectors_labor_constrained: 2,
          sectors_exactly_balanced: 4,
          sectors_physical_resource_constrained: 0,
          sectors_inactive: 2,
        },
        "fallback",
      ),
    ).toBe("Production: 12,345,678 output; 3 sectors at capacity, 2 short of workers.");
    expect(
      driverSentence(
        "tax_bases_derived",
        { personal_income: 100_000_000, corporate_profit: 3_150_000, taxable_consumption: 70_000 },
        "fallback",
      ),
      // Gate 4A3 UX-4a: these params are Money, in MINOR units -- the original expectation here pinned
      // them rendered as counts, 100x too large. 100,000,000 minor units is 1,000,000.00 denars.
    ).toBe("Tax bases: personal income 1,000,000.00, corporate profit 31,500.00, consumption 700.00.");
    expect(driverSentence("turn_resolved", { turn: 7 }, "fallback")).toBe("Turn 7 resolved.");
  });

  it("falls back to the generic label when a param is missing", () => {
    const { unfilled_jobs: _dropped, ...partial } = LABOR;
    expect(driverSentence("labor_market_resolved", partial, "The labour market cleared.")).toBe(
      "The labour market cleared.",
    );
    expect(driverSentence("turn_resolved", {}, "The turn resolved.")).toBe("The turn resolved.");
  });
});

describe("consequential economy sentences", () => {
  it("names the sector that produced nothing", () => {
    expect(driverSentence("sector_inactive", { category: "defense_industry" }, "fallback")).toBe(
      "The Defence industry sector produced nothing this turn.",
    );
  });

  it("falls back to the generic label for an unknown sector, never the raw value", () => {
    const sentence = driverSentence("sector_inactive", { category: "space_mining" }, "A sector was inactive.");
    expect(sentence).toBe("A sector was inactive.");
  });

  it("names depleted deposits and unplaced resource workers", () => {
    expect(
      driverSentence(
        "resource_extraction_resolved",
        { ...EXTRACTION, deposits_depleted: 1, unassigned_resource_workers: 2_500 },
        "fallback",
      ),
    ).toBe("Resource extraction: 1 deposit ran dry; 2,500 resource workers had no deposit to work.");
    expect(
      driverSentence("resource_extraction_resolved", { ...EXTRACTION, deposits_depleted: 2 }, "fallback"),
    ).toBe("Resource extraction: 2 deposits ran dry.");
  });
});

describe("isRoutineDriver", () => {
  it.each(["labor_market_resolved", "production_summary", "tax_bases_derived", "turn_resolved"])(
    "folds %s away",
    (reasonId) => {
      expect(isRoutineDriver({ reason_id: reasonId, params: {} })).toBe(true);
    },
  );

  it("never folds a sector that produced nothing", () => {
    expect(isRoutineDriver({ reason_id: "sector_inactive", params: { category: "energy" } })).toBe(false);
  });

  it("folds extraction only when nothing ran dry and every worker was placed", () => {
    expect(isRoutineDriver({ reason_id: "resource_extraction_resolved", params: EXTRACTION })).toBe(true);
    expect(
      isRoutineDriver({
        reason_id: "resource_extraction_resolved",
        params: { ...EXTRACTION, deposits_depleted: 1 },
      }),
    ).toBe(false);
    expect(
      isRoutineDriver({
        reason_id: "resource_extraction_resolved",
        params: { ...EXTRACTION, unassigned_resource_workers: 1 },
      }),
    ).toBe(false);
    expect(isRoutineDriver({ reason_id: "resource_extraction_resolved", params: {} })).toBe(false);
  });

  it("keeps every other reason visible", () => {
    for (const reasonId of ["budget_blocked", "cabinet_appointed", "promise_breached", "unknown_reason"]) {
      expect(isRoutineDriver({ reason_id: reasonId, params: {} }), reasonId).toBe(false);
    }
  });
});

describe("SECTOR_LABEL", () => {
  it("has a non-empty display name for each of the eleven sectors", () => {
    expect(Object.keys(SECTOR_LABEL)).toHaveLength(11);
    for (const [key, label] of Object.entries(SECTOR_LABEL)) {
      expect(label.trim(), key).not.toBe("");
      expect(label, key).not.toContain("_");
    }
  });
});
