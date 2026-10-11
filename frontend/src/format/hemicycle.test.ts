/**
 * Gate 4A3 M-2: the seat diagram's geometry, checked as rules.
 */

import { describe, expect, it } from "vitest";

import {
  barSegments,
  blocStarts,
  hemicycleLayout,
  HEMICYCLE_VIEW,
  MIN_SEAT_DIAMETER_PX,
  seatDiameterPx,
  seatsTooSmall,
  tallyBar,
} from "./hemicycle";

function closestPair(seats: { x: number; y: number }[]): number {
  let best = Infinity;
  for (let i = 0; i < seats.length; i += 1) {
    for (let j = i + 1; j < seats.length; j += 1) {
      best = Math.min(best, Math.hypot(seats[i]!.x - seats[j]!.x, seats[i]!.y - seats[j]!.y));
    }
  }
  return best;
}

describe("the hemicycle layout", () => {
  it("places exactly one point per seat, for every chamber size from 1 to 400", () => {
    for (let n = 1; n <= 400; n += 1) {
      expect(hemicycleLayout(n).seats, `n=${n}`).toHaveLength(n);
    }
    expect(hemicycleLayout(0).seats).toHaveLength(0);
  });

  it("never lets two seats touch", () => {
    for (const n of [5, 31, 60, 100, 160, 250, 400]) {
      const layout = hemicycleLayout(n);
      expect(closestPair(layout.seats), `n=${n}`).toBeGreaterThan(layout.dotRadius * 2);
    }
  });

  it("orders seats left to right, so a bloc's seats form one wedge", () => {
    const { seats } = hemicycleLayout(100);
    expect(seats[0]!.x).toBeLessThan(HEMICYCLE_VIEW.cx);
    expect(seats[99]!.x).toBeGreaterThan(HEMICYCLE_VIEW.cx);
  });

  it("draws the shipped chambers (100 and 60 seats) at least 6 px wide at the 320 px width", () => {
    // At 320 px the chamber card leaves about 254 px for the plain (label-free) view, 700 units wide.
    for (const n of [100, 60]) {
      const layout = hemicycleLayout(n);
      expect(seatDiameterPx(layout, 254, 700), `n=${n}`).toBeGreaterThanOrEqual(MIN_SEAT_DIAMETER_PX);
      expect(seatsTooSmall(layout, 254, 700)).toBe(false);
    }
  });

  it("falls back to bars for a chamber too large to read at that width", () => {
    expect(seatsTooSmall(hemicycleLayout(400), 254, 700)).toBe(true);
  });
});

describe("bars and tallies", () => {
  it("bloc starts and bar segments follow the seat counts", () => {
    expect(blocStarts([45, 55])).toEqual([0, 45]);
    expect(barSegments([45, 55])).toEqual([
      { startPct: 0, widthPct: 45 },
      { startPct: 45, widthPct: 55 },
    ]);
  });

  it("the tally bar places support and the threshold as shares of the chamber", () => {
    expect(tallyBar(61, 51, 100)).toEqual({ supportPct: 61, requiredPct: 51 });
    expect(tallyBar(0, 0, 0)).toEqual({ supportPct: 0, requiredPct: 0 });
  });
});
