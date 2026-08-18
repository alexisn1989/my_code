/**
 * Gate 4A0 greybox — THE shared turn-result component.
 *
 * This file exists once, and both the live Turn Result screen and the History
 * detail view render it. That is what "one shared result component" means in the
 * frozen plan: the two views do not have parallel presentation logic that could
 * drift apart, exactly as the API defines `TurnResultProjection` once and returns
 * the same type from `/api/game/resolve` and `/api/game/history/{turn}`.
 *
 * Three disclosure layers: outcome -> drivers -> trace. The trace layer is
 * collapsed by default and expanded on demand.
 */

import { useState } from "react";

import { DataTable, EmptyNote, Panel, ToneValue } from "./components";
import type { TurnResultProjection } from "./contract";

export function TurnResultView({
  result,
  /** Distinguishes the two call sites in the DOM without duplicating any logic. */
  context,
}: {
  result: TurnResultProjection;
  context: "live" | "history";
}) {
  const [traceOpen, setTraceOpen] = useState(false);

  return (
    <div data-testid="turn-result-view" data-context={context} className="flex flex-col gap-4">
      <Panel title={`Turn ${result.turn} — outcome`} headingLevel={3}>
        <p className="text-lg">
          <ToneValue tone={result.outcomeTone}>{result.outcomeHeadline}</ToneValue>
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
          <ul className="flex list-disc flex-col gap-2 pl-5 text-sm">
            {result.drivers.map((driver) => (
              <li key={driver.reasonId}>
                {driver.label}{" "}
                <code className="text-xs text-parchment-200/50">{driver.reasonId}</code>
              </li>
            ))}
          </ul>
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
                entry.amountText,
                entry.effectText ?? "—",
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
          <div className="mt-3">
            {result.trace.length === 0 ? (
              <EmptyNote>No trace fields were recorded for this turn.</EmptyNote>
            ) : (
              <DataTable
                caption="Exact values and the report fields they came from"
                columns={["Value", "Amount", "Source field"]}
                rows={result.trace.map((field) => ({
                  key: field.sourceField,
                  cells: [
                    field.label,
                    field.valueText,
                    <code key="src" className="text-xs text-parchment-200/50">
                      {field.sourceField}
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
