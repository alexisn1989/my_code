/**
 * Zustand: the decision DRAFT and UI preferences only -- never authoritative
 * server state (mandate: "Never copy authoritative server state into
 * Zustand"). React Query owns everything that came from the server; this
 * store owns everything the player is still deciding.
 *
 * Nothing here is canonically ordered. `buildDecisionSet.ts` reads this
 * store's plain object shape and is the ONLY place that assembles it into
 * the canonically-ordered payload the server actually receives -- this store
 * is free-form scratch state, not a pre-validated request.
 */

import { create } from "zustand";

import type { components } from "../api/schema";

import { reconcileCompanions, type CabinetOrders } from "./cabinetCompanions";

export type PolicySlotKind = "budget" | "amendment";
export type ProposalRoute = "legislative" | "decree";

export interface BudgetDraft {
  personalIncomeRateBps?: number;
  corporateRateBps?: number;
  consumptionRateBps?: number;
  /** category -> target amount. Only categories the player actually touched. */
  spendingUpdates: Record<string, number>;
  route: ProposalRoute;
  /** (partyId, blocId) -> political capital allocated. */
  influence: Record<string, number>;
}

export interface AmendmentDraft {
  /** axis -> target value (string | number | null). Only axes the player
   * actually touched -- an axis the player never opened is not "set to its
   * current value," it is simply absent from the draft. */
  targets: Record<string, string | number | null>;
  route: ProposalRoute;
  influence: Record<string, number>;
}

/** The fields a selected policy card's template supplies (Gate 4A3A) --
 * everything EXCEPT influence, which a fresh card selection always clears
 * (R5: "clear all influence allocations; they belong to the replaced
 * proposal"). `applyPolicyCard.ts` is the only place that constructs one of
 * these, from a real `PolicyCardRoute.template`. */
export interface AppliedBudgetFields {
  personalIncomeRateBps?: number;
  corporateRateBps?: number;
  consumptionRateBps?: number;
  spendingUpdates: Record<string, number>;
  route: ProposalRoute;
}

export interface AppliedAmendmentFields {
  targets: Record<string, string | number | null>;
  route: ProposalRoute;
}

export interface AppliedCard {
  policySlot: PolicySlotKind | null;
  budget?: AppliedBudgetFields;
  amendment?: AppliedAmendmentFields;
}

/** A bargain staged for a proposal kind the draft no longer carries.
 *
 * The engine binds a bargain to the proposal KIND (never to a digest -- a deliberate Commit 5
 * decision, so the client never has to reproduce canonical-JSON encoding), and slot 1 refuses the
 * whole set with `legislative_bargain_proposal_absent` when no proposal of that kind is present.
 * So a player who stages a budget bargain and then clears the proposal, or switches to an
 * amendment, would be holding a draft that CANNOT preview.
 *
 * ONE function, called by both mutators that can change the slot, because two copies of this rule
 * would be two chances to forget it. Retention on a same-kind replacement is the interesting half:
 * swapping one budget for another keeps the bargain, precisely because the binding is by kind.
 */
export function bargainAfterPolicySlotChange(
  bargain: DraftState["bargain"],
  nextSlot: PolicySlotKind | null,
): DraftState["bargain"] {
  if (bargain === null) {
    return null;
  }
  return bargain.proposalKind === nextSlot ? bargain : null;
}

/** A bargain staged for a proposal that is now being DECREED rather than put to the chamber.
 *
 * The same class of defect as the slot change above, one level down. A bargain buys support in a
 * chamber vote, and the engine refuses the whole set with
 * `legislative_bargain_requires_legislative_route` when the proposal it names takes the decree
 * route -- so a player who stages a bargain and then switches the route would again be holding a
 * draft that CANNOT preview.
 *
 * Clearing is the right answer rather than silently dropping the bargain at submission: dropping it
 * would resolve a turn WITHOUT the bargain the player asked for and report no error at all, which
 * is worse than losing a staging they can redo in one click. The meeting panel's own copy explains
 * why a decreed proposal has no support to buy.
 *
 * `slot` is the proposal whose route just moved. A bargain staged for the other kind is untouched,
 * which cannot arise today (the slot rule keeps the bargain's kind equal to the current slot) and
 * is guarded anyway so the two rules compose rather than depend on each other.
 */
export function bargainAfterRouteChange(
  bargain: DraftState["bargain"],
  slot: PolicySlotKind,
  nextRoute: ProposalRoute,
): DraftState["bargain"] {
  if (bargain === null || bargain.proposalKind !== slot) {
    return bargain;
  }
  return nextRoute === "decree" ? null : bargain;
}

/** The one promise staged this turn. Mirrors `PromiseDecision`'s exclusive shape. */
/** The GENERATED property type, never a hand-written union: a bare `string` would permit
 * drafts the server can never accept, and re-spelling the three members here would duplicate
 * server vocabulary client-side. */
type PromiseTermKind = components["schemas"]["PromiseOption"]["term_kind"];

export type PromiseDraft =
  | {
      readonly action: "make";
      readonly characterId: string;
      readonly termKind: PromiseTermKind;
      readonly subjectId: string;
      readonly deadlineTurn: number;
    }
  | { readonly action: "release"; readonly characterId: string; readonly promiseId: string };

export interface DraftState {
  /** The one mutually-exclusive policy-proposal slot. `null` means no
   * proposal this turn -- a legal, first-class choice, not an unset value. */
  policySlot: PolicySlotKind | null;
  budget: BudgetDraft;
  amendment: AmendmentDraft;
  /** Relationship investment is its own, non-exclusive slot: (partyId,
   * blocId) -> political capital. */
  investments: Record<string, number>;
  /** The one movement order staged for this turn, or `null` for none.
   *
   * Another separate, non-exclusive slot -- movement never interacts with the budget/amendment
   * exclusivity. Nullable rather than a list because ruleset 0.15.0 accepts one order per turn,
   * and because staging a second REPLACES the first (see `setMovementOrder`), which makes the cap
   * unreachable from the interface rather than merely refused by the server. */
  movement: { formationId: string; destinationTheaterId: string } | null;
  /** Cabinet orders staged for this turn, keyed by post value.
   *
   * A record rather than a single nullable order, because a TRANSFER is irreducibly two orders and
   * they are written independently -- see `cabinetCompanions.ts`, which owns the rules that keep
   * the two coherent. Every action below mutates naively and then reconciles, so no action carries
   * a copy of those rules.
   *
   * Only ever changed by a CONFIRMED action. Browsing candidates, selecting one, and cancelling
   * before confirming are component state on the screen and never reach here. */
  cabinetOrders: CabinetOrders;
  /** The one legislative bargain staged this turn, or `null`.
   *
   * A SINGLETON, not a record like `cabinetOrders`: the engine caps this at one per `DecisionSet`
   * (`_at_most_one_legislative_bargain_decision`), so a second staging REPLACES the first -- the
   * wholesale-replacement rule `setMovementOrder` documents. No companion reconciliation, because
   * a bargain is never irreducibly two orders.
   *
   * It DOES need CROSS-SLOT reconciliation, which is a different thing: a bargain names a
   * `proposalKind`, and slot 1 refuses the set with `legislative_bargain_proposal_absent` when the
   * set carries no proposal of that kind. See `setPolicySlot`/`applyCard`. */
  bargain: { characterId: string; proposalKind: PolicySlotKind } | null;
  /** The one assistance request staged this turn, or `null`. Capped at one per set by the engine,
   * and coupled to nothing else in the draft. */
  assistance: { profileId: string } | null;
  /** The one promise staged this turn, or `null`.
   *
   * A discriminated union rather than a bag of optionals, mirroring `PromiseDecision`'s own
   * exclusive shape: a `make` carrying a `promiseId`, or a `release` carrying a deadline, is
   * unconstructible on this side too. */
  promise: PromiseDraft | null;

  dismissedHelp: boolean;
  glossaryOpen: boolean;

  setPolicySlot: (slot: PolicySlotKind | null) => void;
  /** Selecting a policy card (Gate 4A3A): replaces the relevant slot WHOLESALE
   * from `applyPolicyCard.ts`'s mapping -- no stale field survives a card
   * switch, and the incompatible slot is reset to empty, not merged. Never
   * previews, resolves, or spends; it only changes what the next Preview/
   * Resolve call would submit. */
  applyCard: (applied: AppliedCard) => void;
  setBudgetRateTarget: (
    field: "personalIncomeRateBps" | "corporateRateBps" | "consumptionRateBps",
    valueBps: number | undefined,
  ) => void;
  setBudgetSpendingTarget: (category: string, amount: number | undefined) => void;
  setBudgetRoute: (route: ProposalRoute) => void;
  setBudgetInfluence: (partyId: string, blocId: string, politicalCapital: number | undefined) => void;
  setAmendmentTarget: (axis: string, value: string | number | null | undefined) => void;
  setAmendmentRoute: (route: ProposalRoute) => void;
  setAmendmentInfluence: (
    partyId: string,
    blocId: string,
    politicalCapital: number | undefined,
  ) => void;
  setInvestment: (partyId: string, blocId: string, politicalCapital: number | undefined) => void;
  /** Stage a movement order, REPLACING any order already staged.
   *
   * Wholesale replacement mirrors `applyCard`'s documented rule for the policy slot: no stale
   * field survives a switch. Staging an order for a second formation therefore supersedes the
   * first rather than accumulating one the server would reject. */
  setMovementOrder: (formationId: string, destinationTheaterId: string) => void;
  clearMovementOrder: () => void;
  /** Stage a bargain, REPLACING any bargain already staged. */
  setBargain: (characterId: string, proposalKind: PolicySlotKind) => void;
  clearBargain: () => void;
  /** Stage an assistance request, REPLACING any already staged. */
  setAssistanceRequest: (profileId: string) => void;
  clearAssistanceRequest: () => void;
  /** Stage a promise, REPLACING any already staged. */
  setPromise: (promise: PromiseDraft) => void;
  clearPromise: () => void;
  /** Appoint (or replace) somebody, explicitly.
   *
   * `requiresVacatingPost` is passed by the caller from the candidate's own projected row and is
   * stored on the order, which is what makes this entry recognisable as a transfer later. Also the
   * path that PROMOTES a generated companion: writing here makes the post's order explicit, so a
   * later cancellation of the transfer can no longer remove it. */
  confirmAppointment: (post: string, characterId: string, requiresVacatingPost?: string) => void;
  /** Dismiss the holder of one post, explicitly. Promotes a companion for the same reason. */
  confirmDismissal: (post: string) => void;
  /** Remove one post's order. Reconciliation then drops the companion of a transfer this
   * cancelled, and restores the companion of any transfer this left with an empty origin. */
  cancelCabinetOrder: (post: string) => void;
  /** Clears every draft field. Called ONLY after a successful resolve
   * (mandate: "Clear the committed draft only after success"). */
  clearDraft: () => void;
  dismissHelp: () => void;
  setGlossaryOpen: (open: boolean) => void;
}

function influenceKey(partyId: string, blocId: string): string {
  return `${partyId}/${blocId}`;
}

function withEntry(
  record: Record<string, number>,
  key: string,
  value: number | undefined,
): Record<string, number> {
  if (value === undefined) {
    const { [key]: _removed, ...rest } = record;
    return rest;
  }
  return { ...record, [key]: value };
}

const EMPTY_BUDGET: BudgetDraft = {
  spendingUpdates: {},
  route: "legislative",
  influence: {},
};

const EMPTY_AMENDMENT: AmendmentDraft = {
  targets: {},
  route: "legislative",
  influence: {},
};

export const useDraftStore = create<DraftState>((set) => ({
  policySlot: null,
  budget: EMPTY_BUDGET,
  amendment: EMPTY_AMENDMENT,
  investments: {},
  movement: null,
  cabinetOrders: {},
  bargain: null,
  assistance: null,
  promise: null,
  dismissedHelp: false,
  glossaryOpen: false,

  setPolicySlot: (slot) =>
    set((state) => ({
      policySlot: slot,
      // ATOMIC: the bargain clears in the same update that changes the slot, so no render ever
      // observes a draft whose bargain names a proposal the draft does not carry.
      bargain: bargainAfterPolicySlotChange(state.bargain, slot),
    })),

  applyCard: (applied) =>
    set((state) => ({
      bargain: bargainAfterPolicySlotChange(state.bargain, applied.policySlot),
      policySlot: applied.policySlot,
      budget: applied.budget ? { ...EMPTY_BUDGET, ...applied.budget } : EMPTY_BUDGET,
      amendment: applied.amendment
        ? { ...EMPTY_AMENDMENT, ...applied.amendment }
        : EMPTY_AMENDMENT,
    })),

  setBudgetRateTarget: (field, valueBps) =>
    set((state) => ({
      budget: { ...state.budget, [field]: valueBps },
    })),

  setBudgetSpendingTarget: (category, amount) =>
    set((state) => {
      const spendingUpdates = { ...state.budget.spendingUpdates };
      if (amount === undefined) {
        delete spendingUpdates[category];
      } else {
        spendingUpdates[category] = amount;
      }
      return { budget: { ...state.budget, spendingUpdates } };
    }),

  setBudgetRoute: (route) =>
    set((state) => ({
      budget: { ...state.budget, route },
      // ATOMIC, exactly as the slot change is: no render observes a draft whose bargain names a
      // proposal that is about to be decreed.
      bargain: bargainAfterRouteChange(state.bargain, "budget", route),
    })),

  setBudgetInfluence: (partyId, blocId, politicalCapital) =>
    set((state) => ({
      budget: {
        ...state.budget,
        influence: withEntry(state.budget.influence, influenceKey(partyId, blocId), politicalCapital),
      },
    })),

  setAmendmentTarget: (axis, value) =>
    set((state) => {
      const targets = { ...state.amendment.targets };
      if (value === undefined) {
        delete targets[axis];
      } else {
        targets[axis] = value;
      }
      return { amendment: { ...state.amendment, targets } };
    }),

  setAmendmentRoute: (route) =>
    set((state) => ({
      amendment: { ...state.amendment, route },
      bargain: bargainAfterRouteChange(state.bargain, "amendment", route),
    })),

  setAmendmentInfluence: (partyId, blocId, politicalCapital) =>
    set((state) => ({
      amendment: {
        ...state.amendment,
        influence: withEntry(
          state.amendment.influence,
          influenceKey(partyId, blocId),
          politicalCapital,
        ),
      },
    })),

  setInvestment: (partyId, blocId, politicalCapital) =>
    set((state) => ({
      investments: withEntry(state.investments, influenceKey(partyId, blocId), politicalCapital),
    })),

  setMovementOrder: (formationId, destinationTheaterId) =>
    set({ movement: { formationId, destinationTheaterId } }),

  clearMovementOrder: () => set({ movement: null }),

  setBargain: (characterId, proposalKind) => set({ bargain: { characterId, proposalKind } }),
  clearBargain: () => set({ bargain: null }),
  setAssistanceRequest: (profileId) => set({ assistance: { profileId } }),
  clearAssistanceRequest: () => set({ assistance: null }),
  setPromise: (promise) => set({ promise }),
  clearPromise: () => set({ promise: null }),

  confirmAppointment: (post, characterId, requiresVacatingPost) =>
    set((state) => ({
      cabinetOrders: reconcileCompanions({
        ...state.cabinetOrders,
        [post]:
          requiresVacatingPost === undefined
            ? { characterId, origin: "explicit" }
            : { characterId, origin: "explicit", requiresVacatingPost },
      }),
    })),

  confirmDismissal: (post) =>
    set((state) => ({
      cabinetOrders: reconcileCompanions({
        ...state.cabinetOrders,
        [post]: { characterId: null, origin: "explicit" },
      }),
    })),

  cancelCabinetOrder: (post) =>
    set((state) => {
      const { [post]: _removed, ...rest } = state.cabinetOrders;
      return { cabinetOrders: reconcileCompanions(rest) };
    }),

  clearDraft: () =>
    set({
      policySlot: null,
      budget: EMPTY_BUDGET,
      amendment: EMPTY_AMENDMENT,
      investments: {},
      // Cleared with the rest of the draft, which is what stops a `formationId` from a previous
      // campaign -- an id that may not even exist in the new one -- from being submitted after a
      // New Game or Load.
      movement: null,
      // Cleared for exactly that reason too: a `characterId` from a previous campaign names
      // somebody the new one may not have.
      cabinetOrders: {},
      bargain: null,
      assistance: null,
      promise: null,
    }),

  dismissHelp: () => set({ dismissedHelp: true }),
  setGlossaryOpen: (open) => set({ glossaryOpen: open }),
}));
