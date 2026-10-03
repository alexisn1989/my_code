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
 * Chambers are shown chamber by chamber, never pooled into a single number. Gate 4A3 UX-1 adds one
 * shortfall line PER FAILING CHAMBER, computed in `src/format/` from that chamber's own row, and
 * makes the panel ROUTE-AWARE: a decree is not put to a vote, so it shows no vote table and no
 * shortfall advice -- only a pre-resolution sentence that never claims an enactment the resolver
 * would refuse (an unaffordable decree is worded as a refusal).
 */

import type { PreviewProjection } from "../../api/client";
import {
  chamberLabel,
  chamberShortfallSentence,
  decreePreviewSentence,
  failingVoteAdvice,
  formatAmount,
  formatCommitted,
  routeLabel,
} from "../../format/format";
import { DataTable, EmptyNote, Panel, ToneValue } from "../components";

export function ConsequencesPanel({
  preview,
  decreeOption = null,
}: {
  preview: PreviewProjection;
  /** Present only when THIS proposal kind may be decreed (`decreeAllowed`), with its own price. */
  decreeOption?: { cost: number } | null;
}) {
  const isDecree = preview.route === "decree";
  const failingChambers = preview.chambers.filter((chamber) => !chamber.carries);
  const capitalTerms: { label: string; value: number; testId?: string }[] = [
    { label: "Route cost", value: preview.route_capital_cost },
    { label: "Bargaining", value: preview.influence_capital },
    { label: "Cabinet", value: preview.cabinet_capital },
    { label: "Investment", value: preview.investment_capital },
    { label: "Leader bargain", value: preview.legislative_bargain_capital, testId: "bargain-capital" },
    { label: "Promise release", value: preview.promise_release_capital, testId: "promise-release-capital" },
  ];
  return (
    // `data-testid` matching the convention `turn-result-view`, `concern-cards` and `meeting-panel`
    // already set. Gate 4A3 Commit 4a needs to attribute a measured icon to the placement it sits in,
    // and "an icon on Decisions that is NOT inside the policy-card tabpanel" is an inference where a
    // named container is a fact.
    <div data-testid="consequences-panel" className="flex flex-col gap-4">
      <Panel title="Known before resolution" headingLevel={3} headingId="preview-result-heading">
        <p className="mb-3 text-xs text-parchment-200/60">
          This is an estimate, not a guarantee: it reflects the drafted decision as it stands
          right now, and resolving can still differ from this if the draft changes first.
        </p>

        {!preview.has_proposal ? (
          <EmptyNote>No policy proposal is drafted. Only investment (if any) would apply.</EmptyNote>
        ) : (
          <>
            <p className="mb-2 text-sm">
              Route: <span className="text-parchment-100">{routeLabel(preview.route)}</span>
            </p>
            {isDecree ? (
              <p data-testid="decree-preview" className="text-sm">
                <ToneValue tone={preview.affordable ? "positive" : "negative"}>
                  {decreePreviewSentence(preview)}
                </ToneValue>
              </p>
            ) : (
              <>
                {preview.chambers.length === 0 ? (
                  <EmptyNote>No legislative vote applies to this route.</EmptyNote>
                ) : (
                  <DataTable
                    caption="Expected vote, chamber by chamber"
                    columns={["Chamber", "Supporting", "Required", "Seats", "Carries"]}
                    rows={preview.chambers.map((chamber) => ({
                      key: chamber.chamber,
                      cells: [
                        chamberLabel(chamber.chamber),
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
                {!preview.would_pass && failingChambers.length > 0 ? (
                  <div data-testid="failing-vote-advice" className="mt-2 text-sm">
                    <ul className="list-disc pl-5">
                      {failingChambers.map((chamber) => (
                        <li key={chamber.chamber}>{chamberShortfallSentence(chamber)}</li>
                      ))}
                    </ul>
                    <p className="mt-1 text-parchment-200/80">{failingVoteAdvice(decreeOption)}</p>
                  </div>
                ) : null}
              </>
            )}
          </>
        )}

        {/* Gate 4A3 UX-1: only the terms this draft actually spends are listed -- seven zeros read as
            noise -- and the total is always shown. */}
        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-parchment-200/70 sm:grid-cols-4">
          {capitalTerms
            .filter((term) => term.value !== 0)
            .map((term) => (
              <div key={term.label}>
                <dt>{term.label}</dt>
                <dd data-testid={term.testId} className="text-parchment-100">
                  {formatAmount(term.value)}
                </dd>
              </div>
            ))}
          <div>
            <dt>Total committed</dt>
            <dd className="text-parchment-100">{formatAmount(preview.committed_capital)}</dd>
          </div>
        </dl>
        {/* Deliberately OUTSIDE the committed-capital list and labelled as such. An assistance
            grant is money RECEIVED, in the fiscal account, not political capital spent — putting it
            in the grid above would invite a player to read it as part of the total, and the field's
            own docstring draws exactly that distinction. */}
        <p className="mt-2 text-xs text-parchment-200/70">
          Foreign assistance expected:{" "}
          <span data-testid="assistance-estimate" className="text-parchment-100">
            {formatAmount(preview.foreign_assistance_estimate)}
          </span>{" "}
          — money received, not political capital committed.
        </p>
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
