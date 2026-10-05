/**
 * Gate 4A3 UX-4e (DR1): the turn's consequences, named, from each driver's stored params -- with the
 * real param names (`phases.py`), so a renamed param fails here rather than silently falling back.
 */

import { describe, expect, it } from "vitest";

import {
  SPENDING_LABEL,
  TAX_FIELD_LABEL,
  driverPriority,
  driverSentence,
  formatSignedPoints,
  isRoutineDriver,
  outcomeFirst,
} from "./format";

const vote = (outcome: string, passed: number, total: number) => ({
  route: outcome === "enacted_by_decree" ? "decree" : "legislative",
  outcome,
  chambers_passed: passed,
  chambers_total: total,
  supporting_seats: 0,
  required_yes_seats: 0,
  political_capital_committed: 0,
});

describe("the vote never claims a vote that was not held", () => {
  it("a decree says no vote was held, and never 'voted'", () => {
    const sentence = driverSentence("legislative_vote_resolved", vote("enacted_by_decree", 0, 0), "The legislature voted.");
    expect(sentence).toBe("Enacted by decree — no vote was held.");
    expect(sentence.toLowerCase()).not.toContain("voted");
  });

  it.each([
    ["passed_legislative", 1, 1, "The legislature passed the budget: 1 of 1 chamber carried."],
    ["failed_legislative", 0, 1, "The legislature voted the budget down: 0 of 1 chamber carried."],
    ["failed_legislative", 1, 2, "The legislature voted the budget down: 1 of 2 chambers carried."],
    ["no_proposal", 0, 0, "No budget was put to a vote."],
  ])("%s %i/%i", (outcome, passed, total, shown) => {
    expect(driverSentence("legislative_vote_resolved", vote(outcome as string, passed as number, total as number), "x")).toBe(shown);
  });

  it("names the blocking chamber and its shortfall", () => {
    expect(
      driverSentence(
        "budget_blocked_by_legislature",
        { chamber: "lower", supporting_seats: 45, required_yes_seats: 51, shortfall_seats: 6, opening: 500, total_committed: 0, legislative_committed: 0 },
        "x",
      ),
    ).toBe("Lower chamber blocked the budget: 45 supporting votes; 51 required—6 short.");
  });

  it("no longer words the tally as seats out of seats (UX-4g)", () => {
    const sentence = driverSentence(
      "budget_blocked_by_legislature",
      { chamber: "upper", supporting_seats: 20, required_yes_seats: 26, shortfall_seats: 6 },
      "x",
    );
    expect(sentence).toBe("Upper chamber blocked the budget: 20 supporting votes; 26 required—6 short.");
    expect(sentence).not.toMatch(/ of \d+ seats/);
  });
});

describe("policy changes state their figures", () => {
  it("a tax rate, old to new", () => {
    expect(
      driverSentence("tax_rate_changed", { field: "personal_income_rate_bps", old_bps: 2000, new_bps: 2500, category: "", old_amount: 0, new_amount: 0 }, "x"),
    ).toBe("Personal income tax: 20.00% → 25.00%.");
  });

  it("a spending category, in denars", () => {
    expect(
      driverSentence("spending_category_changed", { category: "defense", old_amount: 120_000_000, new_amount: 150_000_000 }, "x"),
    ).toBe("Defence spending: 1,200,000.00 → 1,500,000.00.");
  });

  it("labels every tax field and every spending category", () => {
    expect(Object.keys(TAX_FIELD_LABEL)).toHaveLength(3);
    expect(Object.keys(SPENDING_LABEL)).toHaveLength(7);
  });
});

describe("the state of the government, with figures", () => {
  it("legitimacy, capital and survival risk", () => {
    expect(
      driverSentence(
        "legitimacy_resolved",
        { opening_legitimacy_bps: 6000, closing_legitimacy_bps: 6100, total_legitimacy_change_bps: 100, order_support_contribution_bps: 0, performance_contribution_bps: 100, constitutional_order_support_bps: 5000 },
        "x",
      ),
    ).toBe("Legitimacy: 60.00% → 61.00% (+1.00 points).");
    expect(
      driverSentence("political_capital_resolved", { opening: 500, closing: 383, capacity: 1000, spent: 250, regeneration: 133, route: "decree", outcome: "enacted_by_decree" }, "x"),
    ).toBe("Political capital: 500 → 383 of 1,000 (250 spent, 133 regained).");
    expect(
      driverSentence("coup_risk_assessed", { coup_attempt_risk_bps: 352, unrest_attempt_risk_bps: 120, impeachment_attempt_risk_bps: 0, impeachment_eligible: 0, coup_structural_contribution_bps: 0, unrest_structural_contribution_bps: 0 }, "x"),
    ).toBe("Risk of an attempt this turn: coup 3.52%, unrest 1.20%.");
  });
});

describe("blocs are named", () => {
  const named = { party_id: "governing_party", bloc_id: "core", bloc_display_name: "Crown Party Core" };

  it.each([
    ["enacted_policy_relationship_reaction", { policy_reaction_component_bps: -150 }, "Crown Party Core reacted to the enacted policy (-1.50 points)."],
    ["decree_bypass_relationship_reaction", { decree_bypass_component_bps: -300 }, "Crown Party Core resented being bypassed by decree (-3.00 points)."],
    ["relationship_decay_resolved", { decay_component_bps: 50 }, "Crown Party Core drifted toward its usual stance (+0.50 points)."],
    [
      "bloc_relationship_resolved",
      { opening_relationship_bps: 6000, closing_relationship_bps: 5550, applied_total_change_bps: -450, uncapped_total_change_bps: -450 },
      "Crown Party Core: relationship 60.00% → 55.50% (-4.50 points).",
    ],
  ])("%s", (reason, params, shown) => {
    expect(driverSentence(reason as string, { ...named, ...(params as Record<string, number>) }, "x")).toBe(shown);
  });

  it.each([
    [20, -50, -70, "Crown Party Core: relationship 0.20% → -0.50% (-0.70 points)."],
    [-50, -99, -49, "Crown Party Core: relationship -0.50% → -0.99% (-0.49 points)."],
    [-99, 1, 100, "Crown Party Core: relationship -0.99% → 0.01% (+1.00 points)."],
  ])("a relationship below zero keeps its sign: %i -> %i (UX-4g)", (opening, closing, change, shown) => {
    expect(
      driverSentence(
        "bloc_relationship_resolved",
        { ...named, opening_relationship_bps: opening, closing_relationship_bps: closing, applied_total_change_bps: change },
        "x",
      ),
    ).toBe(shown);
  });

  it("without a projected name, falls back to the generic label -- never an id", () => {
    const sentence = driverSentence(
      "bloc_relationship_resolved",
      { party_id: "governing_party", bloc_id: "core", opening_relationship_bps: 1, closing_relationship_bps: 2, applied_total_change_bps: 1 },
      "A bloc's relationship with the government changed.",
    );
    expect(sentence).toBe("A bloc's relationship with the government changed.");
  });
});

describe("outcome first, and the two newly folded steps", () => {
  it("ranks the decision's outcome ahead of everything else, keeping server order within a rank", () => {
    expect(driverPriority("legislative_vote_resolved")).toBe(0);
    expect(driverPriority("legitimacy_resolved")).toBe(1);
    const ordered = outcomeFirst([
      { reason_id: "resource_extraction_resolved" },
      { reason_id: "legitimacy_resolved" },
      { reason_id: "legislative_vote_resolved" },
      { reason_id: "bloc_relationship_resolved" },
      { reason_id: "budget_blocked_by_legislature" },
    ]).map((d) => d.reason_id);
    expect(ordered).toEqual([
      "legislative_vote_resolved",
      "budget_blocked_by_legislature",
      "resource_extraction_resolved",
      "legitimacy_resolved",
      "bloc_relationship_resolved",
    ]);
  });

  it("folds the capital ledger and baseline drift into Routine steps; keeps the worker warning visible (DR2)", () => {
    expect(isRoutineDriver({ reason_id: "political_capital_ledger_resolved", params: {} })).toBe(true);
    expect(isRoutineDriver({ reason_id: "relationship_decay_resolved", params: {} })).toBe(true);
    expect(
      isRoutineDriver({ reason_id: "resource_extraction_resolved", params: { deposits_depleted: 0, unassigned_resource_workers: 6000 } }),
    ).toBe(false);
  });

  it("formats signed points", () => {
    expect([formatSignedPoints(250), formatSignedPoints(-75), formatSignedPoints(0)]).toEqual([
      "+2.50 points",
      "-0.75 points",
      "±0.00 points",
    ]);
  });
});
