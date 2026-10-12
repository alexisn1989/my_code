/**
 * Gate 4A3 M-3 — the bloc panel: one bloc, its party leader, and the three things the player can
 * stage for it from Parliament.
 *
 * Every action writes the EXISTING draft store through its existing setter (`setBargain`,
 * `setBudgetInfluence` / `setAmendmentInfluence`, `setInvestment`), so what is staged here is
 * exactly what Relationships and Decisions stage, and changes only its own field.
 *
 * Nothing is cached: the panel is given ids, and reads the bloc, the leader, the price and the
 * limits from the CURRENT projection on every render. Nothing is invented: a leader's price and
 * willingness are the engine's; an endorsement's effect is shown only by a later Preview, never
 * estimated here; an investment's effect only from a CURRENT preview.
 *
 * A concluded campaign leaves the panel readable but every action disabled, whatever the draft and
 * options still hold.
 */

import { type RefObject, useEffect, useRef } from "react";

import type { DecisionOptionsProjection, PreviewProjection } from "../../api/client";
import {
  bargainPriceLine,
  bargainQuestion,
  bargainStagedAnnouncement,
  bargainStagedLine,
  investmentEffectSentence,
  investmentStagedLine,
  proposalPhrase,
} from "../../format/format";
import {
  amountFromInput,
  BARGAIN_ACTION_NOTE,
  bargainBlockedReason,
  blocSeatsLine,
  blocStanceLine,
  CAMPAIGN_ENDED,
  CHANGE_PROPOSAL_NOTE,
  distinctPartyBlocCount,
  influenceBlockedReason,
  INFLUENCE_NOTE,
  influenceSummaryLine,
  INVESTMENT_NOTE,
  INVESTMENT_PREVIEW_NOTE,
  investmentRangeLine,
  keepBargainLabel,
  keptAnnouncement,
  leaderTraitsLine,
  noCounterpartLine,
  NOTHING_STAGED_FOR_BLOC,
  OFFER_EFFECT_NOTE,
  offerLine,
  PRICE_FIXED,
  REFUSES_LINE,
  relationshipLine,
  replaceBargainLabel,
  replaceBargainSentence,
  replacedAnnouncement,
  spendingPreferenceLine,
  stageBargainLabel,
  stagedPartyWideLine,
  taxPreferenceLine,
  withdrewAnnouncement,
} from "../../format/parliament";
import { useDraftStore } from "../../state/draft";
import { Portrait } from "../Portrait";
import type { ScreenProps } from "../registry";

const BUTTON =
  "min-h-11 rounded border px-3 py-1 text-sm disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500";
const INPUT =
  "min-h-11 w-28 rounded border border-navy-800 bg-navy-950 px-2 py-1 text-right disabled:opacity-50";

export interface OpenBloc {
  partyId: string;
  blocId: string;
  /** The chamber whose row opened the panel (for placement and focus fallback). */
  chamber: string;
}

export function BlocPanel({
  open,
  options,
  concluded,
  currentPreview,
  headingRef,
  onClose,
  announce,
  navigate,
}: {
  open: OpenBloc;
  options: DecisionOptionsProjection;
  concluded: boolean;
  /** The CURRENT preview for this draft, or null (never a stale one). */
  currentPreview: PreviewProjection | null;
  headingRef: RefObject<HTMLHeadingElement | null>;
  onClose: () => void;
  announce: (message: string) => void;
  navigate: ScreenProps["navigate"];
}) {
  const draft = useDraftStore();
  // Staging swaps the Stage button for the staged line (and withdrawing swaps it back), so the
  // control that had focus disappears. Focus moves to what replaced it instead of falling to the page.
  const focusNext = useRef<"staged" | "stage" | null>(null);
  const stagedRef = useRef<HTMLParagraphElement | null>(null);
  const stageButtonRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    const target = focusNext.current;
    if (target === null) return;
    focusNext.current = null;
    (target === "staged" ? stagedRef.current : stageButtonRef.current)?.focus();
  });
  const rows = options.blocs.filter((b) => b.party_id === open.partyId && b.bloc_id === open.blocId);
  const bloc = rows[0];
  if (bloc === undefined) return null;

  const key = `${open.partyId}/${open.blocId}`;
  const slot = draft.policySlot;
  const route = slot === "amendment" ? draft.amendment.route : draft.budget.route;
  const leader = options.legislative_bargain_counterparties.find((c) => c.party_id === open.partyId) ?? null;
  const staged = draft.bargain;
  const stagedLeader =
    staged === null
      ? null
      : options.legislative_bargain_counterparties.find((c) => c.character_id === staged.characterId) ?? null;
  const bargainBlocked = concluded ? CAMPAIGN_ENDED : bargainBlockedReason(slot, route);
  const influenceBlocked = concluded ? CAMPAIGN_ENDED : influenceBlockedReason(slot, route);
  const influence = slot === "amendment" ? draft.amendment.influence : draft.budget.influence;
  const influenceAmount = influence[key];
  const investment = draft.investments[key];
  const effect =
    concluded || currentPreview === null
      ? undefined
      : currentPreview.investment_effects.find((e) => e.party_id === open.partyId && e.bloc_id === open.blocId);
  const headingId = `bloc-panel-${open.partyId}-${open.blocId}`;

  function stage(leaderId: string, leaderName: string): void {
    if (slot === null || bargainBlocked !== null) return;
    const previous = stagedLeader;
    focusNext.current = "staged";
    draft.setBargain(leaderId, slot);
    announce(
      previous !== null && previous.character_id !== leaderId
        ? replacedAnnouncement(previous.display_name, leaderName)
        : bargainStagedAnnouncement(leaderName, proposalPhrase(slot)),
    );
  }

  function setInfluence(raw: string): void {
    if (slot === null || influenceBlocked !== null) return;
    const amount = amountFromInput(raw);
    if (slot === "amendment") draft.setAmendmentInfluence(open.partyId, open.blocId, amount);
    else draft.setBudgetInfluence(open.partyId, open.blocId, amount);
  }

  function setInvestment(raw: string): void {
    if (concluded) return;
    draft.setInvestment(open.partyId, open.blocId, amountFromInput(raw));
  }

  const stagedLines: string[] = [];
  if (staged !== null && stagedLeader !== null && stagedLeader.party_id === open.partyId) {
    stagedLines.push(bargainStagedLine(stagedLeader.display_name, staged.proposalKind));
  }
  if (slot !== null && influenceAmount !== undefined && influenceAmount > 0) {
    stagedLines.push(influenceSummaryLine(influenceAmount, slot));
  }
  if (investment !== undefined && investment > 0) {
    stagedLines.push(investmentStagedLine(investment, bloc.bloc_name));
  }

  return (
    <section
      role="region"
      aria-labelledby={headingId}
      data-testid="bloc-panel"
      data-party={open.partyId}
      data-bloc={open.blocId}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onClose();
        }
      }}
      className="rounded border border-gold-600 bg-navy-900 p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-parchment-200/80">
            {blocStanceLine(bloc.party_name, bloc.government_role)}
          </p>
          <h3
            id={headingId}
            ref={headingRef}
            tabIndex={-1}
            className="font-[family-name:var(--font-display)] text-xl text-parchment-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            {bloc.bloc_name}
          </h3>
          <p className="text-sm text-parchment-200/80">{blocSeatsLine(rows)}</p>
        </div>
        <button type="button" onClick={onClose} className={`${BUTTON} border-navy-800`} aria-label={`Close ${bloc.bloc_name}`}>
          Close
        </button>
      </div>

      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-parchment-200/80">Relationship</dt>
        <dd data-testid="bloc-relationship">{relationshipLine(bloc.government_relationship_bps)}</dd>
        <dt className="text-parchment-200/80">Taxes</dt>
        <dd>{taxPreferenceLine(bloc.tax_preference_bps)}</dd>
        <dt className="text-parchment-200/80">Spending</dt>
        <dd>{spendingPreferenceLine(bloc.spending_preference_bps)}</dd>
      </dl>

      <div data-testid="bloc-leader" className="mt-4 rounded border border-navy-800 bg-navy-950 p-3 text-sm">
        <p className="text-xs uppercase tracking-wide text-parchment-200/80">Party leader</p>
        {leader === null ? (
          <p data-testid="no-counterpart" className="mt-1">
            {noCounterpartLine(bloc.party_name)}
          </p>
        ) : (
          <>
            <div className="mt-2 flex gap-3">
              <Portrait portraitRef={leader.portrait_ref} displayName={leader.display_name} />
              <div className="min-w-0">
                <p className="text-parchment-100">{leader.display_name}</p>
                <p className="text-parchment-200/80">{leader.party_display_name}</p>
                <p className="text-xs text-parchment-200/80">{leaderTraitsLine(leader)}</p>
              </div>
            </div>
            <p className="mt-2 italic text-parchment-200/80">“{bargainQuestion(leader.will_deal)}”</p>
            {!leader.will_deal || leader.asking_price === null || leader.asking_price === undefined ? (
              <p data-testid="leader-refuses" className="mt-1">
                {REFUSES_LINE}
              </p>
            ) : (
              <div data-testid="leader-offer" className="mt-2 flex flex-col gap-2">
                <p>
                  {offerLine(slot)} {bargainPriceLine(leader.asking_price)} {PRICE_FIXED}
                </p>
                <p className="text-parchment-200/80">{OFFER_EFFECT_NOTE}</p>
                {staged !== null && staged.characterId === leader.character_id ? (
                  <>
                    <p data-testid="bargain-staged-here" ref={stagedRef} tabIndex={-1} className="focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500">
                      {stagedPartyWideLine(
                        leader.display_name,
                        distinctPartyBlocCount(options.blocs, open.partyId),
                        leader.party_display_name,
                      )}
                    </p>
                    <div>
                      <button
                        type="button"
                        disabled={concluded}
                        onClick={() => {
                          if (concluded) return;
                          focusNext.current = "stage";
                          draft.clearBargain();
                          announce(withdrewAnnouncement(leader.display_name));
                        }}
                        className={`${BUTTON} border-navy-800`}
                      >
                        Withdraw bargain
                      </button>
                    </div>
                  </>
                ) : staged !== null && stagedLeader !== null ? (
                  <>
                    <p data-testid="bargain-replace">
                      {replaceBargainSentence(stagedLeader.display_name, stagedLeader.asking_price ?? null)}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={bargainBlocked !== null}
                        onClick={() => stage(leader.character_id, leader.display_name)}
                        className={`${BUTTON} border-gold-600`}
                      >
                        {replaceBargainLabel(leader.display_name, leader.asking_price)}
                      </button>
                      <button
                        type="button"
                        disabled={concluded}
                        onClick={() => announce(keptAnnouncement(stagedLeader.display_name))}
                        className={`${BUTTON} border-navy-800`}
                      >
                        {keepBargainLabel(stagedLeader.display_name)}
                      </button>
                    </div>
                  </>
                ) : (
                  <div>
                    <button
                      type="button"
                      ref={stageButtonRef}
                      disabled={bargainBlocked !== null}
                      onClick={() => stage(leader.character_id, leader.display_name)}
                      className={`${BUTTON} border-gold-600`}
                    >
                      {stageBargainLabel(leader.asking_price)}
                    </button>
                  </div>
                )}
                {bargainBlocked !== null ? (
                  <p data-testid="bargain-blocked-reason" className="text-warning-400">
                    {bargainBlocked}
                  </p>
                ) : null}
              </div>
            )}
          </>
        )}
      </div>

      <h4 className="mt-4 font-[family-name:var(--font-display)] text-base text-parchment-100">What you can do</h4>
      <ol className="m-0 mt-2 flex list-none flex-col gap-3 p-0 text-sm">
        <li className="rounded border border-navy-800 p-3">
          <p className="text-parchment-100">1. Change the proposal</p>
          <p className="text-parchment-200/80">{CHANGE_PROPOSAL_NOTE}</p>
          <button
            type="button"
            onClick={() => navigate("decisions", { focusHeading: true })}
            className={`${BUTTON} mt-2 border-navy-800`}
          >
            Open in Decisions
          </button>
        </li>
        <li className="rounded border border-navy-800 p-3">
          <p className="text-parchment-100">2. Bargain with the leader</p>
          <p className="text-parchment-200/80">{BARGAIN_ACTION_NOTE}</p>
        </li>
        <li className="rounded border border-navy-800 p-3">
          <label className="flex flex-col gap-1">
            <span className="text-parchment-100">3. Spend influence on this vote</span>
            <span className="text-parchment-200/80">{INFLUENCE_NOTE}</span>
            <input
              type="number"
              min={0}
              data-testid="panel-influence"
              aria-label={`Influence capital for ${bloc.bloc_name}`}
              disabled={influenceBlocked !== null}
              value={influenceBlocked === null && influenceAmount !== undefined ? influenceAmount : ""}
              onChange={(event) => setInfluence(event.target.value)}
              className={INPUT}
            />
          </label>
          {influenceBlocked !== null ? (
            <p data-testid="influence-blocked-reason" className="mt-1 text-warning-400">
              {influenceBlocked}
            </p>
          ) : null}
        </li>
        <li className="rounded border border-navy-800 p-3">
          <label className="flex flex-col gap-1">
            <span className="text-parchment-100">4. Invest in the relationship</span>
            <span className="text-parchment-200/80">
              {INVESTMENT_NOTE}{" "}
              {investmentRangeLine(options.relationship_investment_minimum, options.relationship_investment_maximum)}
            </span>
            <input
              type="number"
              min={0}
              max={options.relationship_investment_maximum}
              data-testid="panel-investment"
              aria-label={`Relationship investment for ${bloc.bloc_name}`}
              disabled={concluded}
              value={investment ?? ""}
              onChange={(event) => setInvestment(event.target.value)}
              className={INPUT}
            />
          </label>
          <p data-testid="investment-effect" className="mt-1 text-parchment-200/80">
            {concluded ? CAMPAIGN_ENDED : effect !== undefined ? investmentEffectSentence(effect) : INVESTMENT_PREVIEW_NOTE}
          </p>
        </li>
      </ol>

      <h4 className="mt-4 font-[family-name:var(--font-display)] text-base text-parchment-100">Staged for this bloc</h4>
      <ul data-testid="bloc-staged" className="m-0 mt-1 list-none p-0 text-sm">
        {stagedLines.length === 0 ? (
          <li className="text-parchment-200/80">{NOTHING_STAGED_FOR_BLOC}</li>
        ) : (
          stagedLines.map((line) => <li key={line}>{line}</li>)
        )}
      </ul>
    </section>
  );
}
