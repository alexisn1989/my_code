/**
 * Relationships — the one room where the player meets the people who decide.
 *
 * Three negotiations were built server-side and NONE of them was reachable from the interface:
 * bargaining with a party leader, asking a foreign counterpart for aid, and giving or releasing a
 * promise could only be done by hand-writing JSON. This screen is where all three become playable,
 * and it is the last thing the named-actor slice owed a player.
 *
 * WHY RELATIONSHIPS AND NOT GOVERNMENT. Party leaders and foreign counterparts are literally what
 * this entry names; Government already owns the cabinet. `registry.tsx`'s stated reason for the
 * unavailable screens — that `DashboardProjection` gives only summary cards — is removed here for
 * counterparties specifically, exactly as `cabinet_posts` removed it for the cabinet, so this entry
 * goes live and keeps saying plainly that the rest of the relationship breakdown does not exist yet.
 *
 * STAGING, NOT RESOLVING. Confirming writes to the shared turn draft. The turn is still previewed
 * and resolved from Decisions, so a bargain competes for political capital against everything else.
 *
 * SELECTION IS LOCAL. Browsing counterparties and choosing one are component state; only Confirm
 * reaches the store. Cancel is therefore a real cancel, and reading a leader's traits never
 * invalidates a preview the player already has.
 *
 * TWO INTERACTION STATES, NOT THREE. The cabinet screen walks post -> candidate -> review because
 * choosing a post and choosing a person are two real decisions. Here the row IS the offer: the
 * price, the grant and the earliest legal deadline are all fixed by the server for that
 * counterparty, so a separate "choose your offer" step would be a step with nothing to decide in
 * it. That is a deliberate departure from the cabinet's three-state shape, not a missing state.
 *
 * NO LEGALITY, NO ARITHMETIC, NO IDENTITY GUESSING. Willingness, prices, pools, earliest legal
 * deadlines and releasability are rendered exactly as projected — the no-duplication contract. Every
 * sentence and every figure is composed in `src/format/format.ts`, the one directory
 * `format-boundary.test.ts` permits arithmetic in. Portraits are drawn from the server's
 * `portrait_ref` and never from a character id.
 *
 * THE BARGAIN CONFIRMATION IS DISABLED FOR A DECREE, AND THAT IS NOT CLIENT-SIDE LEGALITY. The
 * server refuses the set outright (`legislative_bargain_requires_legislative_route`); this screen
 * merely declines to stage a draft it has been told cannot resolve, and says why in visible copy
 * rather than leaving a dead control. The backend stays authoritative: a decree bargain submitted
 * any other way is still rejected there.
 */

import { useRef, useState } from "react";

import type { DecisionOptionsProjection } from "../../api/client";
import { useDecisionOptions } from "../../api/queries";
import {
  activePromiseQuestion,
  assistanceGrantLine,
  assistanceQuestion,
  assistanceStagedAnnouncement,
  bargainPriceLine,
  bargainQuestion,
  bargainStagedAnnouncement,
  counterpartySelectedAnnouncement,
  earliestDeadlineLine,
  formatBpsPercent,
  meetingDraftClearedAnnouncement,
  promiseOfferQuestion,
  promiseStagedAnnouncement,
  promiseWindowLine,
  releaseBlockedText,
  releaseStagedAnnouncement,
  remainingCapacityLine,
  releaseCostLine,
} from "../../format/format";
import { useSession } from "../../state/SessionContext";
import { useDraftStore, type PolicySlotKind } from "../../state/draft";
import { ErrorPanel } from "../../status/ErrorPanel";
import { EmptyNote, Panel } from "../components";
import { Portrait } from "../Portrait";
import type { ScreenProps } from "../registry";

type Options = DecisionOptionsProjection;
type BargainRow = Options["legislative_bargain_counterparties"][number];
type AssistanceRow = Options["foreign_assistance_counterparties"][number];
type PromiseRow = Options["promise_options"][number];
type ActiveRow = Options["active_promises"][number];

/** The player-facing name of the proposal a bargain would support. Two authored labels, chosen
 * here rather than transformed from an identifier — there is no `replace("_", " ")` anywhere. */
function proposalLabel(policySlot: PolicySlotKind | null): string {
  return policySlot === "amendment" ? "the constitutional amendment" : "the budget";
}

/** Why the bargain cannot be staged right now, or `null` when it can.
 *
 * Both reasons are facts about the DRAFT the player has already composed, not judgements about the
 * counterparty, which is why they live here and not in a projected field: no proposal at all, and a
 * proposal the player chose to decree. */
function bargainBlockedReason(
  policySlot: PolicySlotKind | null,
  route: "legislative" | "decree",
): string | null {
  if (policySlot === null) {
    return "Put a budget or an amendment in this turn's draft first — a bargain buys support for one exact proposal, so there has to be one.";
  }
  if (route === "decree") {
    return "This turn's proposal is being decreed, not put to the chamber. A bargain buys votes, and a decree holds none — change the route on the Decisions screen to bargain over it.";
  }
  return null;
}

export function MeetingScreen(_props: ScreenProps) {
  const { revision } = useSession();
  const options = useDecisionOptions(revision, { enabled: revision !== null });

  // LOCAL proposal state, discarded on navigation. An unconfirmed approach is not a decision.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");

  const policySlot = useDraftStore((state) => state.policySlot);
  const budgetRoute = useDraftStore((state) => state.budget.route);
  const amendmentRoute = useDraftStore((state) => state.amendment.route);
  const bargain = useDraftStore((state) => state.bargain);
  const assistance = useDraftStore((state) => state.assistance);
  const promise = useDraftStore((state) => state.promise);
  const setBargain = useDraftStore((state) => state.setBargain);
  const clearBargain = useDraftStore((state) => state.clearBargain);
  const setAssistanceRequest = useDraftStore((state) => state.setAssistanceRequest);
  const clearAssistanceRequest = useDraftStore((state) => state.clearAssistanceRequest);
  const setPromise = useDraftStore((state) => state.setPromise);
  const clearPromise = useDraftStore((state) => state.clearPromise);

  const reviewHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const stagedSummaryRef = useRef<HTMLDivElement | null>(null);
  const rowButtonRefs = useRef(new Map<string, HTMLButtonElement | null>());

  if (revision === null) {
    return (
      <div className="flex flex-col gap-6">
        <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
          Relationships
        </h2>
        <Panel title="The people who decide">
          <EmptyNote>Start or load a campaign to meet anybody.</EmptyNote>
        </Panel>
      </div>
    );
  }
  if (options.isPending) {
    return (
      <p role="status" className="text-sm text-parchment-200/80">
        Loading the people who decide…
      </p>
    );
  }
  if (options.isError) {
    return <ErrorPanel error={options.error} onRefresh={() => options.refetch()} />;
  }

  const data = options.data;
  const leaders = data.legislative_bargain_counterparties;
  const counterparts = data.foreign_assistance_counterparties;
  const promiseOptions = data.promise_options;
  const activePromises = data.active_promises;

  const route = policySlot === "amendment" ? amendmentRoute : budgetRoute;
  const blockedReason = bargainBlockedReason(policySlot, route);
  // The bargain's `proposal_kind` is DERIVED from the slot, never chosen. A bargain names the kind
  // of proposal it supports and slot 1 refuses the set when no proposal of that kind is present, so
  // offering the player a kind to pick would be offering them a way to compose a set that cannot
  // preview. The slot IS the answer.
  const proposalKind = policySlot;

  const selectedLeader = leaders.find((row) => row.character_id === selectedId) ?? null;
  const selectedCounterpart = counterparts.find((row) => row.profile_id === selectedId) ?? null;
  const selectedPromise = promiseOptions.find((row) => promiseKey(row) === selectedId) ?? null;
  const selectedActive = activePromises.find((row) => row.promise_id === selectedId) ?? null;
  const hasSelection =
    selectedLeader !== null ||
    selectedCounterpart !== null ||
    selectedPromise !== null ||
    selectedActive !== null;

  const state = hasSelection ? "counterpartySelected" : "idle";

  function select(id: string, displayName: string): void {
    setSelectedId(id);
    setAnnouncement(counterpartySelectedAnnouncement(displayName));
    window.setTimeout(() => reviewHeadingRef.current?.focus(), 0);
  }

  function backToIdle(): void {
    const returning = selectedId;
    setSelectedId(null);
    if (returning !== null) {
      window.setTimeout(() => rowButtonRefs.current.get(returning)?.focus(), 0);
    }
  }

  function afterConfirm(message: string): void {
    setAnnouncement(message);
    setSelectedId(null);
    window.setTimeout(() => stagedSummaryRef.current?.focus(), 0);
  }

  function confirmBargain(row: BargainRow): void {
    if (proposalKind === null || blockedReason !== null) {
      return;
    }
    setBargain(row.character_id, proposalKind);
    afterConfirm(bargainStagedAnnouncement(row.display_name, proposalLabel(policySlot)));
  }

  function confirmAssistance(row: AssistanceRow): void {
    setAssistanceRequest(row.profile_id);
    afterConfirm(assistanceStagedAnnouncement(row.display_name));
  }

  function confirmPromise(row: PromiseRow): void {
    setPromise({
      action: "make",
      characterId: row.character_id,
      termKind: row.term_kind,
      subjectId: row.subject_id,
      deadlineTurn: row.earliest_legal_deadline,
    });
    afterConfirm(promiseStagedAnnouncement(row.character_display_name, row.subject_display_name));
  }

  function confirmRelease(row: ActiveRow): void {
    setPromise({
      action: "release",
      characterId: row.character_id,
      promiseId: row.promise_id,
    });
    afterConfirm(releaseStagedAnnouncement(row.character_display_name));
  }

  function clearStaged(clear: () => void): void {
    clear();
    setAnnouncement(meetingDraftClearedAnnouncement());
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Relationships
      </h2>

      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>

      <div
        data-testid="meeting-panel"
        data-meeting-state={state}
        className="flex flex-col gap-6"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.stopPropagation();
            backToIdle();
          }
        }}
      >
        <Panel title="Party leaders">
          <p className="mb-3 text-sm text-parchment-200/70">
            A bargain buys one party's support for one exact proposal, at the price that leader
            asks. It is paid whether the vote passes or fails.
          </p>
          {blockedReason === null ? null : (
            <p data-testid="bargain-blocked" className="mb-3 text-sm text-amber-300">
              {blockedReason}
            </p>
          )}
          {leaders.length === 0 ? (
            <EmptyNote>No party leader in this legislature has anything to sell.</EmptyNote>
          ) : (
            <ul className="flex flex-col gap-2">
              {leaders.map((row) => (
                <li key={row.character_id}>
                  <button
                    type="button"
                    ref={(node) => {
                      rowButtonRefs.current.set(row.character_id, node);
                    }}
                    data-leader-option={row.character_id}
                    aria-pressed={selectedId === row.character_id}
                    onClick={() => select(row.character_id, row.display_name)}
                    className="flex w-full gap-3 rounded border border-navy-800 px-3 py-2 text-left text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500 aria-pressed:border-gold-500"
                  >
                    <Portrait portraitRef={row.portrait_ref} displayName={row.display_name} />
                    <span className="flex flex-col gap-0.5">
                      <span className="text-parchment-100">
                        {row.display_name} — {row.party_display_name}
                      </span>
                      <span data-leader-question={row.character_id} className="italic text-parchment-200/80">
                        “{bargainQuestion(row.will_deal)}”
                      </span>
                      {row.will_deal && row.asking_price !== null && row.asking_price !== undefined ? (
                        <span data-leader-price={row.character_id} className="text-xs text-parchment-200/70">
                          {bargainPriceLine(row.asking_price)}
                        </span>
                      ) : (
                        <span data-leader-refusal={row.character_id} className="text-xs text-parchment-200/70">
                          Will not deal at any price.
                        </span>
                      )}
                      <span className="text-xs text-parchment-200/60">
                        loyalty {formatBpsPercent(row.loyalty_bps)}, independence{" "}
                        {formatBpsPercent(row.independence_bps)}, ambition{" "}
                        {formatBpsPercent(row.ambition_bps)}, trust{" "}
                        {formatBpsPercent(row.personal_trust_bps)}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Foreign counterparts">
          <p className="mb-3 text-sm text-parchment-200/70">
            Assistance is money received, drawn from a counterpart's finite capacity. It costs no
            political capital, and the pool never refills.
          </p>
          {counterparts.length === 0 ? (
            <EmptyNote>No foreign counterpart is reachable from here.</EmptyNote>
          ) : (
            <ul className="flex flex-col gap-2">
              {counterparts.map((row) => (
                <li key={row.profile_id}>
                  <button
                    type="button"
                    ref={(node) => {
                      rowButtonRefs.current.set(row.profile_id, node);
                    }}
                    data-counterpart-option={row.profile_id}
                    aria-pressed={selectedId === row.profile_id}
                    onClick={() => select(row.profile_id, row.display_name)}
                    className="flex w-full gap-3 rounded border border-navy-800 px-3 py-2 text-left text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500 aria-pressed:border-gold-500"
                  >
                    {/* Present or absent TOGETHER, enforced on the projection: a counterpart with
                        no authored leader has no name and no portrait, and gets neither here. */}
                    {row.counterpart_portrait_ref === null ||
                    row.counterpart_portrait_ref === undefined ||
                    row.counterpart_display_name === null ||
                    row.counterpart_display_name === undefined ? null : (
                      <Portrait
                        portraitRef={row.counterpart_portrait_ref}
                        displayName={row.counterpart_display_name}
                      />
                    )}
                    <span className="flex flex-col gap-0.5">
                      <span className="text-parchment-100">
                        {row.display_name}
                        {row.counterpart_display_name === null ||
                        row.counterpart_display_name === undefined
                          ? ""
                          : ` — ${row.counterpart_display_name}`}
                      </span>
                      <span data-counterpart-question={row.profile_id} className="italic text-parchment-200/80">
                        “{assistanceQuestion(row.will_assist, row.refusal_reason)}”
                      </span>
                      {row.will_assist &&
                      row.estimated_grant !== null &&
                      row.estimated_grant !== undefined ? (
                        <span data-counterpart-grant={row.profile_id} className="text-xs text-parchment-200/70">
                          {assistanceGrantLine(row.estimated_grant)}
                        </span>
                      ) : null}
                      <span className="text-xs text-parchment-200/60">
                        {remainingCapacityLine(row.remaining_capacity)} standing{" "}
                        {formatBpsPercent(row.standing_bps)}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Promises">
          <p className="mb-3 text-sm text-parchment-200/70">
            A promise costs nothing to give and binds what you may do next. Keeping one raises that
            person's trust in you; breaking one costs twice as much as keeping one earns.
          </p>
          {promiseOptions.length === 0 ? (
            <EmptyNote>Nobody is waiting on a promise from you right now.</EmptyNote>
          ) : (
            <ul className="flex flex-col gap-2">
              {promiseOptions.map((row) => {
                const key = promiseKey(row);
                return (
                  <li key={key}>
                    <button
                      type="button"
                      ref={(node) => {
                        rowButtonRefs.current.set(key, node);
                      }}
                      data-promise-option={key}
                      aria-pressed={selectedId === key}
                      onClick={() => select(key, row.character_display_name)}
                      className="flex w-full gap-3 rounded border border-navy-800 px-3 py-2 text-left text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500 aria-pressed:border-gold-500"
                    >
                      <Portrait
                        portraitRef={row.character_portrait_ref}
                        displayName={row.character_display_name}
                      />
                      <span className="flex flex-col gap-0.5">
                        <span className="text-parchment-100">
                          {row.character_display_name} — {row.subject_display_name}
                        </span>
                        <span data-promise-question={key} className="italic text-parchment-200/80">
                          “{promiseOfferQuestion(row.term_kind)}”
                        </span>
                        <span className="text-xs text-parchment-200/70">
                          {earliestDeadlineLine(row.earliest_legal_deadline)}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {activePromises.length === 0 ? null : (
            <div className="mt-4 border-t border-navy-800 pt-4">
              <h3 className="text-sm uppercase tracking-[0.15em] text-parchment-100">
                Outstanding
              </h3>
              <ul className="mt-2 flex flex-col gap-2">
                {activePromises.map((row) => (
                  <li key={row.promise_id}>
                    <button
                      type="button"
                      ref={(node) => {
                        rowButtonRefs.current.set(row.promise_id, node);
                      }}
                      data-active-promise={row.promise_id}
                      aria-pressed={selectedId === row.promise_id}
                      onClick={() => select(row.promise_id, row.character_display_name)}
                      className="flex w-full gap-3 rounded border border-navy-800 px-3 py-2 text-left text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500 aria-pressed:border-gold-500"
                    >
                      <Portrait
                        portraitRef={row.character_portrait_ref}
                        displayName={row.character_display_name}
                      />
                      <span className="flex flex-col gap-0.5">
                        <span className="text-parchment-100">
                          {row.character_display_name} — {row.subject_display_name}
                        </span>
                        <span
                          data-active-promise-question={row.promise_id}
                          className="italic text-parchment-200/80"
                        >
                          “{activePromiseQuestion(row.releasable, row.status)}”
                        </span>
                        <span className="text-xs text-parchment-200/70">
                          {promiseWindowLine(row.made_turn, row.deadline_turn)}
                        </span>
                        {row.releasable ? null : (
                          <span
                            data-release-blocked={row.promise_id}
                            className="text-xs text-parchment-200/70"
                          >
                            {releaseBlockedText(row.release_blocked_reason)}
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>

        {state === "counterpartySelected" ? (
          <div className="rounded border border-gold-600 p-3">
            <h3
              ref={reviewHeadingRef}
              tabIndex={-1}
              data-testid="meeting-review-heading"
              className="text-sm uppercase tracking-[0.15em] text-parchment-100 focus:outline-none"
            >
              Review this approach
            </h3>
            <ul data-testid="meeting-review-lines" className="mt-2 flex flex-col gap-1 text-sm">
              {selectedLeader === null ? null : (
                <li>
                  {selectedLeader.display_name} is asked to back {proposalLabel(policySlot)}.
                </li>
              )}
              {selectedCounterpart === null ? null : (
                <li>{selectedCounterpart.display_name} is asked for assistance.</li>
              )}
              {selectedPromise === null ? null : (
                <li>
                  {selectedPromise.character_display_name} is promised{" "}
                  {selectedPromise.subject_display_name}, through turn{" "}
                  {selectedPromise.earliest_legal_deadline}.
                </li>
              )}
              {selectedActive === null ? null : (
                <li>
                  Your promise to {selectedActive.character_display_name} about{" "}
                  {selectedActive.subject_display_name} is released.
                </li>
              )}
              {selectedActive === null ? null : <li>{releaseCostLine()}</li>}
              {selectedLeader === null || blockedReason === null ? null : (
                <li data-testid="review-bargain-blocked" className="text-amber-300">
                  {blockedReason}
                </li>
              )}
            </ul>
            <div className="mt-3 flex gap-3">
              <button
                type="button"
                data-testid="confirm-meeting"
                disabled={
                  (selectedLeader !== null && blockedReason !== null) ||
                  (selectedActive !== null && !selectedActive.releasable)
                }
                onClick={() => {
                  if (selectedLeader !== null) {
                    confirmBargain(selectedLeader);
                  } else if (selectedCounterpart !== null) {
                    confirmAssistance(selectedCounterpart);
                  } else if (selectedPromise !== null) {
                    confirmPromise(selectedPromise);
                  } else if (selectedActive !== null) {
                    confirmRelease(selectedActive);
                  }
                }}
                className="rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Add to this turn's draft
              </button>
              <button
                type="button"
                data-testid="cancel-meeting"
                onClick={backToIdle}
                className="rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : null}

        {bargain !== null || assistance !== null || promise !== null ? (
          <div
            ref={stagedSummaryRef}
            tabIndex={-1}
            data-testid="staged-meeting-summary"
            className="rounded border border-gold-600 p-3 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            <h3 className="text-sm uppercase tracking-[0.15em] text-parchment-100">
              Staged this turn
            </h3>
            <ul className="mt-2 flex flex-col gap-2">
              {bargain === null ? null : (
                <li data-staged-bargain={bargain.characterId}>
                  <span>
                    {leaders.find((row) => row.character_id === bargain.characterId)
                      ?.display_name ?? bargain.characterId}{" "}
                    is asked to back {proposalLabel(bargain.proposalKind)}.
                  </span>
                  <button
                    type="button"
                    data-testid="remove-bargain"
                    onClick={() => clearStaged(clearBargain)}
                    className="ml-3 rounded border border-navy-800 px-2 py-0.5 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                  >
                    Remove
                  </button>
                </li>
              )}
              {assistance === null ? null : (
                <li data-staged-assistance={assistance.profileId}>
                  <span>
                    {counterparts.find((row) => row.profile_id === assistance.profileId)
                      ?.display_name ?? assistance.profileId}{" "}
                    is asked for assistance.
                  </span>
                  <button
                    type="button"
                    data-testid="remove-assistance"
                    onClick={() => clearStaged(clearAssistanceRequest)}
                    className="ml-3 rounded border border-navy-800 px-2 py-0.5 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                  >
                    Remove
                  </button>
                </li>
              )}
              {promise === null ? null : (
                <li data-staged-promise={promise.action}>
                  <span>
                    {promise.action === "make"
                      ? `A promise to ${promiseName(promiseOptions, promise.characterId)} about ${subjectName(promiseOptions, promise.subjectId)}.`
                      : `Releasing your promise to ${activeName(activePromises, promise.promiseId)}.`}
                  </span>
                  <button
                    type="button"
                    data-testid="remove-promise"
                    onClick={() => clearStaged(clearPromise)}
                    className="ml-3 rounded border border-navy-800 px-2 py-0.5 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                  >
                    Remove
                  </button>
                </li>
              )}
            </ul>
          </div>
        ) : null}
      </div>

      <Panel title="The rest of the relationship picture">
        <EmptyNote>
          Bloc standings, institutional loyalty and the wider diplomatic picture are not available
          in this gate. Only the people you can actually deal with are projected so far.
        </EmptyNote>
      </Panel>
    </div>
  );
}

/** A stable key for a promise OPTION, which has no id of its own: one row per valid triple, and
 * the triple is what identifies it. The two parts are joined only to key a React list and a local
 * selection — nothing ever parses it back apart, and every fact is read from the row's own typed
 * fields. */
function promiseKey(row: PromiseRow): string {
  return `${row.character_id}/${row.term_kind}/${row.subject_id}`;
}

/** Names resolved through rows in the SAME response — the one client-side derivation the
 * no-duplication contract allows. Falling back to the identifier would hide a contract bug rather
 * than surface it, so these are only reached when a row genuinely vanished between renders. */
function promiseName(rows: readonly PromiseRow[], characterId: string): string {
  return rows.find((row) => row.character_id === characterId)?.character_display_name ?? characterId;
}

function subjectName(rows: readonly PromiseRow[], subjectId: string): string {
  return rows.find((row) => row.subject_id === subjectId)?.subject_display_name ?? subjectId;
}

function activeName(rows: readonly ActiveRow[], promiseId: string): string {
  return rows.find((row) => row.promise_id === promiseId)?.character_display_name ?? promiseId;
}
