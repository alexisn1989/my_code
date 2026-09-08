/**
 * Government — the cabinet, and the one place appointments are composed.
 *
 * This entry rendered `UnavailableScreen` for a reason `registry.tsx` states plainly: the API gave
 * only summary concern cards, never a per-institution breakdown, and inventing one client-side is
 * the exact failure Gate 4A2 exists to avoid. `DecisionOptionsProjection.cabinet_posts` removes
 * that reason FOR THE CABINET, so the cabinet becomes live and the rest of the government
 * breakdown keeps saying, honestly, that it is not available in this gate.
 *
 * STAGING, NOT RESOLVING. Nothing here changes the game. Confirming writes to the shared turn draft
 * exactly as the strategic map's movement panel does, and the turn is still previewed and resolved
 * from the Decisions screen -- so a cabinet order competes for political capital alongside every
 * other decision, which is the whole point of it costing any.
 *
 * SELECTION IS LOCAL. Browsing candidates, choosing one, and cancelling are component state and
 * never reach the store. Only Confirm does. That is what makes Cancel a real cancel rather than an
 * undo of something already committed, and what stops a player reading candidate traits from
 * silently invalidating a preview they already have.
 *
 * NO LEGALITY IS RE-IMPLEMENTED HERE. The screen renders `candidate_accepts_post` and
 * `refusal_code` as given. It does not weigh loyalty against legitimacy, does not price an
 * appointment, does not sum capital, and does not decide whether a draft is affordable or seats
 * one person twice -- the last two are `/preview`'s answers, on the Decisions screen. The only
 * client-side derivation is resolving a post VALUE to its label through the projected rows.
 */

import { useRef, useState } from "react";

import type { CabinetCandidateOption, CabinetPostOption } from "../../api/client";
import { useDecisionOptions } from "../../api/queries";
import {
  appointmentCostLine,
  appointmentStagedAnnouncement,
  becomesLine,
  cabinetOrderRemovedAnnouncement,
  candidateSelectedAnnouncement,
  dismissalStagedAnnouncement,
  dismissedLine,
  formatBpsPercent,
  keepsStagedOrderLine,
  leftVacantLine,
  postSelectedAnnouncement,
  refusalReasonText,
  transferStagedAnnouncement,
} from "../../format/format";
import { useSession } from "../../state/SessionContext";
import type { CabinetOrderDraft } from "../../state/cabinetCompanions";
import { useDraftStore } from "../../state/draft";
import { ErrorPanel } from "../../status/ErrorPanel";
import { EmptyNote, Panel } from "../components";
import type { ScreenProps } from "../registry";

/** The label for a post VALUE, resolved through the projected rows -- never by rewriting the
 * identifier. A value with no row is a contract bug, and showing the raw value would hide it. */
function postLabel(posts: readonly CabinetPostOption[], value: string | null | undefined): string {
  if (value === null || value === undefined) {
    return "";
  }
  return posts.find((post) => post.post === value)?.post_display_name ?? value;
}

function holderDescription(
  order: CabinetOrderDraft,
  candidateName: (characterId: string) => string,
): string {
  return order.characterId === null ? "left vacant" : candidateName(order.characterId);
}

export function CabinetScreen(_props: ScreenProps) {
  const { revision } = useSession();
  const options = useDecisionOptions(revision, { enabled: revision !== null });

  // LOCAL proposal state. Never written to the store; discarded on navigation, which is correct --
  // an unconfirmed proposal is not a decision.
  const [selectedPost, setSelectedPost] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [proposedDismissal, setProposedDismissal] = useState(false);
  const [announcement, setAnnouncement] = useState("");

  const cabinetOrders = useDraftStore((state) => state.cabinetOrders);
  const confirmAppointment = useDraftStore((state) => state.confirmAppointment);
  const confirmDismissal = useDraftStore((state) => state.confirmDismissal);
  const cancelCabinetOrder = useDraftStore((state) => state.cancelCabinetOrder);

  const candidatesHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const reviewHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const stagedSummaryRef = useRef<HTMLDivElement | null>(null);
  const postButtonRefs = useRef(new Map<string, HTMLButtonElement | null>());

  if (revision === null) {
    return (
      <div className="flex flex-col gap-6">
        <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
          Government
        </h2>
        <Panel title="Cabinet">
          <EmptyNote>Start or load a campaign to see the government.</EmptyNote>
        </Panel>
      </div>
    );
  }
  if (options.isPending) {
    return (
      <p role="status" className="text-sm text-parchment-200/80">
        Loading the government…
      </p>
    );
  }
  if (options.isError) {
    return <ErrorPanel error={options.error} onRefresh={() => options.refetch()} />;
  }

  const posts = options.data.cabinet_posts;
  const post = posts.find((row) => row.post === selectedPost) ?? null;
  const candidate =
    post?.candidates.find((row) => row.character_id === selectedCandidateId) ?? null;

  const state =
    post === null
      ? "idle"
      : candidate === null && !proposedDismissal
        ? "postSelected"
        : "candidateSelected";

  function candidateName(characterId: string): string {
    for (const row of posts) {
      const match = row.candidates.find((c) => c.character_id === characterId);
      if (match !== undefined) {
        return match.display_name;
      }
    }
    return characterId;
  }

  function clearProposal(): void {
    setSelectedCandidateId(null);
    setProposedDismissal(false);
  }

  function selectPost(value: string): void {
    setSelectedPost(value);
    clearProposal();
    const row = posts.find((p) => p.post === value);
    if (row !== undefined) {
      const available = row.candidates.filter((c) => c.candidate_accepts_post).length;
      setAnnouncement(postSelectedAnnouncement(row.post_display_name, available));
      window.setTimeout(() => candidatesHeadingRef.current?.focus(), 0);
    }
  }

  function selectCandidate(row: CabinetCandidateOption): void {
    setSelectedCandidateId(row.character_id);
    setProposedDismissal(false);
    if (post !== null) {
      setAnnouncement(candidateSelectedAnnouncement(row.display_name, post.post_display_name));
    }
    window.setTimeout(() => reviewHeadingRef.current?.focus(), 0);
  }

  function proposeDismissal(): void {
    setSelectedCandidateId(null);
    setProposedDismissal(true);
    window.setTimeout(() => reviewHeadingRef.current?.focus(), 0);
  }

  function backToPost(): void {
    clearProposal();
    window.setTimeout(() => candidatesHeadingRef.current?.focus(), 0);
  }

  function backToIdle(): void {
    const returning = selectedPost;
    setSelectedPost(null);
    clearProposal();
    if (returning !== null) {
      window.setTimeout(() => postButtonRefs.current.get(returning)?.focus(), 0);
    }
  }

  function escape(): void {
    if (state === "candidateSelected") {
      backToPost();
      return;
    }
    if (state === "postSelected") {
      backToIdle();
    }
  }

  function confirmProposal(): void {
    if (post === null) {
      return;
    }
    if (proposedDismissal) {
      confirmDismissal(post.post);
      setAnnouncement(
        dismissalStagedAnnouncement(post.holder_display_name ?? "", post.post_display_name),
      );
    } else if (candidate !== null) {
      const vacating = candidate.requires_vacating_post ?? undefined;
      confirmAppointment(post.post, candidate.character_id, vacating);
      setAnnouncement(
        vacating === undefined
          ? appointmentStagedAnnouncement(candidate.display_name, post.post_display_name)
          : transferStagedAnnouncement(
              candidate.display_name,
              post.post_display_name,
              postLabel(posts, vacating),
            ),
      );
    } else {
      return;
    }
    setSelectedPost(null);
    clearProposal();
    window.setTimeout(() => stagedSummaryRef.current?.focus(), 0);
  }

  function removeOrder(value: string): void {
    cancelCabinetOrder(value);
    setAnnouncement(cabinetOrderRemovedAnnouncement(postLabel(posts, value)));
  }

  /** Every post this confirmation would change, in words, computed from the local proposal against
   * the current draft. Nothing is listed that the confirm would not do, and the "keeps its staged
   * order" line is how a player sees that their own order was preserved rather than overwritten. */
  function reviewLines(): string[] {
    if (post === null) {
      return [];
    }
    if (proposedDismissal) {
      return [dismissedLine(post.holder_display_name ?? "", post.post_display_name)];
    }
    if (candidate === null) {
      return [];
    }
    const lines = [becomesLine(candidate.display_name, post.post_display_name)];
    const vacating = candidate.requires_vacating_post;
    if (vacating !== null && vacating !== undefined) {
      const existing = cabinetOrders[vacating];
      const vacatingName = postLabel(posts, vacating);
      lines.push(
        existing === undefined || existing.origin === "generated"
          ? leftVacantLine(vacatingName)
          : keepsStagedOrderLine(vacatingName, holderDescription(existing, candidateName)),
      );
    }
    lines.push(appointmentCostLine(candidate.appointment_cost));
    return lines;
  }

  const stagedPosts = Object.keys(cabinetOrders).sort((a, b) => a.localeCompare(b));

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Government
      </h2>

      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>

      <Panel title="Cabinet">
        <p className="mb-3 text-sm text-parchment-200/70">
          Appointments are staged into this turn's draft. Nobody takes office until the turn is
          resolved from the Decisions screen, where the cost is weighed against everything else.
        </p>

        <div
          data-testid="cabinet-panel"
          data-cabinet-state={state}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.stopPropagation();
              escape();
            }
          }}
        >
          <ul className="grid gap-4 sm:grid-cols-2">
            {posts.map((row) => {
              const order = cabinetOrders[row.post];
              return (
                <li key={row.post}>
                  <button
                    type="button"
                    ref={(node) => {
                      postButtonRefs.current.set(row.post, node);
                    }}
                    data-post-option={row.post}
                    aria-pressed={selectedPost === row.post}
                    onClick={() => selectPost(row.post)}
                    className="w-full rounded border border-navy-800 px-3 py-2 text-left text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500 aria-pressed:border-gold-500"
                  >
                    <span className="block text-parchment-100">{row.post_display_name}</span>
                    <span className="block text-xs text-parchment-200/70">
                      {row.holder_display_name === null
                        ? "Vacant"
                        : `Held by ${row.holder_display_name}`}
                    </span>
                    <span
                      data-post-status={row.post}
                      className="block text-xs text-parchment-200/70"
                    >
                      {order === undefined
                        ? "No order staged"
                        : order.characterId === null
                          ? "Order staged: left vacant"
                          : `Order staged: ${candidateName(order.characterId)}`}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>

          {post === null ? null : (
            <div className="mt-4 border-t border-navy-800 pt-4">
              <h3
                ref={candidatesHeadingRef}
                tabIndex={-1}
                data-testid="candidates-heading"
                className="text-sm uppercase tracking-[0.15em] text-parchment-100 focus:outline-none"
              >
                Candidates for {post.post_display_name}
              </h3>

              {post.can_dismiss ? (
                <button
                  type="button"
                  data-testid="propose-dismissal"
                  onClick={proposeDismissal}
                  className="mt-2 rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                >
                  Dismiss {post.holder_display_name}
                </button>
              ) : null}

              <ul className="mt-2 flex flex-col gap-1">
                {post.candidates.map((row) => {
                  const isIncumbent = row.currently_holds_post === post.post;
                  const transferFrom =
                    row.requires_vacating_post === null || row.requires_vacating_post === undefined
                      ? null
                      : postLabel(posts, row.requires_vacating_post);
                  if (isIncumbent) {
                    return (
                      <li key={row.character_id}>
                        <p
                          data-candidate-incumbent={row.character_id}
                          className="px-3 py-1 text-sm text-parchment-200/50"
                        >
                          {row.display_name} — already in post.
                        </p>
                      </li>
                    );
                  }
                  if (!row.candidate_accepts_post) {
                    return (
                      <li key={row.character_id}>
                        <p
                          data-candidate-refused={row.character_id}
                          className="px-3 py-1 text-sm text-parchment-200/50"
                        >
                          {row.display_name} — {refusalReasonText(row.refusal_code)}
                        </p>
                      </li>
                    );
                  }
                  return (
                    <li key={row.character_id}>
                      <button
                        type="button"
                        data-candidate-option={row.character_id}
                        aria-pressed={selectedCandidateId === row.character_id}
                        onClick={() => selectCandidate(row)}
                        className="w-full rounded border border-dashed border-gold-500 px-3 py-1 text-left text-sm text-parchment-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                      >
                        <span className="block">
                          {row.display_name} — {appointmentCostLine(row.appointment_cost)}
                        </span>
                        <span className="block text-xs text-parchment-200/70">
                          competence {formatBpsPercent(row.competence_bps)}, loyalty{" "}
                          {formatBpsPercent(row.loyalty_bps)}, independence{" "}
                          {formatBpsPercent(row.independence_bps)}, ambition{" "}
                          {formatBpsPercent(row.ambition_bps)}, trust{" "}
                          {formatBpsPercent(row.personal_trust_bps)}
                        </span>
                        {transferFrom === null ? null : (
                          <span
                            data-candidate-transfer={row.character_id}
                            className="block text-xs text-parchment-200/70"
                          >
                            Currently {transferFrom}; appointing them here also vacates that post.
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {state === "candidateSelected" ? (
            <div className="mt-4 rounded border border-gold-600 p-3">
              <h3
                ref={reviewHeadingRef}
                tabIndex={-1}
                data-testid="cabinet-review-heading"
                className="text-sm uppercase tracking-[0.15em] text-parchment-100 focus:outline-none"
              >
                Review this change
              </h3>
              <ul data-testid="cabinet-review-lines" className="mt-2 flex flex-col gap-1 text-sm">
                {reviewLines().map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <div className="mt-3 flex gap-3">
                <button
                  type="button"
                  data-testid="confirm-cabinet-order"
                  onClick={confirmProposal}
                  className="rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                >
                  Add to this turn's draft
                </button>
                <button
                  type="button"
                  data-testid="cancel-cabinet-proposal"
                  onClick={backToPost}
                  className="rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}

          {stagedPosts.length > 0 && post === null ? (
            <div
              ref={stagedSummaryRef}
              tabIndex={-1}
              data-testid="staged-cabinet-summary"
              className="mt-4 rounded border border-gold-600 p-3 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
            >
              <h3 className="text-sm uppercase tracking-[0.15em] text-parchment-100">
                Staged this turn
              </h3>
              <ul className="mt-2 flex flex-col gap-2">
                {stagedPosts.map((value) => {
                  const order = cabinetOrders[value];
                  if (order === undefined) {
                    return null;
                  }
                  const label = postLabel(posts, value);
                  return (
                    <li key={value} data-staged-order={value} data-order-origin={order.origin}>
                      <span>
                        {order.characterId === null
                          ? leftVacantLine(label)
                          : becomesLine(candidateName(order.characterId), label)}
                      </span>
                      {/* A generated companion has NO independent Remove: removing it alone would
                          leave a transfer seating one person in two posts. It goes when its
                          transfer goes, and the post stays selectable so it can be replaced by a
                          real appointment instead. */}
                      {order.origin === "explicit" ? (
                        <button
                          type="button"
                          data-remove-order={value}
                          onClick={() => removeOrder(value)}
                          className="ml-3 rounded border border-navy-800 px-2 py-0.5 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                        >
                          Remove
                        </button>
                      ) : (
                        <span
                          data-generated-note={value}
                          className="ml-3 text-xs text-parchment-200/60"
                        >
                          follows the transfer above
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}
        </div>
      </Panel>

      <Panel title="The rest of the government">
        <EmptyNote>
          Institutions, ministries and their metrics are not available in this gate. Only the
          cabinet is projected so far.
        </EmptyNote>
      </Panel>
    </div>
  );
}
