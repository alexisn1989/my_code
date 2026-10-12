/**
 * Gate 4A3 M-2 — Parliament: who sits where, what the draft needs, and how the last vote went.
 *
 * Built from the approved M-V mockups and M-0's data, never from client arithmetic:
 * - each chamber's thresholds are the engine's (`chamber_details`);
 * - support shown in a chamber is ONLY the current preview's own apportionment
 *   (`ChamberPreview.blocs`), and only while that preview describes the current draft
 *   (`useDraftPreview`), the route is legislative and the campaign is not over. Otherwise the chamber
 *   shows seats by bloc and says why;
 * - history appears only under "Last recorded vote", with the stored tallies of the turn that held
 *   the vote, labelled with that turn. It is never drawn onto today's chamber, whose seats may have
 *   changed since.
 *
 * Preview here runs the SAME shared preview Decisions uses. A preview landing never moves focus; a
 * polite announcement is made only for a request this screen issued.
 */

import { Fragment, type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import type { BlocOption, ChamberPreview, LastRecordedVote } from "../../api/client";
import { useDashboard, useDecisionOptions } from "../../api/queries";
import { formatAmount, formatBpsPercent, proposalStagedLine } from "../../format/format";
import { tallyBar } from "../../format/hemicycle";
import {
  AMENDMENT_BLOCS_NOT_RECORDED,
  amendmentThreshold,
  budgetThreshold,
  carryVerdict,
  chamberTitle,
  CONCLUDED_DRAFT_SENTENCE,
  currentTally,
  DECREE_DRAFT_SENTENCE,
  draftStatusText,
  hemicycleLabel,
  LEGEND_OTHER,
  LEGEND_SEATS,
  LEGEND_SUPPORTING,
  neededText,
  NO_PROPOSAL_SENTENCE,
  NO_RECORDED_VOTE,
  noLegislatureSentence,
  orderBlocs,
  parliamentIntro,
  partyColours,
  previewUpdatedAnnouncement,
  recordedChamberLine,
  recordedProposalSentence,
  recordedVoteHeading,
  roleLabel,
  type SeatsOnlyReason,
  seatsOnlyText,
  shortBlocName,
  SUPPORT_COLUMN,
  type ParliamentDraftStatus,
  UNAFFORDABLE_SENTENCE,
} from "../../format/parliament";
import { cardMatchesDraft } from "../../state/applyPolicyCard";
import { useDraftStore } from "../../state/draft";
import { stagedActions } from "../../state/stagedActions";
import { useSession } from "../../state/SessionContext";
import { useDraftPreview } from "../../state/useDraftPreview";
import { ErrorPanel } from "../../status/ErrorPanel";
import { LoadingPanel } from "../../status/StatusPanels";
import { ConcernSummaries } from "../ConcernCards";
import { DataTable, Panel } from "../components";
import { BlocPanel, type OpenBloc } from "../parliament/BlocPanel";
import { Hemicycle } from "../parliament/Hemicycle";
import type { ScreenProps } from "../registry";

const BUTTON =
  "rounded border px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500";

function Swatch({ colour }: { colour: string | undefined }) {
  return (
    <span
      aria-hidden="true"
      className="mr-2 inline-block h-2.5 w-2.5 shrink-0 rounded-full align-middle"
      style={{ backgroundColor: colour }}
    />
  );
}

function ChamberCard({
  chamber,
  totalSeats,
  budgetRequired,
  amendmentRequired,
  blocs,
  colours,
  estimate,
  seatsReason,
  openBloc,
  onOpenBloc,
  registerInvoker,
}: {
  /** Gate 4A3 M-3: which bloc's panel is open (to mark its button), and how to open one. */
  openBloc: OpenBloc | null;
  onOpenBloc: (bloc: BlocOption) => void;
  registerInvoker: (key: string, element: HTMLButtonElement | null) => void;
  chamber: string;
  totalSeats: number;
  budgetRequired: number;
  amendmentRequired: number;
  blocs: readonly BlocOption[];
  colours: Readonly<Record<string, string>>;
  /** The current preview's row for this chamber, or null (seats mode). */
  estimate: ChamberPreview | null;
  seatsReason: SeatsOnlyReason;
}) {
  const rows = orderBlocs(blocs);
  const supportingFor = (bloc: BlocOption): number | null => {
    if (estimate === null) return null;
    const row = estimate.blocs.find((r) => r.party_id === bloc.party_id && r.bloc_id === bloc.bloc_id);
    return row === undefined ? 0 : row.supporting_seats;
  };
  const headingId = `chamber-${chamber}`;
  const bar = estimate === null ? null : tallyBar(estimate.supporting_seats, estimate.required_seats, estimate.total_seats);
  return (
    <section
      aria-labelledby={headingId}
      data-testid="chamber-card"
      data-chamber={chamber}
      data-mode={estimate === null ? "seats" : "current"}
      className="rounded border border-navy-800 bg-navy-900 p-4"
    >
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
        <h3
          id={headingId}
          tabIndex={-1}
          className="font-[family-name:var(--font-display)] text-xl text-parchment-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          {chamberTitle(chamber, totalSeats)}
        </h3>
        <p className="flex flex-col text-sm text-parchment-200 sm:items-end">
          <span data-testid="budget-threshold">{budgetThreshold(budgetRequired)}</span>
          <span data-testid="amendment-threshold">{amendmentThreshold(amendmentRequired)}</span>
        </p>
      </div>

      <div className="mt-3">
        <Hemicycle
          chamber={chamber}
          colours={colours}
          mode={estimate === null ? "seats" : "current"}
          label={hemicycleLabel(
            chamber,
            totalSeats,
            estimate === null ? null : { supporting: estimate.supporting_seats, required: estimate.required_seats },
          )}
          blocs={rows.map((bloc) => ({
            key: `${bloc.party_id}/${bloc.bloc_id}`,
            partyId: bloc.party_id,
            shortName: shortBlocName(bloc.bloc_name, bloc.party_name),
            seats: bloc.seats,
            supporting: supportingFor(bloc) ?? 0,
          }))}
        />
      </div>

      {estimate === null ? (
        <p data-testid="chamber-tally" className="mt-2 text-center text-sm text-parchment-200/80">
          {seatsOnlyText(seatsReason)}
        </p>
      ) : (
        <div data-testid="chamber-tally" className="mt-2 flex flex-col items-center gap-1">
          <p className="flex flex-wrap items-baseline justify-center gap-x-4 gap-y-1 text-sm text-parchment-100">
            <span data-testid="chamber-supporting">{currentTally(estimate.supporting_seats)}</span>
            <span>{neededText(estimate.required_seats)}</span>
            <span
              data-testid="chamber-verdict"
              className={`rounded border px-2 py-0.5 ${estimate.carries ? "border-success-400 text-success-400" : "border-danger-400 text-danger-400"}`}
            >
              {carryVerdict(estimate.carries)}
            </span>
          </p>
          {bar === null ? null : (
            <div aria-hidden="true" className="relative h-2 w-full max-w-md overflow-hidden rounded-sm bg-navy-800">
              <div className="absolute inset-y-0 left-0 bg-gold-600" style={{ width: `${bar.supportPct}%` }} />
              <div className="absolute inset-y-0 w-0.5 bg-parchment-100" style={{ left: `${bar.requiredPct}%` }} />
            </div>
          )}
        </div>
      )}

      <p className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-parchment-200/80">
        {estimate === null ? (
          <span>{LEGEND_SEATS}</span>
        ) : (
          <>
            <span>
              <Swatch colour="var(--color-gold-600)" />
              {LEGEND_SUPPORTING}
            </span>
            <span>
              <span aria-hidden="true" className="mr-2 inline-block h-2.5 w-2.5 rounded-full border-2 border-gold-600 align-middle" />
              {LEGEND_OTHER}
            </span>
          </>
        )}
      </p>

      <div className="mt-3">
        <DataTable
          caption={`${chamberTitle(chamber, totalSeats)}: blocs`}
          columns={["Bloc · party · stance", "Seats", SUPPORT_COLUMN, "Relationship"]}
          rows={rows.map((bloc) => {
            const supporting = supportingFor(bloc);
            return {
              key: `${bloc.party_id}/${bloc.bloc_id}`,
              cells: [
                // Party and stance sit under the bloc's name rather than in a column of their own, so on
                // a phone the numbers stay in view instead of scrolling off beside a wide text column.
                <span key="name" className="block min-w-32">
                  {/* Gate 4A3 M-3: the bloc's name opens its panel. */}
                  <button
                    type="button"
                    data-bloc-open={`${bloc.party_id}/${bloc.bloc_id}`}
                    aria-expanded={
                      openBloc !== null &&
                      openBloc.chamber === chamber &&
                      openBloc.partyId === bloc.party_id &&
                      openBloc.blocId === bloc.bloc_id
                    }
                    ref={(element) => registerInvoker(`${chamber}/${bloc.party_id}/${bloc.bloc_id}`, element)}
                    onClick={() => onOpenBloc(bloc)}
                    className="block min-h-11 rounded text-left underline decoration-gold-600 underline-offset-4 aria-expanded:text-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                  >
                    <Swatch colour={colours[bloc.party_id]} />
                    {bloc.bloc_name}
                  </button>
                  <span className="block pl-4.5 text-xs text-parchment-200/80">
                    {bloc.party_name} · {roleLabel(bloc.government_role)}
                  </span>
                </span>,
                formatAmount(bloc.seats),
                <span key="support" data-testid="bloc-supporting">
                  {supporting === null ? "—" : formatAmount(supporting)}
                </span>,
                formatBpsPercent(bloc.government_relationship_bps),
              ],
            };
          })}
        />
      </div>
    </section>
  );
}

function LastRecordedVotePanel({ last }: { last: LastRecordedVote | null | undefined }) {
  if (last === null || last === undefined) {
    return (
      <Panel title="Last recorded vote">
        <p data-testid="last-recorded-vote" className="text-sm text-parchment-200/80">
          {NO_RECORDED_VOTE}
        </p>
      </Panel>
    );
  }
  const { vote } = last;
  return (
    <Panel title={recordedVoteHeading(last.turn)}>
      <div data-testid="last-recorded-vote" className="flex flex-col gap-3 text-sm">
        <p>{recordedProposalSentence(vote)}</p>
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {vote.chambers.map((c) => (
            <li key={c.chamber} data-testid="recorded-chamber" data-chamber={c.chamber}>
              {recordedChamberLine(c)}
            </li>
          ))}
        </ul>
        {vote.blocs_recorded ? (
          vote.chambers.map((c) =>
            c.blocs.length === 0 ? null : (
              <DataTable
                key={`blocs-${c.chamber}`}
                caption={`${recordedChamberLine(c)}: recorded votes by bloc`}
                columns={["Bloc", "Seats then", "Supporting"]}
                rows={c.blocs.map((b) => ({
                  key: `${b.party_id}/${b.bloc_id}`,
                  cells: [b.bloc_display_name, formatAmount(b.seats), formatAmount(b.supporting_seats)],
                }))}
              />
            ),
          )
        ) : (
          <p data-testid="amendment-blocs-note" className="text-parchment-200/80">
            {AMENDMENT_BLOCS_NOT_RECORDED}
          </p>
        )}
      </div>
    </Panel>
  );
}

/** Gate 4A3 M-3: from `xl` the bloc panel sits beside the chambers; below, inline after its chamber.
 * Without `matchMedia` (jsdom) the inline placement is used. */
function useWideLayout(): boolean {
  const query = "(min-width: 1280px)";
  const [wide, setWide] = useState(() => typeof window.matchMedia === "function" && window.matchMedia(query).matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const update = () => setWide(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, []);
  return wide;
}

/** Focus for a panel that closed with no invoking button left: its chamber's heading, else the
 * screen's heading. */
function focusFallback(chamber: string): void {
  const target =
    document.getElementById(`chamber-${chamber}`) ?? document.getElementById("parliament-heading");
  target?.focus();
}

export function ParliamentScreen({ navigate }: ScreenProps) {
  const { revision, campaignId } = useSession();
  const dashboard = useDashboard(revision, { enabled: revision !== null });
  const options = useDecisionOptions(revision, { enabled: revision !== null });
  const draft = useDraftStore();
  const preview = useDraftPreview();
  // Only a request THIS mounted screen issued is announced; nothing here ever moves focus.
  const [issuedRequestId, setIssuedRequestId] = useState<number | null>(null);
  const [announcement, setAnnouncement] = useState("");
  useEffect(() => {
    if (issuedRequestId === null || preview.current === null || preview.currentRequestId !== issuedRequestId) return;
    setAnnouncement(previewUpdatedAnnouncement(preview.current.chambers));
    setIssuedRequestId(null);
  }, [issuedRequestId, preview.current, preview.currentRequestId]);

  // ---- Gate 4A3 M-3: the bloc panel ------------------------------------------------------------
  // Only ids are kept; the bloc, leader, price and limits are read from the current projection on
  // every render (`BlocPanel`), so nothing shown can be stale.
  const [openBloc, setOpenBloc] = useState<OpenBloc | null>(null);
  const panelHeading = useRef<HTMLHeadingElement | null>(null);
  const invokers = useRef(new Map<string, HTMLButtonElement>());
  const focusPanelNext = useRef(false);
  const wide = useWideLayout();
  const registerInvoker = useCallback((key: string, element: HTMLButtonElement | null) => {
    if (element === null) invokers.current.delete(key);
    else invokers.current.set(key, element);
  }, []);
  // The panel belongs to one view of one campaign: a resolve, load, new game or view-changing
  // refresh closes it.
  const openRef = useRef<OpenBloc | null>(null);
  openRef.current = openBloc;
  useEffect(() => {
    const was = openRef.current;
    if (was === null) return;
    const focusWasInPanel = document.activeElement?.closest('[data-testid="bloc-panel"]') !== null && document.activeElement !== null;
    setOpenBloc(null);
    if (focusWasInPanel) window.setTimeout(() => focusFallback(was.chamber), 0);
  }, [revision, campaignId]);
  useEffect(() => {
    if (!focusPanelNext.current || openBloc === null) return;
    focusPanelNext.current = false;
    panelHeading.current?.focus();
  }, [openBloc]);
  // A bloc that is no longer in the current options closes the panel without error; focus that was
  // in the panel falls back to the chamber's heading (or the screen's).
  const currentBlocs = options.data?.blocs;
  useEffect(() => {
    if (openBloc === null || currentBlocs === undefined) return;
    if (currentBlocs.some((b) => b.party_id === openBloc.partyId && b.bloc_id === openBloc.blocId)) return;
    const focusLost = document.activeElement === null || document.activeElement === document.body;
    setOpenBloc(null);
    if (focusLost) focusFallback(openBloc.chamber);
  }, [currentBlocs, openBloc]);

  function openPanel(chamber: string, bloc: BlocOption): void {
    focusPanelNext.current = true;
    setOpenBloc({ partyId: bloc.party_id, blocId: bloc.bloc_id, chamber });
  }

  function closePanel(): void {
    if (openBloc === null) return;
    const invoker = invokers.current.get(`${openBloc.chamber}/${openBloc.partyId}/${openBloc.blocId}`);
    const chamber = openBloc.chamber;
    setOpenBloc(null);
    window.setTimeout(() => {
      if (invoker !== undefined && invoker.isConnected) invoker.focus();
      else focusFallback(chamber);
    }, 0);
  }

  // The heading sits at the SAME position in every state (first child of the first child), so React
  // keeps the one element from loading to loaded. A place on the map moves focus to this heading as
  // soon as it renders; were the element replaced when the data arrived, focus would fall to the
  // page (found by the M-1 place checks in the M-2 gate run).
  const heading = (
    <h2
      id="parliament-heading"
      tabIndex={-1}
      className="font-[family-name:var(--font-display)] text-2xl text-parchment-100 focus:outline-none"
    >
      Legislature
    </h2>
  );
  const summaries = <ConcernSummaries screen="legislature" />;

  if (dashboard.isPending || options.isPending) {
    return (
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-1">{heading}</div>
        <LoadingPanel label="Loading the legislature…" />
        {summaries}
      </div>
    );
  }
  if (dashboard.isError || options.isError) {
    const error = dashboard.error ?? options.error;
    return (
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-1">{heading}</div>
        <ErrorPanel
          error={error}
          onRefresh={() => {
            void dashboard.refetch();
            void options.refetch();
          }}
        />
        {summaries}
      </div>
    );
  }

  const country = dashboard.data.country_name;
  const data = options.data;
  const concluded = Boolean(dashboard.data.terminal);
  const slot = draft.policySlot;
  const route = slot === "amendment" ? draft.amendment.route : draft.budget.route;
  // A proposal counts only when it would actually be submitted (the builder's own emptiness rule).
  const hasProposal = slot !== null && stagedActions(draft).some((action) => action.kind === "proposal");
  const selectedCard =
    draft.selectedCardId === null ? undefined : data.policy_cards.find((card) => card.card_id === draft.selectedCardId);
  const proposalLine = !hasProposal
    ? NO_PROPOSAL_SENTENCE
    : selectedCard !== undefined && cardMatchesDraft(selectedCard, draft)
      ? `${selectedCard.title} — ${proposalStagedLine(slot, route)}`
      : proposalStagedLine(slot, route);

  // A live estimate is shown ONLY for the current draft, on the legislative route, while the
  // campaign is running. A concluded campaign suppresses it even if the store still holds a match.
  const liveEstimate = !concluded && hasProposal && route === "legislative" ? preview.current : null;
  const status: ParliamentDraftStatus = preview.pendingForDraft
    ? "pending"
    : preview.current !== null
      ? "current"
      : preview.stale
        ? "changed"
        : "not_previewed";
  const seatsReason = (chamber: string): SeatsOnlyReason => {
    if (concluded) return "concluded";
    if (!hasProposal) return "no_proposal";
    if (route === "decree") return "decree";
    if (liveEstimate !== null && !liveEstimate.chambers.some((c) => c.chamber === chamber)) return "not_in_preview";
    return status === "changed" ? "changed" : "not_previewed";
  };
  const colours = partyColours(data.blocs.map((b) => b.party_id));

  const panel: ReactNode =
    openBloc === null ? null : (
      <BlocPanel
        open={openBloc}
        options={data}
        concluded={concluded}
        currentPreview={concluded ? null : preview.current}
        headingRef={panelHeading}
        onClose={closePanel}
        announce={setAnnouncement}
        navigate={navigate}
      />
    );

  function handlePreview() {
    const token = preview.run();
    if (token !== null) setIssuedRequestId(token.requestId);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        {heading}
        <p className="text-sm text-parchment-200">{parliamentIntro(country)}</p>
      </div>

      <div role="status" aria-live="polite" className="sr-only" data-testid="parliament-announcement">
        {announcement}
      </div>

      <Panel title="Your draft">
        <div data-testid="parliament-draft" className="flex flex-col gap-3 text-sm">
          {concluded ? (
            <p>{CONCLUDED_DRAFT_SENTENCE}</p>
          ) : (
            <>
              <p data-testid="draft-proposal" className="text-parchment-100">
                {proposalLine}
              </p>
              {hasProposal && route === "decree" ? <p>{DECREE_DRAFT_SENTENCE}</p> : null}
              {hasProposal ? (
                <p data-testid="draft-status" className="text-parchment-200/80">
                  {draftStatusText(status)}
                </p>
              ) : null}
              {liveEstimate !== null && !liveEstimate.affordable ? (
                <p data-testid="draft-unaffordable">{UNAFFORDABLE_SENTENCE}</p>
              ) : null}
              {preview.errorForDraft !== null ? <ErrorPanel error={preview.errorForDraft} /> : null}
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  className={`${BUTTON} border-navy-800`}
                  onClick={() => navigate("decisions", { focusHeading: true })}
                >
                  Change in Decisions
                </button>
                {hasProposal ? (
                  <button
                    type="button"
                    className={`${BUTTON} border-gold-600 disabled:opacity-50`}
                    disabled={preview.pendingForDraft}
                    onClick={handlePreview}
                  >
                    {preview.pendingForDraft ? "Previewing…" : "Preview"}
                  </button>
                ) : null}
              </div>
            </>
          )}
        </div>
      </Panel>

      {/* The wrapper's structure never changes when the panel opens or closes (only its class), so
          the chamber cards and their bloc buttons are never remounted and focus can return to them. */}
      <div
        data-testid="parliament-body"
        className={wide && openBloc !== null ? "grid grid-cols-[minmax(0,1fr)_24rem] items-start gap-6" : "flex flex-col"}
      >
        <div className="flex min-w-0 flex-col gap-6">
          {data.chamber_details.length === 0 ? (
            <Panel title="Chambers">
              <p className="text-sm">{noLegislatureSentence(country)}</p>
            </Panel>
          ) : (
            data.chamber_details.map((detail) => {
              const estimate = liveEstimate?.chambers.find((c) => c.chamber === detail.chamber) ?? null;
              return (
                <Fragment key={detail.chamber}>
                  <ChamberCard
                    chamber={detail.chamber}
                    totalSeats={detail.total_seats}
                    budgetRequired={detail.budget_required_seats}
                    amendmentRequired={detail.amendment_required_seats}
                    blocs={data.blocs.filter((b) => b.chamber === detail.chamber)}
                    colours={colours}
                    estimate={estimate}
                    seatsReason={seatsReason(detail.chamber)}
                    openBloc={openBloc}
                    onOpenBloc={(bloc) => openPanel(detail.chamber, bloc)}
                    registerInvoker={registerInvoker}
                  />
                  {!wide && openBloc !== null && openBloc.chamber === detail.chamber ? panel : null}
                </Fragment>
              );
            })
          )}

          <LastRecordedVotePanel last={data.last_recorded_vote} />
        </div>
        {wide && openBloc !== null ? <aside className="sticky top-4">{panel}</aside> : null}
      </div>

      {summaries}
    </div>
  );
}
