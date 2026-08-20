/**
 * The ONE place a `DecisionSet` payload is assembled -- canonical order BY
 * CONSTRUCTION, never by sorting a payload after the fact and never relying
 * on the server to repair anything (frozen plan Sec 10.1, "canonical
 * ordering -- client-constructed, never server-normalized"). The engine's own
 * validators still reject a noncanonical or malformed payload with a 422
 * (`test_api_decisions.py`'s reject-not-normalize suite proves that end to
 * end); this function's job is to make sending one impossible from the UI,
 * not to catch it afterward.
 *
 * Reads `DraftState`'s free-form scratch shape and emits exactly what
 * `/api/game/resolve` and `/api/game/preview` accept: a `revision` echoed
 * unchanged, and a `decisions` array in canonical kind order
 * (`bloc_relationship_investment` < `budget` < `constitutional_amendment`,
 * alphabetical -- matches `DecisionSet._decisions_are_in_canonical_kind_order`
 * in `backend/app/simulation/decisions.py`), with every influence/investment
 * list sorted ascending by `(party_id, bloc_id)` and every amendment target
 * sorted ascending by axis name.
 */

import type { Decision } from "../api/client";
import type { AmendmentDraft, BudgetDraft, DraftState } from "./draft";

function sortedInfluence(record: Record<string, number>): { party_id: string; bloc_id: string; political_capital: number }[] {
  return Object.entries(record)
    .map(([key, politicalCapital]) => {
      const [partyId, blocId] = key.split("/");
      return { party_id: partyId ?? "", bloc_id: blocId ?? "", political_capital: politicalCapital };
    })
    .sort((a, b) => (a.party_id === b.party_id ? a.bloc_id.localeCompare(b.bloc_id) : a.party_id.localeCompare(b.party_id)));
}

function buildBudgetDecision(draft: BudgetDraft): Decision | null {
  const spendingUpdates = Object.entries(draft.spendingUpdates).map(([category, amount]) => ({
    category,
    amount,
  }));
  const hasRateTarget =
    draft.personalIncomeRateBps !== undefined ||
    draft.corporateRateBps !== undefined ||
    draft.consumptionRateBps !== undefined;
  if (!hasRateTarget && spendingUpdates.length === 0) {
    // Omission of empty optional decisions: an untouched budget draft is not
    // "a budget decision that changes nothing," it is the absence of one.
    return null;
  }
  const decision: Record<string, unknown> = {
    kind: "budget",
    route: draft.route,
  };
  if (draft.personalIncomeRateBps !== undefined) {
    decision["personal_income_rate_bps"] = draft.personalIncomeRateBps;
  }
  if (draft.corporateRateBps !== undefined) {
    decision["corporate_rate_bps"] = draft.corporateRateBps;
  }
  if (draft.consumptionRateBps !== undefined) {
    decision["consumption_rate_bps"] = draft.consumptionRateBps;
  }
  if (spendingUpdates.length > 0) {
    decision["spending_updates"] = spendingUpdates;
  }
  // A decree route takes no influence -- omitting an empty array here (rather
  // than sending `influence: []`) matches the same "omit what was not set"
  // discipline the rest of this builder follows.
  if (draft.route === "legislative") {
    const influence = sortedInfluence(draft.influence);
    if (influence.length > 0) {
      decision["influence"] = influence;
    }
  }
  return decision;
}

function buildAmendmentDecision(draft: AmendmentDraft): Decision | null {
  const targets = Object.entries(draft.targets)
    .map(([axis, value]) => ({ axis, value }))
    .sort((a, b) => a.axis.localeCompare(b.axis));
  if (targets.length === 0) {
    return null;
  }
  const decision: Record<string, unknown> = {
    kind: "constitutional_amendment",
    targets,
    route: draft.route,
  };
  if (draft.route === "legislative") {
    const influence = sortedInfluence(draft.influence);
    if (influence.length > 0) {
      decision["influence"] = influence;
    }
  }
  return decision;
}

function buildInvestmentDecision(investments: Record<string, number>): Decision | null {
  const rows = sortedInfluence(investments);
  if (rows.length === 0) {
    return null;
  }
  return {
    kind: "bloc_relationship_investment",
    investments: rows.map((row) => ({
      party_id: row.party_id,
      bloc_id: row.bloc_id,
      political_capital: row.political_capital,
    })),
  };
}

/** Builds the canonically-ordered `decisions` array for the current draft.
 * `policySlot` selects which of budget/amendment (if either) contributes --
 * the two are mutually exclusive by construction here, matching the engine's
 * own `_at_most_one_policy_proposal` rule, which this can therefore never
 * violate rather than merely being expected not to. */
export function buildDecisions(draft: DraftState): Decision[] {
  const decisions: Decision[] = [];

  const investment = buildInvestmentDecision(draft.investments);
  if (investment !== null) {
    decisions.push(investment); // "bloc_relationship_investment" sorts first
  }

  if (draft.policySlot === "budget") {
    const budget = buildBudgetDecision(draft.budget);
    if (budget !== null) {
      decisions.push(budget); // "budget" sorts second
    }
  } else if (draft.policySlot === "amendment") {
    const amendment = buildAmendmentDecision(draft.amendment);
    if (amendment !== null) {
      decisions.push(amendment); // "constitutional_amendment" sorts third
    }
  }

  return decisions;
}
