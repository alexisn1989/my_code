/**
 * Gate 4A3A — proves `mapPolicyCardToDraft` copies a real server template
 * through unchanged (no arithmetic, no invented fields) and correctly
 * clears the incompatible slot's shape for `applyCard` to apply wholesale.
 */

import { describe, expect, it } from "vitest";

import type { PolicyCard, PolicyCardRoute } from "../api/client";
import { mapPolicyCardToDraft } from "./applyPolicyCard";

function budgetRoute(overrides: Partial<PolicyCardRoute> = {}): PolicyCardRoute {
  return {
    route: "legislative",
    available: true,
    base_route_cost: 0,
    bargaining_available: true,
    chambers: [],
    template: {
      kind: "budget",
      route: "legislative",
      personal_income_rate_bps: 2500,
      spending_updates: [{ category: "health", amount: 220_000_000 }],
    },
    ...overrides,
  };
}

function amendmentRoute(overrides: Partial<PolicyCardRoute> = {}): PolicyCardRoute {
  return {
    route: "legislative",
    available: true,
    base_route_cost: 0,
    bargaining_available: true,
    chambers: [],
    template: {
      kind: "constitutional_amendment",
      route: "legislative",
      targets: [{ axis: "decree_authority", value: "unlimited" }],
    },
    ...overrides,
  };
}

function baseCard(overrides: Partial<PolicyCard> = {}): PolicyCard {
  return {
    card_id: "tax_personal_income_increase",
    category: "taxation",
    category_label: "Taxation",
    title: "Raise the personal income tax",
    description: "Raise the personal income tax rate.",
    available: true,
    clears_proposal_slot: false,
    effects: [],
    routes: [budgetRoute()],
    ...overrides,
  };
}

describe("mapPolicyCardToDraft: budget templates", () => {
  it("copies every raw field through unchanged, never summing or scaling", () => {
    const card = baseCard();
    const applied = mapPolicyCardToDraft(card, card.routes[0]!);
    expect(applied).toEqual({
      policySlot: "budget",
      budget: {
        personalIncomeRateBps: 2500,
        corporateRateBps: undefined,
        consumptionRateBps: undefined,
        spendingUpdates: { health: 220_000_000 },
        route: "legislative",
      },
    });
  });

  it("carries the route's own route value, not a hardcoded default", () => {
    const route = budgetRoute({
      route: "decree",
      template: { kind: "budget", route: "decree", personal_income_rate_bps: 1500 },
    });
    const applied = mapPolicyCardToDraft(baseCard({ routes: [route] }), route);
    expect(applied.budget?.route).toBe("decree");
  });

  it("maps an empty spending_updates array to an empty record, not undefined", () => {
    const route = budgetRoute({
      template: { kind: "budget", route: "legislative", corporate_rate_bps: 3000 },
    });
    const applied = mapPolicyCardToDraft(baseCard({ routes: [route] }), route);
    expect(applied.budget?.spendingUpdates).toEqual({});
  });
});

describe("mapPolicyCardToDraft: amendment templates", () => {
  it("copies every target axis/value through unchanged", () => {
    const card = baseCard({
      card_id: "constitution_decree_authority_to_unlimited",
      category: "constitution",
      routes: [amendmentRoute()],
    });
    const applied = mapPolicyCardToDraft(card, card.routes[0]!);
    expect(applied).toEqual({
      policySlot: "amendment",
      amendment: {
        targets: { decree_authority: "unlimited" },
        route: "legislative",
      },
    });
  });

  it("copies a null target value through unchanged (abolishing a term limit)", () => {
    const route = amendmentRoute({
      template: {
        kind: "constitutional_amendment",
        route: "legislative",
        targets: [{ axis: "executive_term_limit_terms", value: null }],
      },
    });
    const applied = mapPolicyCardToDraft(baseCard({ routes: [route] }), route);
    expect(applied.amendment?.targets).toEqual({ executive_term_limit_terms: null });
  });
});

describe("mapPolicyCardToDraft: the no-proposal card", () => {
  it("clears the policy slot entirely, with no budget or amendment fields", () => {
    const card = baseCard({
      card_id: "no_proposal",
      category: "restraint",
      clears_proposal_slot: true,
      routes: [],
    });
    // The no-proposal card has no routes; the route argument is never read
    // for a clears_proposal_slot card, so an arbitrary route stands in.
    const applied = mapPolicyCardToDraft(card, budgetRoute());
    expect(applied).toEqual({ policySlot: null });
  });
});

describe("mapPolicyCardToDraft: guards against applying an unavailable route", () => {
  it("throws rather than silently applying a null template", () => {
    const route = budgetRoute({ available: false, template: null });
    const card = baseCard({ available: false, routes: [route] });
    expect(() => mapPolicyCardToDraft(card, route)).toThrow(/not available/);
  });
});
