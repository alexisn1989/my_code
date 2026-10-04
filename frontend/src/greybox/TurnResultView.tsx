/**
 * Gate 4A2 — THE shared turn-result component, now over the REAL
 * `TurnResultProjection`. Both the live Turn Result screen and the History
 * detail view render this same component, over the same generated type,
 * which is what makes `test_resolve_returns_both_shapes_and_they_agree_with_history`
 * (backend `test_api_concurrency.py`) a guarantee about the UI too: there is
 * no second, parallel presentation path that could drift from this one.
 *
 * Three disclosure layers: outcome -> drivers/ledger/unchanged -> trace. The
 * trace layer is collapsed by default and expanded on demand.
 */

import { useEffect, useId, useState, type MouseEvent } from "react";

import type { TurnResultProjection } from "../api/client";
import { driverSentence, isRoutineDriver, outcomeFirst } from "../format/format";
import { DataTable, EmptyNote, Panel, ToneValue } from "./components";

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

  const drivers = result.drivers.map((driver, index) => ({ driver, index }));
  // Gate 4A3 UX-4e (DR1): what the player's decisions did comes first; the rest keeps server order.
  const visible = outcomeFirst(
    drivers.filter(({ driver }) => !isRoutineDriver(driver)).map((row) => ({ ...row, reason_id: row.driver.reason_id })),
  );
  const routine = drivers.filter(({ driver }) => isRoutineDriver(driver));

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

  function followReason(event: MouseEvent<HTMLAnchorElement>, index: number, isRoutine: boolean) {
    event.preventDefault();
    if (isRoutine) setRoutineOpen(true);
    setFocusTarget(index);
  }

  function driverItem({ driver, index }: { driver: (typeof result.drivers)[number]; index: number }) {
    return (
      // Keyed by POSITION as well as reason id: one turn routinely emits the same reason several
      // times (a relationship reaction per bloc), and a reason-id key alone gave React duplicate
      // keys -- found by the Gate 4A3 Commit 5b walkthrough. The list is static per render, so the
      // position is a stable identity here.
      <li
        key={`${index}:${driver.reason_id}`}
        id={anchorId(index)}
        data-reason-id={driver.reason_id}
        tabIndex={-1}
        className="rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
      >
        {/* Composed from the driver's OWN stored params where this build has wording for the
            reason, and from the generic `label` otherwise -- see `driverSentence`. The reason id
            itself is no longer painted here (T2): it lives in the Trace, linked back to this line. */}
        {driverSentence(driver.reason_id, driver.params, driver.label)}
      </li>
    );
  }

  return (
    <div data-testid="turn-result-view" data-context={context} className="flex flex-col gap-4">
      {/* Gate 4A3 UX-4e (DR3, ruled): "Turn {N} — outcome" named the turn the result PRODUCED, one
          higher than the turn the player had just resolved ("Resolve turn 0…" → "Turn 1 — outcome").
          A neutral heading removes the contradiction without a contract change (R3, narrowed). */}
      <Panel title="Turn outcome" headingLevel={3}>
        <p className="text-lg">
          <ToneValue tone={result.outcome_tone}>{result.outcome_headline}</ToneValue>
        </p>
        {context === "history" ? (
          <p className="mt-2 text-xs text-parchment-200/60">
            Reviewing a past turn. Rendered by the same component as the live result.
          </p>
        ) : null}
      </Panel>

      <Panel title="Why this happened" headingLevel={3}>
        {result.drivers.length === 0 ? (
          <EmptyNote>No drivers were recorded for this turn.</EmptyNote>
        ) : (
          <>
            {visible.length === 0 ? (
              <EmptyNote>Only routine steps were recorded for this turn.</EmptyNote>
            ) : (
              <ul data-testid="drivers-consequential" className="flex list-disc flex-col gap-2 pl-5 text-sm">
                {visible.map(driverItem)}
              </ul>
            )}
            {routine.length === 0 ? null : (
              <details
                data-testid="drivers-routine"
                open={routineOpen}
                onToggle={(event) => setRoutineOpen(event.currentTarget.open)}
                className="mt-3 text-sm"
              >
                <summary className="cursor-pointer rounded text-parchment-200/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500">
                  Routine steps this turn ({routine.length})
                </summary>
                <ul className="mt-2 flex list-disc flex-col gap-2 pl-5">{routine.map(driverItem)}</ul>
              </details>
            )}
          </>
        )}
      </Panel>

      <Panel title="What your decision committed" headingLevel={3}>
        {result.ledger.length === 0 ? (
          <EmptyNote>Nothing was committed this turn.</EmptyNote>
        ) : (
          <DataTable
            caption="Political capital committed this turn"
            columns={["Item", "Target", "Amount", "Effect"]}
            rows={result.ledger.map((entry) => ({
              key: `${entry.label}-${entry.target ?? "none"}`,
              cells: [
                entry.label,
                entry.target ?? "—",
                entry.amount_text,
                entry.effect_text ?? "—",
              ],
            }))}
          />
        )}
      </Panel>

      <Panel title="What did not change" headingLevel={3}>
        {result.unchanged.length === 0 ? (
          <EmptyNote>No explicit unchanged statements were recorded.</EmptyNote>
        ) : (
          <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
            {result.unchanged.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Trace" headingLevel={3}>
        <button
          type="button"
          aria-expanded={traceOpen}
          onClick={() => setTraceOpen((open) => !open)}
          className="rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          {traceOpen ? "Hide exact values" : "Show exact values"}
        </button>
        {traceOpen ? (
          <div className="mt-3 flex flex-col gap-3">
            {result.drivers.length === 0 ? null : (
              <div>
                <h4 className="text-sm font-semibold">Reasons recorded</h4>
                <ol data-testid="trace-reasons" className="mt-1 flex list-decimal flex-col gap-1 pl-5 text-sm">
                  {drivers.map(({ driver, index }) => (
                    <li key={`${index}:${driver.reason_id}`}>
                      <a
                        href={`#${anchorId(index)}`}
                        onClick={(event) => followReason(event, index, isRoutineDriver(driver))}
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
