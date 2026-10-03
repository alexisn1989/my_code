/**
 * Gate 4A3 UX-3 (U10): the Dashboard's national tint, tested where its arithmetic lives.
 */

import { describe, expect, it } from "vitest";

import {
  TINT_MIX_MAX_PERCENT,
  TINT_MIX_MIN_PERCENT,
  tintAccessibleName,
  tintCaption,
  tintFill,
  tintMixPercent,
} from "./format";

describe("tintMixPercent", () => {
  it("runs from the floor at 0 bps to the ceiling at 10,000 bps", () => {
    expect(tintMixPercent(0)).toBe(TINT_MIX_MIN_PERCENT);
    expect(tintMixPercent(10_000)).toBe(TINT_MIX_MAX_PERCENT);
    expect(tintMixPercent(5_000)).toBe(37.5);
    expect([TINT_MIX_MIN_PERCENT, TINT_MIX_MAX_PERCENT]).toEqual([15, 60]);
  });

  it("is clamped outside the ratio scale", () => {
    expect(tintMixPercent(-2_500)).toBe(TINT_MIX_MIN_PERCENT);
    expect(tintMixPercent(12_000)).toBe(TINT_MIX_MAX_PERCENT);
  });

  it("is strictly increasing across the scale, so a different value draws a different tint", () => {
    let previous = -Infinity;
    for (let bps = 0; bps <= 10_000; bps += 100) {
      const value = tintMixPercent(bps);
      expect(value, `at ${bps} bps`).toBeGreaterThan(previous);
      expect(value).toBeGreaterThanOrEqual(TINT_MIX_MIN_PERCENT);
      expect(value).toBeLessThanOrEqual(TINT_MIX_MAX_PERCENT);
      previous = value;
    }
  });

  it("builds an opaque mix of two palette tokens", () => {
    expect(tintFill(6_000)).toBe(
      "color-mix(in oklab, var(--color-gold-600) 42%, var(--color-navy-950))",
    );
  });
});

describe("tint copy", () => {
  it("states what the colour shows, in the player's terms", () => {
    expect(tintCaption("Legitimacy")).toBe(
      "The colour shows national legitimacy: the stronger it is, the deeper the tint.",
    );
  });

  it("names only what is drawn", () => {
    const name = tintAccessibleName("Kingdom of Valdrun", "Legitimacy", "60.00%");
    expect(name).toBe("Kingdom of Valdrun: national tint by legitimacy, 60.00%.");
    for (const word of ["outline", "placeholder", "province", "mechanics"]) {
      expect(name.toLowerCase()).not.toContain(word);
      expect(tintCaption("Legitimacy").toLowerCase()).not.toContain(word);
    }
  });
});
