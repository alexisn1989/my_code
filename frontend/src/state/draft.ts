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

export interface DraftState {
  /** The one mutually-exclusive policy-proposal slot. `null` means no
   * proposal this turn -- a legal, first-class choice, not an unset value. */
  policySlot: PolicySlotKind | null;
  budget: BudgetDraft;
  amendment: AmendmentDraft;
  /** Relationship investment is its own, non-exclusive slot: (partyId,
   * blocId) -> political capital. */
  investments: Record<string, number>;

  dismissedHelp: boolean;
  glossaryOpen: boolean;

  setPolicySlot: (slot: PolicySlotKind | null) => void;
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
  dismissedHelp: false,
  glossaryOpen: false,

  setPolicySlot: (slot) => set({ policySlot: slot }),

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

  setBudgetRoute: (route) => set((state) => ({ budget: { ...state.budget, route } })),

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

  setAmendmentRoute: (route) => set((state) => ({ amendment: { ...state.amendment, route } })),

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

  clearDraft: () =>
    set({
      policySlot: null,
      budget: EMPTY_BUDGET,
      amendment: EMPTY_AMENDMENT,
      investments: {},
    }),

  dismissHelp: () => set({ dismissedHelp: true }),
  setGlossaryOpen: (open) => set({ glossaryOpen: open }),
}));
