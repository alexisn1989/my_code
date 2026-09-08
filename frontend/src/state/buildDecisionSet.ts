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
 * (`bloc_relationship_investment` < `budget` < `cabinet` <
 * `constitutional_amendment` < `military_movement`, alphabetical -- matches
 * `DecisionSet._decisions_are_in_canonical_kind_order` in
 * `backend/app/simulation/decisions.py`), with every influence/investment
 * list sorted ascending by `(party_id, bloc_id)`, every amendment target
 * sorted ascending by axis name, and every cabinet order sorted ascending by
 * post.
 *
 * It is also where the cabinet draft's UI-only provenance STOPS. `origin`,
 * `generatedBy` and `requiresVacatingPost` exist so the interface can tell a
 * companion dismissal from one the player staged (see
 * `cabinetCompanions.ts`); none of it is a decision, and none of it is
 * emitted. A generated dismissal is still submitted -- it is a real order --
 * and what is dropped is only the record of why the interface added it.
 */

import type { Decision } from "../api/client";
import type { CabinetOrders } from "./cabinetCompanions";
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

function buildCabinetDecision(orders: CabinetOrders): Decision | null {
  const posts = Object.keys(orders).sort((a, b) => a.localeCompare(b));
  if (posts.length === 0) {
    return null;
  }
  return {
    kind: "cabinet",
    orders: posts.map((post) => {
      const order = orders[post];
      // `character_id` is OMITTED for a dismissal rather than sent as `null`, matching
      // `CabinetOrder`'s own default and this builder's "omit what was not set" discipline. The
      // three provenance fields are not read here at all, which is how they cannot leak.
      return order?.characterId == null
        ? { post }
        : { post, character_id: order.characterId };
    }),
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

  const cabinet = buildCabinetDecision(draft.cabinetOrders);

  if (draft.policySlot === "budget") {
    const budget = buildBudgetDecision(draft.budget);
    if (budget !== null) {
      decisions.push(budget); // "budget" sorts second
    }
  }

  if (cabinet !== null) {
    decisions.push(cabinet); // "cabinet" sorts third, after "budget"
  }

  if (draft.policySlot === "amendment") {
    const amendment = buildAmendmentDecision(draft.amendment);
    if (amendment !== null) {
      decisions.push(amendment); // "constitutional_amendment" sorts fourth
    }
  }

  if (draft.movement !== null) {
    decisions.push({
      kind: "military_movement",
      orders: [
        {
          formation_id: draft.movement.formationId,
          destination_theater_id: draft.movement.destinationTheaterId,
        },
      ],
    }); // "military_movement" sorts last of the five kinds
  }

  return decisions;
}

/**
 * A stable identity for "the exact request a preview was made against".
 *
 * A preview estimate describes ONE decision set at ONE revision of ONE campaign. Change any of
 * those three and the estimate no longer describes anything the player is about to submit -- so
 * the screen compares this signature at render time against the one it captured when it asked.
 *
 * Lives here rather than in the screen for two reasons, both enforced by tests: `JSON.stringify`
 * is banned in the rendering layer (`raw-data-boundary.test.ts`, scoped to `greybox/**`), and
 * building a string by concatenation is arithmetic the format boundary refuses outside
 * `src/format/**`. One `JSON.stringify` over a tuple is neither.
 *
 * Built from `buildDecisions` rather than from the raw draft on purpose: two drafts that produce
 * the same submitted payload ARE the same request, so a player who changes something and changes
 * it back keeps a preview that still honestly describes what they would send.
 */
export function previewRequestSignature(
  draft: DraftState,
  revision: string | null,
  campaignId: string | null,
): string {
  return JSON.stringify([revision, campaignId, buildDecisions(draft)]);
}
