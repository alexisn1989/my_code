/**
 * Gate 4A2 — proves `buildDecisions` emits canonical order BY CONSTRUCTION,
 * never by sorting a malformed payload after the fact. Each test builds a
 * `DraftState`-shaped object with fields deliberately populated in whatever
 * order a UI interaction would produce, and checks the emitted array's
 * canonical kind order and each decision's own canonical sub-ordering.
 */

import { describe, expect, it } from "vitest";

import { buildDecisions } from "./buildDecisionSet";
import { useDraftStore, type DraftState } from "./draft";

function baseDraft(overrides: Partial<DraftState> = {}): DraftState {
  return {
    policySlot: null,
    budget: { spendingUpdates: {}, route: "legislative", influence: {} },
    amendment: { targets: {}, route: "legislative", influence: {} },
    investments: {},
    movement: null,
    dismissedHelp: false,
    glossaryOpen: false,
    setPolicySlot: () => {},
    applyCard: () => {},
    setBudgetRateTarget: () => {},
    setBudgetSpendingTarget: () => {},
    setBudgetRoute: () => {},
    setBudgetInfluence: () => {},
    setAmendmentTarget: () => {},
    setAmendmentRoute: () => {},
    setAmendmentInfluence: () => {},
    setMovementOrder: () => {},
    clearMovementOrder: () => {},
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

// --------------------------------------------------------------------------
// Movement combines with every other kind (Military Movement, commit 8)
// --------------------------------------------------------------------------
//
// `military_movement` sorts LAST of the four kinds, and the server rejects a noncanonical set
// rather than sorting it. Each row below states the resulting array exactly -- no elided or
// optional member -- so a reader can see the ordering rather than infer it.

const MOVEMENT = { formationId: "arken_first_army", destinationTheaterId: "arken_north" };

const MOVEMENT_DECISION = {
  kind: "military_movement",
  orders: [{ formation_id: "arken_first_army", destination_theater_id: "arken_north" }],
};

describe("buildDecisions: movement", () => {
  it("emits nothing when no order is staged", () => {
    expect(buildDecisions(baseDraft())).toEqual([]);
  });

  it("movement only", () => {
    expect(buildDecisions(baseDraft({ movement: MOVEMENT }))).toEqual([MOVEMENT_DECISION]);
  });

  it("movement + relationship investment", () => {
    const decisions = buildDecisions(
      baseDraft({ movement: MOVEMENT, investments: { "party_a|bloc_a": 5 } }),
    );
    expect(decisions.map((d) => d.kind)).toEqual([
      "bloc_relationship_investment",
      "military_movement",
    ]);
  });

  it("movement + budget", () => {
    const decisions = buildDecisions(
      baseDraft({
        movement: MOVEMENT,
        policySlot: "budget",
        budget: { personalIncomeRateBps: 2500, spendingUpdates: {}, route: "legislative", influence: {} },
      }),
    );
    expect(decisions.map((d) => d.kind)).toEqual(["budget", "military_movement"]);
  });

  it("movement + constitutional amendment", () => {
    const decisions = buildDecisions(
      baseDraft({
        movement: MOVEMENT,
        policySlot: "amendment",
        amendment: { targets: { decree_authority: "unlimited" }, route: "legislative", influence: {} },
      }),
    );
    expect(decisions.map((d) => d.kind)).toEqual([
      "constitutional_amendment",
      "military_movement",
    ]);
  });

  it("movement + relationship investment + budget", () => {
    const decisions = buildDecisions(
      baseDraft({
        movement: MOVEMENT,
        investments: { "party_a|bloc_a": 5 },
        policySlot: "budget",
        budget: { personalIncomeRateBps: 2500, spendingUpdates: {}, route: "legislative", influence: {} },
      }),
    );
    expect(decisions.map((d) => d.kind)).toEqual([
      "bloc_relationship_investment",
      "budget",
      "military_movement",
    ]);
  });

  it("movement + relationship investment + amendment", () => {
    const decisions = buildDecisions(
      baseDraft({
        movement: MOVEMENT,
        investments: { "party_a|bloc_a": 5 },
        policySlot: "amendment",
        amendment: { targets: { decree_authority: "unlimited" }, route: "legislative", influence: {} },
      }),
    );
    expect(decisions.map((d) => d.kind)).toEqual([
      "bloc_relationship_investment",
      "constitutional_amendment",
      "military_movement",
    ]);
  });

  it("is built from the draft's CONTENT, not the order the player clicked", () => {
    // The array is assembled from a plain object with no ordering of its own, so two players who
    // staged the same turn in opposite orders must submit byte-identical payloads -- otherwise
    // they would digest differently and produce different `entry_hash`es for the same decisions.
    const budget = {
      personalIncomeRateBps: 2500,
      spendingUpdates: {},
      route: "legislative" as const,
      influence: {},
    };
    const movementFirst = buildDecisions(
      baseDraft({ movement: MOVEMENT, policySlot: "budget", budget }),
    );
    const budgetFirst = buildDecisions(
      baseDraft({ policySlot: "budget", budget, movement: MOVEMENT }),
    );

    expect(JSON.stringify(movementFirst)).toBe(JSON.stringify(budgetFirst));
  });
});

// --------------------------------------------------------------------------
// The staged order's lifetime (frozen plan §9.1.1, §9.2 F7)
// --------------------------------------------------------------------------
//
// Resolution happens on the Decisions screen, so the map is NOT mounted when a turn resolves.
// Nothing attempts to focus an unmounted map node, and the staged order's survival is a property
// of the shared draft store rather than of any screen -- which is exactly why it can be asserted
// here, one layer below the screens.

describe("the staged movement order's lifetime", () => {
  it("is reconstructed from the draft alone, so navigating away cannot lose it", () => {
    // The map holds no order state of its own: everything it displays about a staged order comes
    // from this store, so unmounting and remounting the screen is a no-op for the order.
    useDraftStore.getState().clearDraft();
    useDraftStore.getState().setMovementOrder("arken_first_army", "arken_north");

    expect(useDraftStore.getState().movement).toEqual({
      formationId: "arken_first_army",
      destinationTheaterId: "arken_north",
    });
    expect(buildDecisions(useDraftStore.getState()).map((d) => d.kind)).toEqual([
      "military_movement",
    ]);
  });

  it("a second order replaces the first rather than accumulating", () => {
    useDraftStore.getState().clearDraft();
    useDraftStore.getState().setMovementOrder("first", "a");
    useDraftStore.getState().setMovementOrder("second", "b");

    const decisions = buildDecisions(useDraftStore.getState());
    expect(decisions).toHaveLength(1);
    expect(decisions[0]).toEqual({
      kind: "military_movement",
      orders: [{ formation_id: "second", destination_theater_id: "b" }],
    });
  });

  it("clearDraft removes it, which is what stops it crossing campaigns", () => {
    // `clearDraft` runs on a successful resolve AND on New Game / Load. Without that last part a
    // `formationId` from a previous scenario -- an id that may not exist in the new one -- would
    // be submitted against the wrong campaign.
    useDraftStore.getState().setMovementOrder("arken_first_army", "arken_north");
    useDraftStore.getState().clearDraft();

    expect(useDraftStore.getState().movement).toBeNull();
    expect(buildDecisions(useDraftStore.getState())).toEqual([]);
  });

  it("survives everything short of a clear, so a FAILED resolve keeps it", () => {
    // `clearDraft` lives inside `onSuccess` only. A rejected or errored resolve leaves the whole
    // draft -- movement included -- intact for the player to correct and retry.
    useDraftStore.getState().clearDraft();
    useDraftStore.getState().setMovementOrder("arken_first_army", "arken_north");
    useDraftStore.getState().setPolicySlot("budget");
    useDraftStore.getState().setBudgetRateTarget("personalIncomeRateBps", 2500);

    expect(buildDecisions(useDraftStore.getState()).map((d) => d.kind)).toEqual([
      "budget",
      "military_movement",
    ]);
    expect(useDraftStore.getState().movement).not.toBeNull();
  });
});
