/**
 * The formation-marker geometry, tested where it lives.
 *
 * All of this is arithmetic, so all of it lives in `src/format/` -- `format-boundary.test.ts`
 * walks the real TypeScript AST and fails on any arithmetic `BinaryExpression` outside this
 * directory. Testing it here rather than only through the screen means the guarantees below are
 * statements about the rule, not about one component's use of it.
 */

import { describe, expect, it } from "vitest";

import {
  FORMATION_FAN_SLOTS,
  formationMarkerPlacements,
  formationOverflowLabel,
  type LabelAnchorValue,
} from "./format";

const CENTRE_X = 5000;
const CENTRE_Y = 5000;

function ids(count: number): string[] {
  return Array.from({ length: count }, (_, index) => `army_${String(index).padStart(2, "0")}`);
}

function place(count: number, anchor: LabelAnchorValue = "center") {
  return formationMarkerPlacements(CENTRE_X, CENTRE_Y, anchor, ids(count));
}

describe("formationMarkerPlacements: the rendering ceiling", () => {
  it.each([
    [1, 1, 0],
    [2, 2, 0],
    [6, 6, 0],
    [7, 5, 2],
    [20, 5, 15],
  ])("%i formations produce %i icons and hide %i", (count, icons, hidden) => {
    const placements = place(count);
    const individual = placements.filter((p) => p.formationId !== null);
    const overflow = placements.filter((p) => p.formationId === null);

    expect(individual).toHaveLength(icons);
    if (hidden === 0) {
      expect(overflow).toHaveLength(0);
    } else {
      expect(overflow).toHaveLength(1);
      expect(overflow[0].hiddenCount).toBe(hidden);
    }
  });

  it("never emits more markers than there are slots", () => {
    for (const count of [1, 2, 6, 7, 20, 100]) {
      expect(place(count).length).toBeLessThanOrEqual(FORMATION_FAN_SLOTS);
    }
  });

  it("the overflow control occupies a slot rather than being a seventh marker", () => {
    // Revision 3a's rule was six icons PLUS a control -- seven markers for six slots, with nowhere
    // stated for the seventh, so it could not guarantee the non-overlap it claimed.
    const placements = place(7);
    expect(placements).toHaveLength(FORMATION_FAN_SLOTS);
    expect(placements[placements.length - 1].formationId).toBeNull();
  });

  it("keeps the ids in the order it was given, never re-sorting", () => {
    const reversed = ["c", "b", "a"];
    expect(
      formationMarkerPlacements(CENTRE_X, CENTRE_Y, "center", reversed).map((p) => p.formationId),
    ).toEqual(reversed);
  });

  it("hides the LAST formations, so the first five in canonical order stay visible", () => {
    expect(
      place(7)
        .filter((p) => p.formationId !== null)
        .map((p) => p.formationId),
    ).toEqual(["army_00", "army_01", "army_02", "army_03", "army_04"]);
  });
});

describe("formationMarkerPlacements: geometry", () => {
  it.each([1, 2, 6, 7, 20])("places %i markers at distinct whole-unit positions", (count) => {
    const placements = place(count);
    const positions = placements.map((p) => `${p.x},${p.y}`);

    expect(new Set(positions).size).toBe(positions.length);
    for (const placement of placements) {
      expect(Number.isInteger(placement.x)).toBe(true);
      expect(Number.isInteger(placement.y)).toBe(true);
    }
  });

  it("puts every marker the same distance from the node", () => {
    const distances = place(6).map((p) =>
      Math.round(Math.hypot(p.x - CENTRE_X, p.y - CENTRE_Y)),
    );
    expect(new Set(distances).size).toBe(1);
  });

  it.each([
    ["n" as const, "below"],
    ["s" as const, "above"],
    ["center" as const, "above"],
  ])("with a %s anchor, slot 0 opens %s the node", (anchor, side) => {
    // The defect the mockups found: a fan starting due north puts slot 0 straight through the name
    // of every `anchor: n` theater -- three of five in `tiny_valid`.
    const [first] = formationMarkerPlacements(CENTRE_X, CENTRE_Y, anchor, ["only"]);
    if (side === "below") {
      expect(first.y).toBeGreaterThan(CENTRE_Y);
    } else {
      expect(first.y).toBeLessThan(CENTRE_Y);
    }
  });

  it.each([
    ["e" as const, -1],
    ["w" as const, 1],
  ])("with a %s anchor, slot 0 opens the other way", (anchor, direction) => {
    const [first] = formationMarkerPlacements(CENTRE_X, CENTRE_Y, anchor, ["only"]);
    expect(Math.sign(first.x - CENTRE_X)).toBe(direction);
  });

  it("is deterministic: the same inputs give byte-identical output", () => {
    expect(JSON.stringify(place(20, "n"))).toBe(JSON.stringify(place(20, "n")));
  });
});

describe("formationOverflowLabel", () => {
  it("states the exact hidden count", () => {
    expect(formationOverflowLabel(2)).toBe("+2");
    expect(formationOverflowLabel(15)).toBe("+15");
  });
});
