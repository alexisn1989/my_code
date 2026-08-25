/**
 * Gate 4A3A — proves the two-level grouping never drops a card, always
 * produces exactly three level-1 majors, and derives the four constitutional
 * families correctly from real card_id prefixes (the same prefixes
 * policy_cards.py's generators emit).
 */

import { describe, expect, it } from "vitest";

import type { PolicyCard } from "../../api/client";
import { groupPolicyCards, locateCard } from "./groupPolicyCards";

function card(id: string, category: PolicyCard["category"]): PolicyCard {
  return {
    card_id: id,
    category,
    category_label: category,
    title: id,
    description: id,
    available: true,
    clears_proposal_slot: category === "restraint",
    effects: [],
    routes: [],
  };
}

const SAMPLE_CARDS: PolicyCard[] = [
  card("tax_personal_income_increase", "taxation"),
  card("tax_personal_income_decrease", "taxation"),
  card("spending_health_increase", "spending"),
  card("spending_health_decrease", "spending"),
  card("constitution_decree_authority_to_unlimited", "constitution"),
  card("constitution_government_form_presidential_appointed", "constitution"),
  card("constitution_term_limit_to_none", "constitution"),
  card("constitution_election_interval_to_8", "constitution"),
  card("no_proposal", "restraint"),
];

describe("groupPolicyCards", () => {
  it("produces exactly the three level-1 majors, in order", () => {
    const majors = groupPolicyCards(SAMPLE_CARDS);
    expect(majors.map((major) => major.id)).toEqual(["budget", "constitution", "restraint"]);
  });

  it("drops no card: every input card appears in exactly one output bucket", () => {
    const majors = groupPolicyCards(SAMPLE_CARDS);
    const seen = majors.flatMap((major) => major.cards).map((c) => c.card_id);
    expect(seen.sort()).toEqual(SAMPLE_CARDS.map((c) => c.card_id).sort());
  });

  it("groups taxation and spending cards under the budget major", () => {
    const majors = groupPolicyCards(SAMPLE_CARDS);
    const budget = majors.find((major) => major.id === "budget")!;
    expect(budget.families.map((family) => family.id)).toEqual(["taxation", "spending"]);
    expect(budget.families[0]!.cards).toHaveLength(2);
    expect(budget.families[1]!.cards).toHaveLength(2);
  });

  it("derives the four constitutional families from card_id prefixes, in the documented order", () => {
    const majors = groupPolicyCards(SAMPLE_CARDS);
    const constitution = majors.find((major) => major.id === "constitution")!;
    expect(constitution.families.map((family) => family.id)).toEqual([
      "decree_authority",
      "government_form",
      "term_limit",
      "election_interval",
    ]);
    for (const family of constitution.families) {
      expect(family.cards).toHaveLength(1);
    }
  });

  it("omits an empty family entirely rather than emitting a zero-card tab", () => {
    const noTermLimitCards = SAMPLE_CARDS.filter(
      (c) => !c.card_id.startsWith("constitution_term_limit_"),
    );
    const majors = groupPolicyCards(noTermLimitCards);
    const constitution = majors.find((major) => major.id === "constitution")!;
    expect(constitution.families.map((family) => family.id)).not.toContain("term_limit");
  });

  it("puts the single restraint card directly under its major with no families", () => {
    const majors = groupPolicyCards(SAMPLE_CARDS);
    const restraint = majors.find((major) => major.id === "restraint")!;
    expect(restraint.families).toEqual([]);
    expect(restraint.cards.map((c) => c.card_id)).toEqual(["no_proposal"]);
  });

  it("throws on an unrecognized constitutional card_id prefix rather than silently misfiling it", () => {
    const bogus = [...SAMPLE_CARDS, card("constitution_something_new", "constitution")];
    expect(() => groupPolicyCards(bogus)).toThrow(/unrecognized/);
  });
});

describe("locateCard", () => {
  it("finds a budget-family card's major and family", () => {
    const majors = groupPolicyCards(SAMPLE_CARDS);
    expect(locateCard(majors, "spending_health_increase")).toEqual({
      major: "budget",
      family: "spending",
    });
  });

  it("finds a constitution-family card's major and family", () => {
    const majors = groupPolicyCards(SAMPLE_CARDS);
    expect(locateCard(majors, "constitution_term_limit_to_none")).toEqual({
      major: "constitution",
      family: "term_limit",
    });
  });

  it("finds the restraint card with a null family", () => {
    const majors = groupPolicyCards(SAMPLE_CARDS);
    expect(locateCard(majors, "no_proposal")).toEqual({ major: "restraint", family: null });
  });

  it("returns null for a card id that is not present", () => {
    const majors = groupPolicyCards(SAMPLE_CARDS);
    expect(locateCard(majors, "does_not_exist")).toBeNull();
  });
});
