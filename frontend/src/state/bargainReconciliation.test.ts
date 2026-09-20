import { describe, expect, it } from "vitest";

import { bargainAfterPolicySlotChange, bargainAfterRouteChange, useDraftStore } from "./draft";

/**
 * The cross-slot rule, which is the defect a first draft of this feature shipped without.
 *
 * A bargain names a `proposalKind`, and slot 1 refuses the whole set with
 * `legislative_bargain_proposal_absent` when the set carries no proposal of that kind. So a player
 * who stages a budget bargain and then clears the proposal, or switches to an amendment, would be
 * holding a draft that CANNOT preview — with nothing on screen explaining why.
 */
describe("bargainAfterPolicySlotChange — the pure rule", () => {
  const bargain = { characterId: "leader_rural_alliance", proposalKind: "budget" } as const;

  it("clears on budget -> null", () => {
    expect(bargainAfterPolicySlotChange(bargain, null)).toBeNull();
  });

  it("clears on budget -> amendment", () => {
    expect(bargainAfterPolicySlotChange(bargain, "amendment")).toBeNull();
  });

  it("RETAINS on budget -> budget", () => {
    // The interesting half. The server binds a bargain to the proposal KIND, never to a digest, so
    // swapping one budget for another leaves the bargain describing exactly what is still there.
    expect(bargainAfterPolicySlotChange(bargain, "budget")).toEqual(bargain);
  });

  it("is a no-op when nothing is staged", () => {
    expect(bargainAfterPolicySlotChange(null, "amendment")).toBeNull();
  });
});

describe("the store applies the rule ATOMICALLY", () => {
  const stage = () => {
    useDraftStore.getState().clearDraft();
    useDraftStore.getState().setPolicySlot("budget");
    useDraftStore.getState().setBargain("leader_rural_alliance", "budget");
  };

  it("clears the bargain in the same update that clears the slot", () => {
    stage();
    expect(useDraftStore.getState().bargain).not.toBeNull();
    useDraftStore.getState().setPolicySlot(null);
    const state = useDraftStore.getState();
    // Both halves observed together: no render can see a slot-less draft still holding a bargain.
    expect(state.policySlot).toBeNull();
    expect(state.bargain).toBeNull();
  });

  it("clears the bargain when the slot switches to an amendment", () => {
    stage();
    useDraftStore.getState().setPolicySlot("amendment");
    expect(useDraftStore.getState().bargain).toBeNull();
  });

  it("keeps the bargain when the slot stays a budget", () => {
    stage();
    useDraftStore.getState().setPolicySlot("budget");
    expect(useDraftStore.getState().bargain).toEqual({
      characterId: "leader_rural_alliance",
      proposalKind: "budget",
    });
  });

  it("applies the same rule through applyCard, not just setPolicySlot", () => {
    // Two mutators can change the slot, so the rule lives in ONE function both call. If `applyCard`
    // ever forgot it, this is the test that notices.
    stage();
    useDraftStore.getState().applyCard({
      policySlot: "amendment",
      budget: undefined,
      amendment: { targets: {}, route: "legislative" },
    });
    expect(useDraftStore.getState().bargain).toBeNull();
  });

  it("clearDraft resets all three negotiation slots", () => {
    useDraftStore.getState().clearDraft();
    useDraftStore.getState().setPolicySlot("budget");
    useDraftStore.getState().setBargain("x", "budget");
    useDraftStore.getState().setAssistanceRequest("kessia");
    useDraftStore.getState().setPromise({
      action: "release",
      characterId: "x",
      promiseId: "pr_x",
    });
    useDraftStore.getState().clearDraft();
    const state = useDraftStore.getState();
    expect(state.bargain).toBeNull();
    expect(state.assistance).toBeNull();
    expect(state.promise).toBeNull();
  });
});

/**
 * The ROUTE rule — the same defect one level down, and the one a first pass at this screen missed.
 *
 * Clearing the slot is not the only way to strand a bargain. Keeping the budget and switching its
 * ROUTE to decree strands it too: ruleset 0.23.0 refuses the set with
 * `legislative_bargain_requires_legislative_route`, because a decree holds no chamber vote for an
 * endorsement to move. A draft that cannot preview is the defect, whichever field caused it.
 */
describe("bargainAfterRouteChange — the pure rule", () => {
  const bargain = { characterId: "leader_rural_alliance", proposalKind: "budget" } as const;

  it("clears when the budget it names turns into a decree", () => {
    expect(bargainAfterRouteChange(bargain, "budget", "decree")).toBeNull();
  });

  it("RETAINS when the route stays with the chamber", () => {
    expect(bargainAfterRouteChange(bargain, "budget", "legislative")).toEqual(bargain);
  });

  it("ignores a route change on the OTHER proposal kind", () => {
    // Unreachable today, because the slot rule keeps the bargain's kind equal to the current slot.
    // Guarded anyway so the two rules compose instead of depending on each other's invariants.
    expect(bargainAfterRouteChange(bargain, "amendment", "decree")).toEqual(bargain);
  });

  it("is a no-op when nothing is staged", () => {
    expect(bargainAfterRouteChange(null, "budget", "decree")).toBeNull();
  });
});

describe("the store applies the ROUTE rule atomically too", () => {
  it("drops a staged bargain when the budget is switched to a decree", () => {
    useDraftStore.getState().clearDraft();
    useDraftStore.getState().setPolicySlot("budget");
    useDraftStore.getState().setBargain("leader_rural_alliance", "budget");
    useDraftStore.getState().setBudgetRoute("decree");

    const state = useDraftStore.getState();
    expect(state.bargain).toBeNull();
    // The proposal itself is untouched — only the bargain the engine would have refused is gone.
    expect(state.policySlot).toBe("budget");
    expect(state.budget.route).toBe("decree");
  });

  it("does the same for an amendment", () => {
    useDraftStore.getState().clearDraft();
    useDraftStore.getState().setPolicySlot("amendment");
    useDraftStore.getState().setBargain("leader_rural_alliance", "amendment");
    useDraftStore.getState().setAmendmentRoute("decree");
    expect(useDraftStore.getState().bargain).toBeNull();
  });

  it("keeps the bargain when the route moves back to the chamber", () => {
    useDraftStore.getState().clearDraft();
    useDraftStore.getState().setPolicySlot("budget");
    useDraftStore.getState().setBargain("leader_rural_alliance", "budget");
    useDraftStore.getState().setBudgetRoute("legislative");
    expect(useDraftStore.getState().bargain).toEqual({
      characterId: "leader_rural_alliance",
      proposalKind: "budget",
    });
  });
});
