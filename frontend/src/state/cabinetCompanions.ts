/**
 * Cabinet draft orders, and the one function that keeps a transfer coherent.
 *
 * A transfer -- moving somebody from one cabinet post to another -- is irreducibly TWO orders: the
 * destination gets the person, and the post they leave gets emptied. Only one of those is something
 * the player asked for. The other is a consequence the interface inferred, and the two must stay
 * distinguishable, or cancelling a transfer would erase a dismissal the player staged deliberately.
 *
 * So an order records its own provenance, and `reconcileCompanions` -- pure, total and idempotent --
 * re-establishes every companion invariant after each mutation. Store actions therefore mutate
 * naively and reconcile, rather than each one remembering the rules for itself.
 *
 * None of this reaches the server. `buildDecisionSet.ts` strips all three UI-only fields; the wire
 * format is `{post, character_id}` and nothing else.
 */

/** Where an order came from. `generated` is the interface's inference, never a player instruction. */
export type CabinetOrderOrigin = "explicit" | "generated";

export interface CabinetOrderDraft {
  /** The appointee, or `null` for a dismissal. */
  characterId: string | null;
  origin: CabinetOrderOrigin;
  /**
   * `generated` only: the DESTINATION post of the transfer that produced this companion.
   *
   * A link rather than a flag, so cancelling one transfer removes its own companion and no other --
   * with two transfers in flight, "is there a generated dismissal?" would not be a useful question.
   */
  generatedBy?: string;
  /**
   * `explicit` only: the post this appointment moves the appointee OUT of.
   *
   * Present exactly when the order is a transfer, which is what makes the draft self-describing:
   * the set of live transfers is derivable from the record alone, with no second lookup into a
   * server response. That is the whole reason reconciliation can be a pure function of the draft.
   */
  requiresVacatingPost?: string;
}

/** post value -> that post's staged order. An absent key is no order for that post. */
export type CabinetOrders = Record<string, CabinetOrderDraft>;

/** Every live transfer in `orders`, as destination post -> origin post. */
function liveTransfers(orders: CabinetOrders): Map<string, string> {
  const transfers = new Map<string, string>();
  for (const [post, order] of Object.entries(orders)) {
    if (order.origin === "explicit" && order.requiresVacatingPost !== undefined) {
      transfers.set(post, order.requiresVacatingPost);
    }
  }
  return transfers;
}

/**
 * A generated entry is valid only when its link is BOTH real and consistent: `generatedBy` names a
 * live explicit transfer, AND that transfer vacates this very post. The second half matters --
 * a companion left over from a transfer that has since been re-pointed at a different origin is
 * mismatched, not merely stale, and keeping it would empty a post no transfer is leaving.
 */
function companionIsValid(post: string, order: CabinetOrderDraft, transfers: Map<string, string>): boolean {
  if (order.generatedBy === undefined) {
    return false;
  }
  return transfers.get(order.generatedBy) === post;
}

/**
 * Return `orders` with every companion invariant restored.
 *
 * PURE: the argument is never mutated, and every entry in the result is either the identical object
 * from the input or a freshly created companion. TOTAL: defined on any record, including malformed
 * ones a future bug might produce. IDEMPOTENT: reconciling a reconciled record changes nothing --
 * which is the property that lets store actions call it unconditionally.
 *
 * Four steps, in this order:
 *
 *   1. Find the live transfers.
 *   2. Drop every generated entry that is orphaned or mismatched (see `companionIsValid`).
 *   3. Create or RESTORE a companion for each live transfer whose origin now has no order. The
 *      restore case is the one a rules-in-each-action design misses: a player who edits a companion
 *      into a real appointment and then removes that appointment would otherwise be left with a
 *      transfer that seats one person in two posts.
 *   4. Never overwrite an explicit order -- step 3 fills empty slots only.
 *
 * The two-way swap needs no special case and gets none. Two explicit transfers pointing at each
 * other occupy both origins, so step 3 creates nothing; cancel either side and the remaining
 * transfer's origin is empty again, so its companion appears.
 */
export function reconcileCompanions(orders: CabinetOrders): CabinetOrders {
  const transfers = liveTransfers(orders);
  const result: CabinetOrders = {};

  for (const [post, order] of Object.entries(orders)) {
    if (order.origin === "generated" && !companionIsValid(post, order, transfers)) {
      continue;
    }
    result[post] = order;
  }

  for (const [destination, origin] of transfers) {
    if (result[origin] === undefined) {
      result[origin] = { characterId: null, origin: "generated", generatedBy: destination };
    }
  }

  return result;
}
