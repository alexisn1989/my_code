/**
 * Gate 4A3 UX-4a (U9): money is shown as grouped denars, never as a raw count of minor units.
 */

import { describe, expect, it } from "vitest";

import { MINOR_UNITS_PER_DENAR, driverSentence, formatAmount, formatMoney } from "./format";

describe("formatMoney", () => {
  it.each([
    [10_000_000_000, "100,000,000.00"],
    [315_000_000, "3,150,000.00"],
    [1_205, "12.05"],
    [-1_205, "-12.05"],
    [7, "0.07"],
    [0, "0.00"],
  ])("renders %i minor units as %s", (minor, shown) => {
    expect(formatMoney(minor)).toBe(shown);
  });

  it("uses 100 minor units to the denar, as the engine does", () => {
    expect(MINOR_UNITS_PER_DENAR).toBe(100);
  });

  it("differs from formatAmount by exactly the minor-unit factor -- the UX-2 defect, stated", () => {
    expect(formatAmount(10_000_000_000)).toBe("10,000,000,000");
    expect(formatMoney(10_000_000_000)).toBe("100,000,000.00");
  });
});

describe("the tax-bases sentence states denars", () => {
  it("renders a real-sized turn's bases as the CLI's format_money amounts, grouped", () => {
    // The CLI renders these three params with `format_money`: 2,150,000,000 minor units is
    // "21500000.00" there, and "21,500,000.00" here.
    expect(
      driverSentence(
        "tax_bases_derived",
        { personal_income: 2_150_000_000, corporate_profit: 640_000_000, taxable_consumption: 1_725_000_050 },
        "fallback",
      ),
    ).toBe(
      "Tax bases: personal income 21,500,000.00, corporate profit 6,400,000.00, consumption 17,250,000.50.",
    );
  });
});
