/**
 * Template -> draft mapping ONLY (Gate 4A3A). Selecting a card populates the
 * draft; it never previews, resolves, or spends -- this module has no
 * knowledge of `useDraftStore`, React Query, or any endpoint. It reads one
 * `PolicyCardRoute.template` -- a real, server-authored, canonical
 * `BudgetDecision` or `ConstitutionalAmendmentDecision` -- and produces the
 * plain `AppliedCard` data `draft.ts`'s `applyCard` action uses to replace
 * the relevant slot wholesale.
 *
 * No arithmetic here: every raw field is copied through unchanged, never
 * summed, scaled, or reformatted (that boundary belongs to `src/format/**`).
 */

import type { BudgetDecision, ConstitutionalAmendmentDecision, PolicyCard, PolicyCardRoute } from "../api/client";
import type { AppliedAmendmentFields, AppliedBudgetFields, AppliedCard } from "./draft";

function mapBudgetTemplate(template: BudgetDecision): AppliedBudgetFields {
  const spendingUpdates: Record<string, number> = {};
  for (const update of template.spending_updates ?? []) {
    spendingUpdates[update.category] = update.amount;
  }
  return {
    personalIncomeRateBps: template.personal_income_rate_bps ?? undefined,
    corporateRateBps: template.corporate_rate_bps ?? undefined,
    consumptionRateBps: template.consumption_rate_bps ?? undefined,
    spendingUpdates,
    route: template.route,
  };
}

function mapAmendmentTemplate(template: ConstitutionalAmendmentDecision): AppliedAmendmentFields {
  const targets: Record<string, string | number | null> = {};
  for (const target of template.targets) {
    targets[target.axis] = target.value;
  }
  return { targets, route: template.route };
}

/**
 * `route` must be one of `card.routes` and must be `available` (its
 * `template` non-null) -- selecting an unavailable route is a caller bug the
 * card browser must not allow to reach here (its "Select" button is disabled
 * for an unavailable route).
 */
export function mapPolicyCardToDraft(card: PolicyCard, route: PolicyCardRoute): AppliedCard {
  if (card.clears_proposal_slot) {
    return { policySlot: null };
  }
  const template = route.template;
  if (!route.available || template == null) {
    throw new Error(
      `cannot apply route ${route.route} of card ${card.card_id}: route is not available`,
    );
  }
  if (template.kind === "budget") {
    return { policySlot: "budget", budget: mapBudgetTemplate(template) };
  }
  return { policySlot: "amendment", amendment: mapAmendmentTemplate(template) };
}

export interface ChosenCardRoute {
  route: PolicyCardRoute;
  /** True iff `priorRoute` was set but this card does not offer it
   * available, so a DIFFERENT route (the card's first available one) had to
   * be chosen instead -- the caller's cue to announce the change (R5). */
  changed: boolean;
}

/**
 * R5's route-preservation rule, as one pure, independently testable
 * decision: "preserve the selected route only if the new card declares that
 * route available; otherwise select the card's first available route and
 * announce why the route changed." `priorRoute` is `null` when there was no
 * previous selection (a fresh pick, or the prior selection was the
 * no-proposal card) -- in that case the card's first available route is
 * chosen with no announcement, since nothing was actually preserved or lost.
 *
 * Returns `null` only for a card with no available route at all, which the
 * card browser's disabled Select button should already prevent reaching
 * here -- defensive, not a path any test expects to exercise via the UI.
 */
export function chooseCardRoute(
  card: PolicyCard,
  priorRoute: "legislative" | "decree" | null,
): ChosenCardRoute | null {
  const available = card.routes.filter((route) => route.available);
  if (available.length === 0) {
    return null;
  }
  if (priorRoute !== null) {
    const preserved = available.find((route) => route.route === priorRoute);
    if (preserved) {
      return { route: preserved, changed: false };
    }
    return { route: available[0]!, changed: true };
  }
  return { route: available[0]!, changed: false };
}
