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
  driverSentence,
  labelOffsetPosition,
  refusalReasonText,
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

describe("formationMarkerPlacements: no marker lands on its own theater's name", () => {
  // Commit 7 tested the `n` anchor, which is the case drawing the mockups found. All five are
  // asserted here: the guarantee is about slot 0 for EVERY anchor, not only the one that broke.
  const ANCHORS: LabelAnchorValue[] = ["n", "s", "e", "w", "center"];

  /** Where `labelOffsetPosition` puts this theater's name, in the same grid units. */
  function labelAt(anchor: LabelAnchorValue) {
    return labelOffsetPosition(CENTRE_X, CENTRE_Y, anchor);
  }

  it.each(ANCHORS)("slot 0 clears the label for anchor %s", (anchor) => {
    const [first] = formationMarkerPlacements(CENTRE_X, CENTRE_Y, anchor, ["only"]);
    const label = labelAt(anchor);

    // "Clears" means genuinely apart, not merely unequal: a marker one unit from the text would
    // pass an inequality check and still be unreadable.
    const separation = Math.hypot(first.x - label.x, first.y - label.y);
    expect(separation).toBeGreaterThan(400);
  });

  it.each(ANCHORS)("slot 0 never sits on the node itself for anchor %s", (anchor) => {
    const [first] = formationMarkerPlacements(CENTRE_X, CENTRE_Y, anchor, ["only"]);
    expect(Math.hypot(first.x - CENTRE_X, first.y - CENTRE_Y)).toBeGreaterThan(400);
  });

  it("the separation check would fail if a marker were placed on the label", () => {
    // Anti-vacuity for the threshold above: the same measurement against a deliberately colliding
    // position must fall under it, or the assertions would pass for any geometry at all.
    const label = labelAt("n");
    expect(Math.hypot(label.x - label.x, label.y - label.y)).toBeLessThan(400);
  });
});


describe("refusalReasonText", () => {
  it("gives plain English for every code this build emits", () => {
    expect(refusalReasonText("cabinet_character_leads_a_party")).toContain("leads a party");
    expect(refusalReasonText("cabinet_candidate_refuses_low_legitimacy")).toContain("legitimacy");
    expect(refusalReasonText("cabinet_candidate_refuses_this_post")).toContain("beneath them");
  });

  it("never returns the raw code, for any code including unknown ones", () => {
    const codes = [
      "cabinet_character_leads_a_party",
      "cabinet_candidate_refuses_low_legitimacy",
      "cabinet_candidate_refuses_this_post",
      "cabinet_some_future_refusal_nobody_has_worded_yet",
      null,
      undefined,
    ];
    for (const code of codes) {
      const text = refusalReasonText(code);
      expect(text).not.toMatch(/[a-z]+_[a-z]+/);
      expect(text.length).toBeGreaterThan(0);
      if (typeof code === "string") {
        expect(text).not.toContain(code);
      }
    }
  });

  it("gives an unrecognised code generic prose that still reads as a refusal", () => {
    expect(refusalReasonText("cabinet_some_future_refusal")).toBe("Will not serve.");
  });
});


describe("driverSentence", () => {
  const cabinetParams = {
    post: "chief_of_staff",
    post_display_name: "chief of staff",
    capital_committed: 276,
    character_id: "ilse_marovec",
    character_display_name: "Ilse Marovec",
    outgoing_character_id: "hal_verrin",
    outgoing_character_display_name: "Hal Verrin",
  };

  it("names both people in a replacement", () => {
    expect(driverSentence("cabinet_replaced", cabinetParams, "A cabinet post changed hands.")).toBe(
      "Ilse Marovec replaced Hal Verrin as chief of staff for 276 political capital.",
    );
  });

  it("names the appointee in an appointment", () => {
    expect(driverSentence("cabinet_appointed", cabinetParams, "A cabinet post was filled.")).toBe(
      "Ilse Marovec was appointed chief of staff for 276 political capital.",
    );
  });

  it("names the departing holder in a dismissal, and quotes no cost", () => {
    const sentence = driverSentence("cabinet_dismissed", cabinetParams, "A cabinet post was vacated.");
    expect(sentence).toBe("Hal Verrin was dismissed as chief of staff; the post is now vacant.");
    expect(sentence).not.toContain("276");
  });

  it("composes from the STORED params, never from any current state", () => {
    // The names a past turn was resolved under, even when they are nothing like today's roster.
    const historical = { ...cabinetParams, character_display_name: "Someone Long Gone" };
    expect(driverSentence("cabinet_replaced", historical, "x")).toContain("Someone Long Gone");
  });

  it("falls back to the generic label for an unknown reason, and for absent params", () => {
    expect(driverSentence("formation_moved", cabinetParams, "A formation moved.")).toBe(
      "A formation moved.",
    );
    expect(driverSentence("cabinet_replaced", undefined, "A cabinet post changed hands.")).toBe(
      "A cabinet post changed hands.",
    );
    expect(driverSentence("cabinet_replaced", { post_display_name: "x" }, "fallback")).toBe("fallback");
  });

  it("never renders a raw identifier when it composes a sentence", () => {
    for (const reason of ["cabinet_appointed", "cabinet_replaced", "cabinet_dismissed"]) {
      const sentence = driverSentence(reason, cabinetParams, "generic");
      expect(sentence).not.toContain("chief_of_staff");
      expect(sentence).not.toContain("ilse_marovec");
      expect(sentence).not.toContain("hal_verrin");
    }
  });

  // Characters slice: the legislative bargain. The two fixtures use DIFFERENT leaders on purpose --
  // Maret Kuusk genuinely accepts under the engine's gate and Nadia Brekke genuinely refuses, so
  // neither sentence is illustrated with somebody who would never produce it.
  const acceptedParams = {
    character_id: "leader_rural_alliance",
    character_display_name: "Maret Kuusk",
    party_id: "rural_alliance",
    party_display_name: "Rural Alliance",
    proposal_kind: "budget",
    proposal_display_name: "the budget",
    asking_price: 105,
    endorsement_bps: 2000,
  };

  // A strict SUBSET: no `asking_price`, no `endorsement_bps`. A refusal commits nothing, so its
  // entry has no field in which a price could travel.
  const refusedParams = {
    character_id: "leader_opposition_party",
    character_display_name: "Nadia Brekke",
    party_id: "opposition_party",
    party_display_name: "Reform Opposition",
    proposal_kind: "budget",
    proposal_display_name: "the budget",
  };

  it("names the leader, the party, the proposal and the price paid on an acceptance", () => {
    expect(
      driverSentence(
        "legislative_bargain_accepted",
        acceptedParams,
        "A party leader backed the proposal.",
      ),
    ).toBe("Maret Kuusk of the Rural Alliance backed the budget, for 105 political capital.");
  });

  it("states no figure on a refusal, because the params carry none", () => {
    const sentence = driverSentence(
      "legislative_bargain_refused_will_not_deal",
      refusedParams,
      "A party leader refused to deal.",
    );
    expect(sentence).toBe("Nadia Brekke of the Reform Opposition would not deal over the budget.");
    // The removed counteroffer, kept removed: the sentence cannot name a price the player might
    // have paid, because no such param exists on a refusal.
    expect(sentence).not.toContain("105");
    expect(Object.keys(refusedParams)).not.toContain("asking_price");
    expect(Object.keys(refusedParams)).not.toContain("endorsement_bps");
  });

  it("falls back to the generic label when a bargain param is missing", () => {
    const { asking_price: _price, ...withoutPrice } = acceptedParams;
    expect(driverSentence("legislative_bargain_accepted", withoutPrice, "generic")).toBe("generic");
  });

  it("renders no raw identifier for either bargain outcome", () => {
    const cases: [string, Record<string, string | number>][] = [
      ["legislative_bargain_accepted", acceptedParams],
      ["legislative_bargain_refused_will_not_deal", refusedParams],
    ];
    for (const [reason, params] of cases) {
      const sentence = driverSentence(reason, params, "generic");
      for (const raw of [
        "leader_rural_alliance",
        "leader_opposition_party",
        "rural_alliance",
        "opposition_party",
        "constitutional_amendment",
        "legislative_bargain",
      ]) {
        expect(sentence).not.toContain(raw);
      }
    }
  });
});
