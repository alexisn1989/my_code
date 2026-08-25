/**
 * Gate 4A3A (R10) — the consequences panel: three honest groups, never
 * blended.
 *
 * **Known before resolution** and **Uncertain / excluded** are both
 * rendered here, from `PreviewProjection` -- a deterministic estimate the
 * server computed from the ACTUAL drafted decision, composing the exact
 * same primitives `/resolve` does (never a client-side guess). **Actual
 * after resolution** is deliberately NOT this component: it is
 * `TurnResultView.tsx`, a different component on a different screen,
 * reading only stored `TurnResultProjection` fields -- so a "what we
 * expected" table and a "what happened" table can never accidentally share
 * a row or a heading.
 *
 * Nothing here computes a margin or shortfall the server did not already
 * supply: `ChamberPreview` carries `supporting_seats`/`required_seats`/
 * `total_seats`/`carries` and nothing else, so that is exactly what is
 * shown, chamber by chamber, never pooled into a single number.
 */

import type { PreviewProjection } from "../../api/client";
import { formatAmount, formatCommitted } from "../../format/format";
import { DataTable, EmptyNote, Panel, ToneValue } from "../components";

export function ConsequencesPanel({ preview }: { preview: PreviewProjection }) {
  return (
    <div className="flex flex-col gap-4">
      <Panel title="Known before resolution" headingLevel={3}>
        <p className="mb-3 text-xs text-parchment-200/60">
          This is an estimate, not a guarantee: it reflects the drafted decision as it stands
          right now, and resolving can still differ from this if the draft changes first.
        </p>

        {!preview.has_proposal ? (
          <EmptyNote>No policy proposal is drafted. Only investment (if any) would apply.</EmptyNote>
        ) : (
          <>
            <p className="mb-2 text-sm">
              Route: <span className="text-parchment-100">{preview.route}</span>
            </p>
            {preview.chambers.length === 0 ? (
              <EmptyNote>No legislative vote applies to this route.</EmptyNote>
            ) : (
              <DataTable
                caption="Chamber-by-chamber projection"
                columns={["Chamber", "Supporting", "Required", "Seats", "Carries"]}
                rows={preview.chambers.map((chamber) => ({
                  key: chamber.chamber,
                  cells: [
                    chamber.chamber,
                    formatAmount(chamber.supporting_seats),
                    formatAmount(chamber.required_seats),
                    formatAmount(chamber.total_seats),
                    <ToneValue key="c" tone={chamber.carries ? "positive" : "negative"}>
                      {chamber.carries ? "Carries" : "Fails"}
                    </ToneValue>,
                  ],
                }))}
              />
            )}
            <p className="mt-3 text-sm">
              <ToneValue tone={preview.would_pass ? "positive" : "negative"}>
                {preview.would_pass ? "Would pass" : "Would not pass"}
              </ToneValue>
            </p>
          </>
        )}

        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-parchment-200/70 sm:grid-cols-4">
          <div>
            <dt>Route cost</dt>
            <dd className="text-parchment-100">{formatAmount(preview.route_capital_cost)}</dd>
          </div>
          <div>
            <dt>Bargaining</dt>
            <dd className="text-parchment-100">{formatAmount(preview.influence_capital)}</dd>
          </div>
          <div>
            <dt>Investment</dt>
            <dd className="text-parchment-100">{formatAmount(preview.investment_capital)}</dd>
          </div>
          <div>
            <dt>Total committed</dt>
            <dd className="text-parchment-100">{formatAmount(preview.committed_capital)}</dd>
          </div>
        </dl>
        <p className="mt-2 text-sm">
          {formatCommitted(preview.committed_capital, preview.opening_capital)}
          {" — "}
          <ToneValue tone={preview.affordable ? "positive" : "negative"}>
            {preview.affordable ? "affordable" : "exceeds available capital"}
          </ToneValue>
        </p>
      </Panel>

      <Panel title="Uncertain / excluded from this estimate" headingLevel={3}>
        <p className="text-sm text-parchment-200/70">
          Preview does not guarantee these; nothing below claims a likely direction for any of
          them.
        </p>
        <ul className="mt-2 list-disc pl-5 text-sm text-parchment-200/70">
          {preview.excludes_stochastic_channels.map((channel) => (
            <li key={channel}>{channel}</li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
