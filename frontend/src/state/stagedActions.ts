/**
 * Gate 4A3 UX-4b (U8) — the ONE definition of "what the player has staged this turn".
 *
 * Three surfaces state it: the nav's "· N staged", Decisions' "This turn's draft" list, and the
 * resolve confirmation. They used to disagree -- the confirmation counted `buildDecisions(draft)`,
 * i.e. wire DECISIONS (two cabinet changes are one `cabinet` decision; three investments are one
 * `bloc_relationship_investment`), and nothing else counted at all. Now all three read this list.
 *
 * It counts PLAYER ACTIONS, and only ones that will actually be SUBMITTED:
 *
 *   - the policy proposal, exactly when `policyProposalDecision` (the builder's own rule) would send
 *     one. An untouched budget, a target-less amendment, either of those with influence or a decree
 *     route, and "no major action" all count ZERO -- none of them reaches the wire;
 *   - each EXPLICIT cabinet order. A transfer's generated companion (the post it vacates) is a real
 *     order on the wire but not a player action, so it is attached to its transfer as a consequence
 *     rather than counted;
 *   - each relationship-investment row (each is its own choice of bloc and amount);
 *   - the bargain, the assistance request, the promise, and the movement order.
 *
 * `buildDecisions` stays the wire format; this never feeds it.
 */

import { policyProposalDecision } from "./buildDecisionSet";
import type { DraftState, PolicySlotKind, PromiseDraft } from "./draft";

export type StagedAction =
  | { kind: "proposal"; slot: PolicySlotKind }
  | {
      kind: "cabinet";
      post: string;
      characterId: string | null;
      /** The generated orders this transfer causes -- shown under it, never counted. */
      consequences: { post: string; characterId: string | null }[];
    }
  | { kind: "investment"; partyId: string; blocId: string; politicalCapital: number }
  | { kind: "bargain"; characterId: string; proposalKind: PolicySlotKind }
  | { kind: "assistance"; profileId: string }
  | { kind: "promise"; promise: PromiseDraft }
  | { kind: "movement"; formationId: string; destinationTheaterId: string };

type StagedInputs = Pick<
  DraftState,
  | "policySlot"
  | "budget"
  | "amendment"
  | "investments"
  | "cabinetOrders"
  | "bargain"
  | "assistance"
  | "promise"
  | "movement"
>;

export function stagedActions(draft: StagedInputs): StagedAction[] {
  const actions: StagedAction[] = [];

  if (draft.policySlot !== null && policyProposalDecision(draft) !== null) {
    actions.push({ kind: "proposal", slot: draft.policySlot });
  }

  const posts = Object.keys(draft.cabinetOrders).sort((a, b) => a.localeCompare(b));
  for (const post of posts) {
    const order = draft.cabinetOrders[post];
    if (order === undefined || order.origin !== "explicit") continue;
    const consequences = posts
      .filter((other) => draft.cabinetOrders[other]?.generatedBy === post)
      .map((other) => ({ post: other, characterId: draft.cabinetOrders[other]?.characterId ?? null }));
    actions.push({ kind: "cabinet", post, characterId: order.characterId, consequences });
  }

  for (const key of Object.keys(draft.investments).sort((a, b) => a.localeCompare(b))) {
    const [partyId = "", blocId = ""] = key.split("/");
    actions.push({ kind: "investment", partyId, blocId, politicalCapital: draft.investments[key] ?? 0 });
  }

  if (draft.bargain !== null) {
    actions.push({ kind: "bargain", ...draft.bargain });
  }
  if (draft.assistance !== null) {
    actions.push({ kind: "assistance", profileId: draft.assistance.profileId });
  }
  if (draft.promise !== null) {
    actions.push({ kind: "promise", promise: draft.promise });
  }
  if (draft.movement !== null) {
    actions.push({ kind: "movement", ...draft.movement });
  }

  return actions;
}
