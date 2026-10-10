/**
 * Gate 4A3 victory path: the objective's words -- the D-V1 amendment lines and the preview's
 * conditional sentences. The effect inputs are the server's real previews
 * (`src/test/objective-results.json`, pinned by `backend/tests/test_objective_fixtures.py`).
 */

import { describe, expect, it } from "vitest";

import type { PreviewProjection, TurnResultProjection } from "../api/client";
import resultsJson from "../test/objective-results.json";
import {
  amendmentEnactedSentence,
  driverSentence,
  metText,
  objectiveEffectCaveat,
  objectiveEffectSentence,
  type ObjectiveEffectInput,
} from "./format";

const results = resultsJson as unknown as {
  reformResult: TurnResultProjection;
  previewPasses: PreviewProjection;
  previewFails: PreviewProjection;
  previewUnaffordable: PreviewProjection;
};

const EFFECTS: ObjectiveEffectInput["effect"][] = [
  "qualifies",
  "reform_continues",
  "reopens_route",
  "cannot_qualify",
  "keeps_transition",
  "ends_transition",
];

describe("metText", () => {
  it("states a condition in words, never by colour alone", () => {
    expect(metText(true)).toBe("Met");
    expect(metText(false)).toBe("Not yet");
  });
});

describe("D-V1: a named line per changed axis", () => {
  it("names every axis of the real Valdrun reform, from its stored params", () => {
    const lines = results.reformResult.drivers
      .filter((driver) => driver.reason_id === "constitutional_amendment_enacted")
      .map((driver) => driverSentence(driver.reason_id, driver.params ?? undefined, driver.label));
    expect(lines).toEqual([
      "Decree authority: unlimited → none.",
      "Executive selection: hereditary succession → direct election.",
      "Executive system: monarchical → presidential.",
      "Election schedule: none → every 4 turns.",
    ]);
    expect(new Set(lines).size).toBe(4);
  });

  it("words term limits, a removed schedule and singular counts", () => {
    expect(
      amendmentEnactedSentence({ axis: "executive_term_limit_terms", opening_value: "null", closing_value: "2" }),
    ).toBe("Term limit: none → 2 terms.");
    expect(
      amendmentEnactedSentence({ axis: "executive_term_limit_terms", opening_value: "2", closing_value: "1" }),
    ).toBe("Term limit: 2 terms → 1 term.");
    expect(
      amendmentEnactedSentence({ axis: "national_election_interval_turns", opening_value: "8", closing_value: "null" }),
    ).toBe("Election schedule: every 8 turns → none.");
    expect(
      amendmentEnactedSentence({ axis: "decree_authority", opening_value: "emergency_only", closing_value: "none" }),
    ).toBe("Decree authority: emergency only → none.");
  });

  it("falls back to the generic label rather than print an identifier", () => {
    expect(amendmentEnactedSentence({ axis: "legislature", opening_value: "a", closing_value: "b" })).toBeUndefined();
    expect(amendmentEnactedSentence({ axis: "decree_authority", opening_value: "none" })).toBeUndefined();
    expect(
      driverSentence("constitutional_amendment_enacted", { axis: "decree_authority", opening_value: "odd", closing_value: "none" }, "The constitution was amended."),
    ).toBe("The constitution was amended.");
  });
});

describe("the preview's effect, always IF ENACTED", () => {
  it("every effect is said conditionally and with no percentage", () => {
    for (const effect of EFFECTS) {
      for (const conditionsMet of [1, 2, 3]) {
        const sentence = objectiveEffectSentence({
          effect,
          conditions_met: conditionsMet,
          still_needed: ["No decree authority"],
          deciding_election_turn: 5,
          election_this_turn_too_soon: false,
        });
        expect(sentence.startsWith("If enacted,"), `${effect}: ${sentence}`).toBe(true);
        expect(sentence).not.toMatch(/%|will be recorded|will record/);
      }
    }
  });

  it("words the real previews exactly", () => {
    expect(objectiveEffectSentence(results.previewFails.objective_effect_if_enacted!)).toBe(
      "If enacted, this reform would record the qualifying transition; the election on turn 5 would decide.",
    );
    expect(objectiveEffectSentence(results.previewPasses.objective_effect_if_enacted!)).toBe(
      "If enacted, this reform would record the qualifying transition; the election on turn 20 would decide.",
    );
  });

  it("names the same-turn election, and an unknown one", () => {
    expect(
      objectiveEffectSentence({ effect: "qualifies", conditions_met: 3, deciding_election_turn: 37, election_this_turn_too_soon: true }),
    ).toBe(
      "If enacted, this reform would record the qualifying transition. This turn's election would come too soon to count; the election on turn 37 would decide.",
    );
    expect(objectiveEffectSentence({ effect: "keeps_transition", conditions_met: 3, deciding_election_turn: null })).toBe(
      "If enacted, the qualifying transition would stand; the next national election would decide.",
    );
  });

  it("states what remains, and the dead ends", () => {
    expect(
      objectiveEffectSentence({
        effect: "reform_continues",
        conditions_met: 1,
        still_needed: ["An elected executive", "No decree authority"],
      }),
    ).toBe("If enacted, 1 of 3 constitutional conditions would be met. Still needed: an elected executive and no decree authority.");
    expect(objectiveEffectSentence({ effect: "cannot_qualify", conditions_met: 2 })).toBe(
      "If enacted, the constitution could no longer qualify: it would leave non-competitive rule without meeting all three conditions in the same reform.",
    );
    expect(objectiveEffectSentence({ effect: "cannot_qualify", conditions_met: 3 })).toBe(
      "If enacted, all three conditions would be met, but this would not count as the qualifying reform: the constitution is not under non-competitive rule.",
    );
    expect(objectiveEffectSentence({ effect: "ends_transition", conditions_met: 2 })).toBe(
      "If enacted, this would end the qualifying transition, and the constitution would have to be reformed again.",
    );
    expect(objectiveEffectSentence({ effect: "reopens_route", conditions_met: 2 })).toBe(
      "If enacted, the constitution would return to non-competitive rule, so a later reform could qualify.",
    );
  });
});

describe("the caveat when resolving would not enact it", () => {
  it("says so for a failing vote and an unaffordable draft, and nothing when it would pass", () => {
    expect(objectiveEffectCaveat(results.previewPasses)).toBeNull();
    expect(objectiveEffectCaveat(results.previewFails)).toBe(
      "This amendment would not pass as it stands, so it would not change the constitution.",
    );
    expect(objectiveEffectCaveat(results.previewUnaffordable)).toBe(
      "This draft is not affordable, so resolving it would be refused.",
    );
  });
});
