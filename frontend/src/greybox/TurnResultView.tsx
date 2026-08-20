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

import { useState } from "react";

import type { TurnResultProjection } from "../api/client";
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

  return (
    <div data-testid="turn-result-view" data-context={context} className="flex flex-col gap-4">
      <Panel title={`Turn ${result.turn} — outcome`} headingLevel={3}>
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
          <ul className="flex list-disc flex-col gap-2 pl-5 text-sm">
            {result.drivers.map((driver) => (
              <li key={driver.reason_id}>
                {driver.label}{" "}
                <code className="text-xs text-parchment-200/50">{driver.reason_id}</code>
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
          <div className="mt-3">
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
                    <code key="src" className="text-xs text-parchment-200/50">
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
