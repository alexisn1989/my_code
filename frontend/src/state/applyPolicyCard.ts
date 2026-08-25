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
