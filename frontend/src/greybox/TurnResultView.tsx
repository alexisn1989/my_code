/**
 * Gate 4A2 — THE shared turn-result component, now over the REAL
 * `TurnResultProjection`. Both the live Turn Result screen and the History
 * detail view render this same component, over the same generated type,
 * which is what makes `test_resolve_returns_both_shapes_and_they_agree_with_history`
 * (backend `test_api_concurrency.py`) a guarantee about the UI too: there is
 * no second, parallel presentation path that could drift from this one.
 *
 * Gate 4A3 M-4 restructures it after the approved M-V `result` mockup:
 *   1. the proposal card -- the verdict in words, what was proposed, and the vote the turn RECORDED
 *      (`recorded_vote`), or why none was held (`no_vote_reason`);
 *   2. people and reactions -- who acted, with the likeness they had on that turn, and how each
 *      bloc took it, its reactions listed under it;
 *   3. what else happened;
 *   4. the bookkeeping, collapsed: routine steps, the ledger, what did not change, and the trace.
 * `partitionDrivers` (format/result.ts) places every driver exactly once and keeps its original
 * index, so every Trace link still lands on its line.
 */

import { useEffect, useId, useState, type MouseEvent } from "react";

import type { TurnResultProjection } from "../api/client";
import { chamberLabel, driverSentence } from "../format/format";
import { AMENDMENT_BLOCS_NOT_RECORDED, recordedChamberLine, recordedProposalSentence } from "../format/parliament";
import {
  BLOCS_HEADING,
  NO_BLOC_MOVES,
  NO_PEOPLE,
  NOTHING_ELSE,
  OTHER_HEADING,
  PEOPLE_HEADING,
  RECORDED_SEATS_LEGEND,
  UNCHANGED_SUMMARY,
  VOTES_BY_BLOC,
  YOUR_PROPOSAL,
  blocMove,
  committedSummary,
  noVoteLine,
  partitionDrivers,
  personOf,
  recordedBlocSupport,
  recordedHemicycleLabel,
  resultVerdict,
  routineSummary,
  voteColours,
  type IndexedDriver,
} from "../format/result";
import { DataTable, EmptyNote, Panel, ToneValue } from "./components";
import { Hemicycle } from "./parliament/Hemicycle";
import { Portrait } from "./Portrait";

const SECTION = "rounded border border-navy-800 bg-navy-900 p-4";
// Every disclosure and the Trace toggle are at least 44 px tall: touch targets, as on the map and in
// the bloc panel.
const SUMMARY =
  "min-h-11 cursor-pointer rounded py-3 text-parchment-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500";

export function TurnResultView({
  result,
  /** Distinguishes the two call sites in the DOM without duplicating any logic. */
  context,
}: {
  result: TurnResultProjection;
  context: "live" | "history";
}) {
  const [traceOpen, setTraceOpen] = useState(false);
  // Gate 4A3 UX-2: bookkeeping drivers are folded into a CONTROLLED disclosure, so a Trace link can
  // open it before moving focus -- a native toggle alone would leave the target hidden.
  const [routineOpen, setRoutineOpen] = useState(false);
  const [focusTarget, setFocusTarget] = useState<number | null>(null);
  // Anchors are scoped per rendered view, so two views on one page could never share an id.
  const scope = useId();
  const anchorId = (index: number) => `${scope}driver-${index}`;

  const parts = partitionDrivers(result.drivers);
  const routineIndices = new Set(parts.routine.map((row) => row.index));
  const vote = result.recorded_vote ?? null;
  const verdict = resultVerdict(vote, result.no_vote_reason);
  const colours = vote === null ? {} : voteColours(vote);
  const proposalLine = vote !== null ? recordedProposalSentence(vote) : noVoteLine(result.no_vote_reason);

  useEffect(() => {
    if (focusTarget === null) return;
    const target = document.getElementById(anchorId(focusTarget));
    if (target !== null) {
      target.scrollIntoView?.({ block: "center" });
      target.focus();
    }
    setFocusTarget(null);
    // `anchorId` is derived from the stable `scope`; the effect runs per requested target.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusTarget]);

  function followReason(event: MouseEvent<HTMLAnchorElement>, index: number) {
    event.preventDefault();
    if (routineIndices.has(index)) setRoutineOpen(true);
    setFocusTarget(index);
  }

  // Every driver line carries its ORIGINAL index as its anchor, wherever the partition placed it,
  // so the Trace's "Reasons recorded" links keep landing on it.
  function anchorProps({ driver, index }: IndexedDriver) {
    return {
      id: anchorId(index),
      "data-reason-id": driver.reason_id,
      tabIndex: -1,
    } as const;
  }
  const FOCUSABLE = "rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500";

  function driverItem(row: IndexedDriver) {
    // Keyed by POSITION as well as reason id: one turn routinely emits the same reason several
    // times (a relationship reaction per bloc).
    return (
      <li key={`${row.index}:${row.reason_id}`} {...anchorProps(row)} className={FOCUSABLE}>
        {/* Composed from the driver's OWN stored params -- see `driverSentence`. The reason id is
            not painted here (T2): it lives in the Trace, linked back to this line. */}
        {driverSentence(row.driver.reason_id, row.driver.params, row.driver.label)}
      </li>
    );
  }

  function personItem(row: IndexedDriver) {
    const person = personOf(row.driver.params);
    return (
      <li
        key={`${row.index}:${row.reason_id}`}
        {...anchorProps(row)}
        data-testid="result-person"
        className={`flex items-start gap-3 ${FOCUSABLE}`}
      >
        {person?.portraitRef ? <Portrait portraitRef={person.portraitRef} displayName={person.name} /> : null}
        <div>
          {person ? <p className="font-[family-name:var(--font-display)] text-parchment-100">{person.name}</p> : null}
          <p>{driverSentence(row.driver.reason_id, row.driver.params, row.driver.label)}</p>
        </div>
      </li>
    );
  }

  return (
    <div
      data-testid="turn-result-view"
      data-context={context}
      data-unmatched-components={parts.unmatched.length}
      className="flex flex-col gap-4"
    >
      {/* 1. The proposal card. Gate 4A3 UX-4e (DR3): the neutral heading "Turn outcome" stays. The
          card is an authored surface (navy-900) with a gold edge; the M-V parchment card was not
          adopted, because every text backdrop must be one of the palette's authored surfaces. */}
      <section
        data-testid="proposal-card"
        data-verdict={verdict?.kind ?? "none"}
        className="rounded border border-gold-600 bg-navy-900 p-4"
        aria-labelledby={`${scope}outcome-heading`}
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h3
            id={`${scope}outcome-heading`}
            className="font-[family-name:var(--font-display)] text-lg text-parchment-100"
          >
            Turn outcome
          </h3>
          {verdict ? (
            <p
              data-testid="result-verdict"
              className="rounded border border-gold-600 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-parchment-100"
            >
              {verdict.word}
            </p>
          ) : null}
        </div>
        <p className="mt-2 text-lg">
          <ToneValue tone={result.outcome_tone}>{result.outcome_headline}</ToneValue>
        </p>
        {/* Gate 4A3 victory path: what this turn did to the campaign objective. */}
        {result.objective_line ? (
          <p data-testid="objective-line" className="mt-2 text-sm text-parchment-100">
            {result.objective_line}
          </p>
        ) : null}
        {proposalLine === null ? null : (
          <p data-testid="result-proposal" className="mt-3 text-sm">
            <span className="text-xs uppercase tracking-wide text-parchment-200/80">{YOUR_PROPOSAL}: </span>
            {proposalLine}
          </p>
        )}
        {parts.card.length === 0 ? null : (
          <ul data-testid="result-card-drivers" className="mt-2 flex list-disc flex-col gap-1 pl-5 text-sm">
            {parts.card.map(driverItem)}
          </ul>
        )}
        {vote === null ? null : (
          <div className="mt-3 flex flex-col gap-3">
            <div className="grid gap-3 md:grid-cols-2">
              {vote.chambers.map((chamber) => (
                <div
                  key={chamber.chamber}
                  data-testid="result-chamber"
                  data-chamber={chamber.chamber}
                  className="rounded border border-navy-800 p-3"
                >
                  <h4 className="font-[family-name:var(--font-display)] text-parchment-100">
                    {chamberLabel(chamber.chamber)}
                  </h4>
                  {vote.blocs_recorded && (chamber.blocs ?? []).length > 0 ? (
                    <Hemicycle
                      chamber={chamber.chamber}
                      mode="recorded"
                      arcLabels={false}
                      colours={colours}
                      label={recordedHemicycleLabel(chamber)}
                      blocs={(chamber.blocs ?? []).map((row) => ({
                        key: `${row.party_id}/${row.bloc_id}`,
                        partyId: row.party_id,
                        shortName: row.bloc_display_name,
                        seats: row.seats,
                        supporting: row.supporting_seats,
                      }))}
                    />
                  ) : null}
                  <p data-testid="result-chamber-line" className="mt-1 text-sm">
                    {recordedChamberLine(chamber)}
                  </p>
                </div>
              ))}
            </div>
            {vote.blocs_recorded ? (
              <>
                <p className="text-xs text-parchment-200/80">{RECORDED_SEATS_LEGEND}</p>
                <details data-testid="result-bloc-votes" className="text-sm">
                  <summary className={SUMMARY}>{VOTES_BY_BLOC}</summary>
                  <div className="mt-2">
                    <DataTable
                      caption={VOTES_BY_BLOC}
                      columns={["Bloc", "Chamber", "Supporting of seats"]}
                      rows={vote.chambers.flatMap((chamber) =>
                        (chamber.blocs ?? []).map((row) => ({
                          key: `${chamber.chamber}/${row.party_id}/${row.bloc_id}`,
                          cells: [row.bloc_display_name, chamberLabel(chamber.chamber), recordedBlocSupport(row)],
                        })),
                      )}
                    />
                  </div>
                </details>
              </>
            ) : (
              <p data-testid="amendment-blocs-note" className="text-sm text-parchment-200/80">
                {AMENDMENT_BLOCS_NOT_RECORDED}
              </p>
            )}
          </div>
        )}
        {context === "history" ? (
          <p className="mt-3 text-xs text-parchment-200/80">
            Reviewing a past turn. Rendered by the same component as the live result.
          </p>
        ) : null}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 2. People and reactions. */}
        <Panel title={PEOPLE_HEADING} headingLevel={3}>
          {parts.people.length === 0 ? (
            <EmptyNote>{NO_PEOPLE}</EmptyNote>
          ) : (
            <ul data-testid="result-people" className="flex flex-col gap-3 text-sm">
              {parts.people.map(personItem)}
            </ul>
          )}
          <h4 className="mb-2 mt-4 font-[family-name:var(--font-display)] text-parchment-100">{BLOCS_HEADING}</h4>
          {parts.blocs.length === 0 ? (
            <EmptyNote>{NO_BLOC_MOVES}</EmptyNote>
          ) : (
            <ul data-testid="result-blocs" className="flex flex-col divide-y divide-navy-800 text-sm">
              {parts.blocs.map((group) => {
                const move = blocMove(group.total.driver.params);
                return (
                  <li
                    key={`${group.total.index}:${group.key}`}
                    data-testid="result-bloc"
                    data-party={group.partyId}
                    data-bloc={group.blocId}
                    data-direction={move?.direction ?? "unknown"}
                    className="py-2"
                  >
                    <div {...anchorProps(group.total)} className={`flex flex-wrap justify-between gap-x-3 ${FOCUSABLE}`}>
                      {move === null ? (
                        driverSentence(group.total.driver.reason_id, group.total.driver.params, group.total.driver.label)
                      ) : (
                        <>
                          <span>
                            {move.name}
                            <span className="text-parchment-200/80"> · {move.span}</span>
                          </span>
                          <span data-testid="result-bloc-move">
                            <span aria-hidden="true">{move.mark} </span>
                            {move.words}
                          </span>
                        </>
                      )}
                    </div>
                    {group.components.length === 0 ? null : (
                      <ul className="mt-1 flex list-disc flex-col gap-1 pl-5 text-parchment-200/90">
                        {group.components.map(driverItem)}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>

        {/* 3. What else happened. */}
        <Panel title={OTHER_HEADING} headingLevel={3}>
          {parts.other.length === 0 ? (
            <EmptyNote>{NOTHING_ELSE}</EmptyNote>
          ) : (
            <ul data-testid="drivers-consequential" className="flex list-disc flex-col gap-2 pl-5 text-sm">
              {parts.other.map(driverItem)}
            </ul>
          )}
        </Panel>
      </div>

      {/* 4. The bookkeeping, collapsed. */}
      {parts.routine.length === 0 ? null : (
        <details
          data-testid="drivers-routine"
          open={routineOpen}
          onToggle={(event) => setRoutineOpen(event.currentTarget.open)}
          className={`${SECTION} text-sm`}
        >
          <summary className={SUMMARY}>{routineSummary(parts.routine.length)}</summary>
          <ul className="mt-2 flex list-disc flex-col gap-2 pl-5">{parts.routine.map(driverItem)}</ul>
        </details>
      )}

      <details data-testid="result-ledger" className={`${SECTION} text-sm`}>
        <summary className={SUMMARY}>{committedSummary(result.ledger.length)}</summary>
        <div className="mt-2">
          {result.ledger.length === 0 ? (
            <EmptyNote>Nothing was committed this turn.</EmptyNote>
          ) : (
            <DataTable
              caption="Political capital committed this turn"
              columns={["Item", "Target", "Amount", "Effect"]}
              rows={result.ledger.map((entry) => ({
                key: `${entry.label}-${entry.target ?? "none"}`,
                cells: [entry.label, entry.target ?? "—", entry.amount_text, entry.effect_text ?? "—"],
              }))}
            />
          )}
        </div>
      </details>

      <details data-testid="result-unchanged" className={`${SECTION} text-sm`}>
        <summary className={SUMMARY}>{UNCHANGED_SUMMARY}</summary>
        <div className="mt-2">
          {result.unchanged.length === 0 ? (
            <EmptyNote>No explicit unchanged statements were recorded.</EmptyNote>
          ) : (
            <ul className="flex list-disc flex-col gap-1 pl-5">
              {result.unchanged.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </div>
      </details>

      <Panel title="Trace" headingLevel={3}>
        <button
          type="button"
          aria-expanded={traceOpen}
          onClick={() => setTraceOpen((open) => !open)}
          className="min-h-11 rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          {traceOpen ? "Hide exact values" : "Show exact values"}
        </button>
        {traceOpen ? (
          <div className="mt-3 flex flex-col gap-3">
            {result.drivers.length === 0 ? null : (
              <div>
                <h4 className="text-sm font-semibold">Reasons recorded</h4>
                <ol data-testid="trace-reasons" className="mt-1 flex list-decimal flex-col gap-1 pl-5 text-sm">
                  {result.drivers.map((driver, index) => (
                    <li key={`${index}:${driver.reason_id}`}>
                      <a
                        href={`#${anchorId(index)}`}
                        onClick={(event) => followReason(event, index)}
                        className="underline focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                      >
                        <code className="text-xs">{driver.reason_id}</code>
                      </a>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {result.trace.length === 0 ? (
              <EmptyNote>No trace fields were recorded for this turn.</EmptyNote>
            ) : (
              <DataTable
                caption="Exact values and the report fields they came from"
                columns={["Value", "Amount", "Source field"]}
                rows={result.trace.map((field) => ({
                  key: field.source_field,
                  cells: [
                    field.label,
                    field.value_text,
                    <code key="src" className="text-xs text-parchment-200/60">
                      {field.source_field}
                    </code>,
                  ],
                }))}
              />
            )}
          </div>
        ) : null}
      </Panel>

      {result.terminal ? (
        <Panel title="This turn ended the campaign" headingLevel={3}>
          <p>{result.terminal.headline}</p>
        </Panel>
      ) : null}
    </div>
  );
}
