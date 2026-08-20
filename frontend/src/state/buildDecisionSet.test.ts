/**
 * Gate 4A2 — proves `buildDecisions` emits canonical order BY CONSTRUCTION,
 * never by sorting a malformed payload after the fact. Each test builds a
 * `DraftState`-shaped object with fields deliberately populated in whatever
 * order a UI interaction would produce, and checks the emitted array's
 * canonical kind order and each decision's own canonical sub-ordering.
 */

import { describe, expect, it } from "vitest";

import { buildDecisions } from "./buildDecisionSet";
import type { DraftState } from "./draft";

function baseDraft(overrides: Partial<DraftState> = {}): DraftState {
  return {
    policySlot: null,
    budget: { spendingUpdates: {}, route: "legislative", influence: {} },
    amendment: { targets: {}, route: "legislative", influence: {} },
    investments: {},
    dismissedHelp: false,
    glossaryOpen: false,
    setPolicySlot: () => {},
    setBudgetRateTarget: () => {},
    setBudgetSpendingTarget: () => {},
    setBudgetRoute: () => {},
    setBudgetInfluence: () => {},
    setAmendmentTarget: () => {},
    setAmendmentRoute: () => {},
    setAmendmentInfluence: () => {},
    setInvestment: () => {},
    clearDraft: () => {},
    dismissHelp: () => {},
    setGlossaryOpen: () => {},
    ...overrides,
  };
}

describe("buildDecisions: no-proposal and omission", () => {
  it("emits an empty array for an untouched draft (a legal no-proposal turn)", () => {
    expect(buildDecisions(baseDraft())).toEqual([]);
  });

  it("omits a budget with no rate or spending target even if the slot is selected", () => {
    const draft = baseDraft({ policySlot: "budget" });
    expect(buildDecisions(draft)).toEqual([]);
  });

  it("omits an amendment with no axis targets even if the slot is selected", () => {
    const draft = baseDraft({ policySlot: "amendment" });
    expect(buildDecisions(draft)).toEqual([]);
  });
});

describe("buildDecisions: mutual exclusion of the policy slot", () => {
  it("emits ONLY the budget when policySlot is budget, even if amendment targets exist", () => {
    const draft = baseDraft({
      policySlot: "budget",
      budget: {
        spendingUpdates: { health: 1 },
        route: "legislative",
        influence: {},
      },
      amendment: {
        targets: { decree_authority: "unlimited" },
        route: "legislative",
        influence: {},
      },
    });
    const decisions = buildDecisions(draft);
    expect(decisions).toHaveLength(1);
    expect(decisions[0]?.["kind"]).toBe("budget");
  });

  it("emits ONLY the amendment when policySlot is amendment", () => {
    const draft = baseDraft({
      policySlot: "amendment",
      budget: { spendingUpdates: { health: 1 }, route: "legislative", influence: {} },
      amendment: {
        targets: { decree_authority: "unlimited" },
        route: "legislative",
        influence: {},
      },
    });
    const decisions = buildDecisions(draft);
    expect(decisions).toHaveLength(1);
    expect(decisions[0]?.["kind"]).toBe("constitutional_amendment");
  });
});

describe("buildDecisions: relationship investment stays a separate, non-exclusive slot", () => {
  it("emits both an investment and a budget in the same turn", () => {
    const draft = baseDraft({
      policySlot: "budget",
      budget: { spendingUpdates: { health: 1 }, route: "legislative", influence: {} },
      investments: { "governing_party/core": 10 },
    });
    const decisions = buildDecisions(draft);
    expect(decisions.map((d) => d["kind"])).toEqual(["bloc_relationship_investment", "budget"]);
  });

  it("emits an investment alone with no policy slot selected", () => {
    const draft = baseDraft({ investments: { "governing_party/core": 10 } });
    const decisions = buildDecisions(draft);
    expect(decisions).toHaveLength(1);
    expect(decisions[0]?.["kind"]).toBe("bloc_relationship_investment");
  });
});

describe("buildDecisions: canonical kind order regardless of construction order", () => {
  it("always places bloc_relationship_investment before budget before constitutional_amendment", () => {
    // Amendment can never coexist with budget (mutual exclusion), so this
    // proves investment-before-budget and investment-before-amendment
    // separately, which is the whole ordering space that can ever occur.
    const withBudget = baseDraft({
      policySlot: "budget",
      budget: { spendingUpdates: { health: 1 }, route: "legislative", influence: {} },
      investments: { "z_party/z_bloc": 5 },
    });
    expect(buildDecisions(withBudget).map((d) => d["kind"])).toEqual([
      "bloc_relationship_investment",
      "budget",
    ]);

    const withAmendment = baseDraft({
      policySlot: "amendment",
      amendment: { targets: { decree_authority: "none" }, route: "legislative", influence: {} },
      investments: { "z_party/z_bloc": 5 },
    });
    expect(buildDecisions(withAmendment).map((d) => d["kind"])).toEqual([
      "bloc_relationship_investment",
      "constitutional_amendment",
    ]);
  });
});

describe("buildDecisions: canonical (party_id, bloc_id) ordering within one decision", () => {
  it("sorts influence ascending by (party_id, bloc_id) regardless of insertion order", () => {
    const draft = baseDraft({
      policySlot: "budget",
      budget: {
        spendingUpdates: { health: 1 },
        route: "legislative",
        // Inserted out of order on purpose.
        influence: {
          "opposition_party/main": 5,
          "governing_party/core": 10,
        },
      },
    });
    const [budget] = buildDecisions(draft);
    const influence = budget?.["influence"] as { party_id: string; bloc_id: string }[];
    expect(influence.map((row) => `${row.party_id}/${row.bloc_id}`)).toEqual([
      "governing_party/core",
      "opposition_party/main",
    ]);
  });

  it("sorts investments ascending by (party_id, bloc_id)", () => {
    const draft = baseDraft({
      investments: {
        "z_party/a_bloc": 5,
        "a_party/z_bloc": 10,
      },
    });
    const [investment] = buildDecisions(draft);
    const rows = investment?.["investments"] as { party_id: string; bloc_id: string }[];
    expect(rows.map((row) => `${row.party_id}/${row.bloc_id}`)).toEqual([
      "a_party/z_bloc",
      "z_party/a_bloc",
    ]);
  });

  it("sorts amendment axis targets ascending by axis name", () => {
    const draft = baseDraft({
      policySlot: "amendment",
      amendment: {
        targets: {
          national_election_interval_turns: 4,
          decree_authority: "none",
          executive_system: "parliamentary",
        },
        route: "legislative",
        influence: {},
      },
    });
    const [amendment] = buildDecisions(draft);
    const targets = amendment?.["targets"] as { axis: string }[];
    expect(targets.map((t) => t.axis)).toEqual([
      "decree_authority",
      "executive_system",
      "national_election_interval_turns",
    ]);
  });
});

describe("buildDecisions: a decree route takes no influence", () => {
  it("omits influence entirely when the budget route is decree", () => {
    const draft = baseDraft({
      policySlot: "budget",
      budget: {
        spendingUpdates: { health: 1 },
        route: "decree",
        influence: { "governing_party/core": 10 },
      },
    });
    const [budget] = buildDecisions(draft);
    expect(budget?.["influence"]).toBeUndefined();
    expect(budget?.["route"]).toBe("decree");
  });
});
