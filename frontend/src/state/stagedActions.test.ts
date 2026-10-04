/**
 * Gate 4A3 UX-4b (U8): `stagedActions` counts player actions that WILL BE SUBMITTED -- never a
 * proposal the builder would drop.
 *
 * Every phantom case asserts two things together: the proposal is not counted, AND the same draft
 * submits nothing for it (`buildDecisions` carries no budget or amendment). Agreement between the
 * surfaces is worthless if they all count something the server will never see.
 */

import { beforeEach, describe, expect, it } from "vitest";

import { buildDecisions } from "./buildDecisionSet";
import { useDraftStore } from "./draft";
import { stagedActions } from "./stagedActions";

const store = () => useDraftStore.getState();
const proposalKinds = new Set(["budget", "constitutional_amendment"]);

function submittedProposals(): string[] {
  return buildDecisions(store())
    .map((d) => (d as { kind: string }).kind)
    .filter((kind) => proposalKinds.has(kind));
}

function stagedProposals(): number {
  return stagedActions(store()).filter((a) => a.kind === "proposal").length;
}

beforeEach(() => {
  store().clearDraft();
});

describe("no phantom proposals", () => {
  it("a budget slot selected with no rate or spending target counts 0 and submits nothing", () => {
    store().setPolicySlot("budget");
    expect(stagedProposals()).toBe(0);
    expect(submittedProposals()).toEqual([]);
    expect(stagedActions(store())).toEqual([]);
  });

  it("an amendment slot selected with no target counts 0 and submits nothing", () => {
    store().setPolicySlot("amendment");
    expect(stagedProposals()).toBe(0);
    expect(submittedProposals()).toEqual([]);
  });

  it("influence entered on a target-less budget counts 0, and the influence is not submitted", () => {
    store().setPolicySlot("budget");
    store().setBudgetInfluence("governing_party", "core", 40);
    expect(stagedProposals()).toBe(0);
    expect(submittedProposals()).toEqual([]);
    expect(JSON.stringify(buildDecisions(store()))).not.toContain("influence");
  });

  it("influence entered on a target-less amendment counts 0, and the influence is not submitted", () => {
    store().setPolicySlot("amendment");
    store().setAmendmentInfluence("governing_party", "core", 40);
    expect(stagedProposals()).toBe(0);
    expect(submittedProposals()).toEqual([]);
    expect(JSON.stringify(buildDecisions(store()))).not.toContain("influence");
  });

  it("a target-less budget or amendment on the decree route counts 0", () => {
    store().setPolicySlot("budget");
    store().setBudgetRoute("decree");
    expect(stagedProposals()).toBe(0);
    expect(submittedProposals()).toEqual([]);
    store().setPolicySlot("amendment");
    store().setAmendmentRoute("decree");
    expect(stagedProposals()).toBe(0);
    expect(submittedProposals()).toEqual([]);
  });

  it("'no major action' counts 0, even with a budget draft left behind in state", () => {
    store().setPolicySlot("budget");
    store().setBudgetRateTarget("personalIncomeRateBps", 3_000);
    store().setPolicySlot(null);
    expect(stagedProposals()).toBe(0);
    expect(submittedProposals()).toEqual([]);
  });

  it("positive control: one rate target makes the budget count 1, and submits exactly that budget", () => {
    store().setPolicySlot("budget");
    store().setBudgetInfluence("governing_party", "core", 40);
    expect(stagedProposals()).toBe(0);
    store().setBudgetRateTarget("personalIncomeRateBps", 3_000);
    expect(stagedProposals()).toBe(1);
    expect(submittedProposals()).toEqual(["budget"]);
  });

  it("positive control: one amendment target makes the amendment count 1", () => {
    store().setPolicySlot("amendment");
    store().setAmendmentTarget("decree_authority", "none");
    expect(stagedProposals()).toBe(1);
    expect(submittedProposals()).toEqual(["constitutional_amendment"]);
  });
});

describe("player actions, not wire orders", () => {
  it("one transfer is 1 staged action and 2 wire orders, with the vacated post as its consequence", () => {
    store().confirmAppointment("chief_of_staff", "char_b", "foreign_minister");
    const actions = stagedActions(store());
    expect(actions).toEqual([
      {
        kind: "cabinet",
        post: "chief_of_staff",
        characterId: "char_b",
        consequences: [{ post: "foreign_minister", characterId: null }],
      },
    ]);
    const cabinet = buildDecisions(store()).find((d) => (d as { kind: string }).kind === "cabinet") as {
      orders: unknown[];
    };
    expect(cabinet.orders).toHaveLength(2);
  });

  it("a mixed draft: N differs from buildDecisions().length, and every action maps to one decision", () => {
    store().confirmAppointment("chief_of_staff", "char_b", "foreign_minister");
    store().setInvestment("governing_party", "core", 20);
    store().setInvestment("opposition_party", "main", 30);
    store().setPolicySlot("budget");
    store().setBudgetRateTarget("personalIncomeRateBps", 3_000);
    const actions = stagedActions(store());
    const decisions = buildDecisions(store()).map((d) => (d as { kind: string }).kind);
    expect(actions.map((a) => a.kind)).toEqual(["proposal", "cabinet", "investment", "investment"]);
    expect(actions).toHaveLength(4);
    expect(decisions).toEqual(["bloc_relationship_investment", "budget", "cabinet"]);
    const decisionFor: Record<string, string> = {
      proposal: "budget",
      cabinet: "cabinet",
      investment: "bloc_relationship_investment",
    };
    for (const action of actions) {
      expect(decisions, action.kind).toContain(decisionFor[action.kind]);
    }
  });

  it("the singletons each count once", () => {
    store().setAssistanceRequest("kessia");
    store().setMovementOrder("formation_1", "theater_2");
    store().setPromise({ action: "release", characterId: "char_c", promiseId: "promise_1" });
    expect(stagedActions(store()).map((a) => a.kind)).toEqual(["assistance", "promise", "movement"]);
    expect(buildDecisions(store())).toHaveLength(3);
  });
});
