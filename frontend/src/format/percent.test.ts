/**
 * Gate 4A3 UX-4g: `formatBpsPercent` keeps the sign of a negative value under one percent. A
 * truncated quotient turned -50 bps into "-0", which printed as "0.50%". The table is the backend's
 * own (`backend/tests/test_api_projections.py`, `format_bps_percent`), so the two cannot drift apart.
 */

import { describe, expect, it } from "vitest";

import { formatBpsPercent } from "./format";

describe("formatBpsPercent", () => {
  it.each([
    [-1, "-0.01%"],
    [-50, "-0.50%"],
    [-99, "-0.99%"],
    [-100, "-1.00%"],
    [-150, "-1.50%"],
    [-8_000, "-80.00%"],
    [-10_000, "-100.00%"],
    [0, "0.00%"],
    [50, "0.50%"],
    [4_822, "48.22%"],
    [10_000, "100.00%"],
  ])("%i bps -> %s", (bps, shown) => {
    expect(formatBpsPercent(bps)).toBe(shown);
  });

  it("never prints a negative value without its sign", () => {
    for (let bps = -10_000; bps < 0; bps += 1) {
      expect(formatBpsPercent(bps).startsWith("-")).toBe(true);
    }
  });
});
