/**
 * Gate 4A2 — the decision composer, preview, and resolve. Options come from
 * `/api/game/decision-options` (real bps/capital bounds, real seated blocs,
 * real constitutional axes -- nothing invented). The draft lives in Zustand
 * (`../../state/draft`) until Preview or Resolve is pressed; the payload sent
 * is always `buildDecisions(draft)` -- canonical order by construction, never
 * client-sorted after the fact.
 *
 * Preview is explicitly labelled an estimate (`PreviewProjection.estimate`
 * is always `true`) and never claims to guarantee a stochastic outcome
 * (election swing, coup, unrest, impeachment) -- those fields simply do not
 * exist on `PreviewProjection`, so there is nothing to accidentally display
 * as if they did.
 */

import { useState } from "react";

import { useDashboard, useDecisionOptions, usePreview, useResolve } from "../../api/queries";
import type { DecisionOptionsProjection, PreviewProjection } from "../../api/client";
import { ResolutionInProgressError, StaleRevisionError } from "../../api/errors";
import { formatAmount, formatBpsPercent, formatCommitted } from "../../format/format";
import { buildDecisions } from "../../state/buildDecisionSet";
import { useDraftStore } from "../../state/draft";
import { useSession } from "../../state/SessionContext";
import { ErrorPanel } from "../../status/ErrorPanel";
import { LoadingPanel } from "../../status/StatusPanels";
import { DataTable, EmptyNote, Panel, ToneValue } from "../components";
import type { ScreenProps } from "../registry";

type BlocOption = DecisionOptionsProjection["blocs"][number];

interface BlocActor {
  party_id: string;
  bloc_id: string;
  bloc_name: string;
  /** One entry per chamber this bloc holds seats in -- kept as separate
   * already-server-provided seat counts, never summed (the format boundary
   * forbids client-side chamber summing; two numbers shown side by side is
   * not the same claim as one number computed from them). */
  chambers: { chamber: string; seats: number }[];
}

/**
 * The server lists one `BlocOption` row PER CHAMBER a bloc holds seats in
 * (`build_decision_options` in `backend/app/api/projections.py`), but
 * `InfluenceAllocation`/investment both target a bloc globally by
 * `(party_id, bloc_id)` alone -- the same actor's lower- and upper-chamber
 * rows are the SAME target, not two. Rendering one editable input per raw
 * row would bind two table rows to the same underlying value (confusing,
 * and a duplicate React key besides); this groups the raw rows back into
 * one actor per unique `(party_id, bloc_id)` before any input is built.
 */
function groupBlocsByActor(blocs: readonly BlocOption[]): BlocActor[] {
  const byKey = new Map<string, BlocActor>();
  for (const bloc of blocs) {
    const key = `${bloc.party_id}/${bloc.bloc_id}`;
    const existing = byKey.get(key);
    if (existing) {
      existing.chambers.push({ chamber: bloc.chamber, seats: bloc.seats });
    } else {
      byKey.set(key, {
        party_id: bloc.party_id,
        bloc_id: bloc.bloc_id,
        bloc_name: bloc.bloc_name,
        chambers: [{ chamber: bloc.chamber, seats: bloc.seats }],
      });
    }
  }
  return [...byKey.values()];
}

function chamberSeatsText(chambers: { chamber: string; seats: number }[]): string {
  return chambers.map((entry) => `${entry.chamber} ${formatAmount(entry.seats)}`).join(" · ");
}

function PreviewPanel({ preview }: { preview: PreviewProjection }) {
  return (
    <Panel title="Preview (estimate)">
      <p className="mb-3 text-xs text-parchment-200/60">
        An estimate, not a guarantee. Excludes: {preview.excludes_stochastic_channels.join(", ")}.
      </p>
      {!preview.has_proposal ? (
        <EmptyNote>No policy proposal is drafted. Only investment (if any) would apply.</EmptyNote>
      ) : (
        <>
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
      <p className="mt-2 text-sm">
        {formatCommitted(preview.committed_capital, preview.opening_capital)}
        {" — "}
        <ToneValue tone={preview.affordable ? "positive" : "negative"}>
          {preview.affordable ? "affordable" : "exceeds available capital"}
        </ToneValue>
      </p>
    </Panel>
  );
}

export function DecisionsScreen({ navigate }: ScreenProps) {
  const { revision, setRevision } = useSession();
  const dashboard = useDashboard(revision);
  const options = useDecisionOptions(revision);
  const preview = usePreview();
  const resolve = useResolve();
  const draft = useDraftStore();
  const [confirming, setConfirming] = useState(false);

  // A concluded campaign disables Resolve proactively, before the player
  // builds a decision that could only ever be rejected: the dashboard's own
  // `terminal` field (the same one Dashboard/TerminalScreen read) is checked
  // here too, ahead of the composer, rather than relying solely on the
  // server's `game_concluded` 409 to surface after the fact.
  if (dashboard.data?.terminal) {
    const terminal = dashboard.data.terminal;
    return (
      <Panel title="The campaign has ended">
        <p>
          <ToneValue tone={terminal.bucket === "victory" ? "positive" : "negative"}>
            {terminal.headline}
          </ToneValue>
        </p>
        <p className="mt-2 text-sm text-parchment-200/70">
          No further turn can be resolved. Review the outcome instead.
        </p>
        <button
          type="button"
          onClick={() => navigate("terminal")}
          className="mt-3 rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          Go to Victory / Defeat
        </button>
      </Panel>
    );
  }

  if (options.isPending) {
    return <LoadingPanel label="Loading decision options…" />;
  }
  if (options.isError) {
    return <ErrorPanel error={options.error} onRefresh={() => options.refetch()} />;
  }
  const data = options.data;

  function handlePreview() {
    if (revision === null) {
      return;
    }
    preview.mutate({ revision, decisions: buildDecisions(draft) });
  }

  function handleResolve() {
    if (revision === null) {
      return;
    }
    resolve.mutate(
      { revision, decisions: buildDecisions(draft) },
      {
        onSuccess: (response) => {
          setRevision(response.dashboard.revision);
          draft.clearDraft();
          setConfirming(false);
          navigate("result");
        },
        // On EVERY failure the draft is left exactly as it was -- there is no
        // code path here that touches the draft store except the success
        // branch above.
      },
    );
  }

  const resolveError = resolve.error;
  const isStale = resolveError instanceof StaleRevisionError;
  const isBusy = resolveError instanceof ResolutionInProgressError;

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Decision workspace
      </h2>

      <Panel title="Policy proposal (one per turn)">
        <p className="mb-3 text-sm text-parchment-200/70">
          A budget and a constitutional amendment occupy the same slot. Choosing one replaces the
          other. Choosing neither is a legal no-proposal turn.
        </p>
        <div role="radiogroup" aria-label="Policy proposal" className="flex flex-wrap gap-3">
          {(["budget", "amendment"] as const).map((kind) => (
            <button
              key={kind}
              type="button"
              role="radio"
              aria-checked={draft.policySlot === kind}
              onClick={() => draft.setPolicySlot(draft.policySlot === kind ? null : kind)}
              className="rounded border border-navy-800 px-3 py-2 text-sm aria-checked:border-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
            >
              {kind === "budget" ? "Budget" : "Constitutional amendment"}
            </button>
          ))}
        </div>

        {draft.policySlot === "budget" ? (
          <div className="mt-4 flex flex-col gap-3">
            <p className="text-sm text-parchment-200/70">
              Tax rates ({formatBpsPercent(data.tax_rate_bps_minimum)}–
              {formatBpsPercent(data.tax_rate_bps_maximum)} allowed):
            </p>
            {(
              [
                ["personalIncomeRateBps", "Personal income"],
                ["corporateRateBps", "Corporate"],
                ["consumptionRateBps", "Consumption"],
              ] as const
            ).map(([field, label]) => (
              <label key={field} className="flex items-center justify-between gap-3 text-sm">
                <span>{label}</span>
                <input
                  type="number"
                  min={data.tax_rate_bps_minimum}
                  max={data.tax_rate_bps_maximum}
                  value={draft.budget[field] ?? ""}
                  onChange={(event) =>
                    draft.setBudgetRateTarget(
                      field,
                      event.target.value === "" ? undefined : Number(event.target.value),
                    )
                  }
                  className="w-28 rounded border border-navy-800 bg-navy-950 px-2 py-1 text-right"
                />
              </label>
            ))}

            <p className="mt-2 text-sm text-parchment-200/70">Spending targets:</p>
            {data.spending_categories.map((category) => (
              <label
                key={category.category}
                className="flex items-center justify-between gap-3 text-sm"
              >
                <span>
                  {category.category}{" "}
                  <span className="text-xs text-parchment-200/50">
                    (current {formatAmount(category.current_amount)})
                  </span>
                </span>
                <input
                  type="number"
                  min={0}
                  value={draft.budget.spendingUpdates[category.category] ?? ""}
                  onChange={(event) =>
                    draft.setBudgetSpendingTarget(
                      category.category,
                      event.target.value === "" ? undefined : Number(event.target.value),
                    )
                  }
                  className="w-32 rounded border border-navy-800 bg-navy-950 px-2 py-1 text-right"
                />
              </label>
            ))}

            <RouteAndInfluence
              route={draft.budget.route}
              decreeAvailable={data.decree_available}
              decreeCost={data.decree_legislative_capital_cost}
              onRoute={draft.setBudgetRoute}
              blocs={data.blocs}
              influence={draft.budget.influence}
              onInfluence={draft.setBudgetInfluence}
            />
          </div>
        ) : null}

        {draft.policySlot === "amendment" ? (
          <div className="mt-4 flex flex-col gap-3">
            {data.constitutional_axes.map((axis) => (
              <label
                key={axis.axis}
                className="flex items-center justify-between gap-3 text-sm"
              >
                <span>
                  {axis.axis}{" "}
                  <span className="text-xs text-parchment-200/50">
                    (current {String(axis.current_value)})
                  </span>
                </span>
                {axis.allowed_values ? (
                  <select
                    value={String(draft.amendment.targets[axis.axis] ?? "")}
                    onChange={(event) =>
                      draft.setAmendmentTarget(
                        axis.axis,
                        event.target.value === "" ? undefined : event.target.value,
                      )
                    }
                    className="rounded border border-navy-800 bg-navy-950 px-2 py-1"
                  >
                    <option value="">— unchanged —</option>
                    {axis.allowed_values.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="number"
                    value={(() => {
                      const current = draft.amendment.targets[axis.axis];
                      return typeof current === "number" ? current : "";
                    })()}
                    onChange={(event) =>
                      draft.setAmendmentTarget(
                        axis.axis,
                        event.target.value === "" ? undefined : Number(event.target.value),
                      )
                    }
                    className="w-28 rounded border border-navy-800 bg-navy-950 px-2 py-1 text-right"
                  />
                )}
              </label>
            ))}

            <RouteAndInfluence
              route={draft.amendment.route}
              decreeAvailable={data.decree_available}
              decreeCost={data.decree_amendment_capital_cost}
              onRoute={draft.setAmendmentRoute}
              blocs={data.blocs}
              influence={draft.amendment.influence}
              onInfluence={draft.setAmendmentInfluence}
            />
          </div>
        ) : null}
      </Panel>

      <Panel title="Relationship investment (separate slot)">
        <p className="mb-3 text-sm text-parchment-200/70">
          Not part of the policy slot. Range: {data.relationship_investment_minimum}–
          {data.relationship_investment_maximum} per bloc.
        </p>
        {data.blocs.length === 0 ? (
          <EmptyNote>No blocs are available to invest in.</EmptyNote>
        ) : (
          <DataTable
            caption="Blocs available for relationship investment"
            columns={["Bloc", "Seats by chamber", "Investment"]}
            rows={groupBlocsByActor(data.blocs).map((actor) => {
              const key = `${actor.party_id}/${actor.bloc_id}`;
              return {
                key,
                cells: [
                  actor.bloc_name,
                  chamberSeatsText(actor.chambers),
                  <input
                    key="inv"
                    type="number"
                    min={0}
                    max={data.relationship_investment_maximum}
                    aria-label={`Relationship investment for ${actor.bloc_name}`}
                    value={draft.investments[key] ?? ""}
                    onChange={(event) =>
                      draft.setInvestment(
                        actor.party_id,
                        actor.bloc_id,
                        event.target.value === "" ? undefined : Number(event.target.value),
                      )
                    }
                    className="w-24 rounded border border-navy-800 bg-navy-950 px-2 py-1 text-right"
                  />,
                ],
              };
            })}
          />
        )}
      </Panel>

      <Panel title="Preview and resolve">
        <p className="mb-2 text-sm">Opening capital: {formatAmount(data.opening_capital)}</p>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            disabled={preview.isPending}
            onClick={handlePreview}
            className="rounded border border-navy-800 px-3 py-1 text-sm disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            {preview.isPending ? "Previewing…" : "Preview"}
          </button>
          <button
            type="button"
            disabled={resolve.isPending}
            onClick={() => setConfirming(true)}
            className="rounded border border-gold-600 px-3 py-1 text-sm disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            {resolve.isPending ? "Resolving…" : "Resolve turn"}
          </button>
        </div>

        {preview.isError ? <ErrorPanel error={preview.error} /> : null}
        {preview.isSuccess ? <PreviewPanel preview={preview.data} /> : null}

        {confirming ? (
          <div className="mt-4 rounded border border-gold-600 p-3">
            <p className="mb-2 text-sm">
              Confirm resolving this turn with {buildDecisions(draft).length} decision(s)
              committed.
            </p>
            <div className="flex gap-3">
              <button
                type="button"
                disabled={resolve.isPending}
                onClick={handleResolve}
                className="rounded border border-gold-600 px-3 py-1 text-sm disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
              >
                Confirm and resolve
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : null}

        {resolve.isError ? (
          <div className="mt-3">
            <ErrorPanel
              error={resolveError}
              onRetry={isBusy ? handleResolve : undefined}
              onRefresh={isStale ? () => options.refetch() : undefined}
            />
          </div>
        ) : null}
      </Panel>
    </div>
  );
}

function RouteAndInfluence({
  route,
  decreeAvailable,
  decreeCost,
  onRoute,
  blocs,
  influence,
  onInfluence,
}: {
  route: "legislative" | "decree";
  decreeAvailable: boolean;
  decreeCost: number;
  onRoute: (route: "legislative" | "decree") => void;
  blocs: readonly BlocOption[];
  influence: Record<string, number>;
  onInfluence: (partyId: string, blocId: string, politicalCapital: number | undefined) => void;
}) {
  return (
    <div className="mt-2 flex flex-col gap-3">
      <div role="radiogroup" aria-label="Route" className="flex gap-3 text-sm">
        <button
          type="button"
          role="radio"
          aria-checked={route === "legislative"}
          onClick={() => onRoute("legislative")}
          className="rounded border border-navy-800 px-3 py-1 aria-checked:border-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          Legislative vote
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={route === "decree"}
          disabled={!decreeAvailable}
          onClick={() => onRoute("decree")}
          className="rounded border border-navy-800 px-3 py-1 aria-checked:border-gold-500 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          Decree ({formatAmount(decreeCost)} capital){!decreeAvailable ? " — unavailable" : ""}
        </button>
      </div>

      {route === "legislative" && blocs.length > 0 ? (
        <div>
          <p className="mb-1 text-sm text-parchment-200/70">Influence (whip a bloc's vote):</p>
          <DataTable
            caption="Influence allocations"
            columns={["Bloc", "Seats by chamber", "Capital"]}
            rows={groupBlocsByActor(blocs).map((actor) => {
              const key = `${actor.party_id}/${actor.bloc_id}`;
              return {
                key,
                cells: [
                  actor.bloc_name,
                  chamberSeatsText(actor.chambers),
                  <input
                    key="inf"
                    type="number"
                    min={0}
                    aria-label={`Influence capital for ${actor.bloc_name}`}
                    value={influence[key] ?? ""}
                    onChange={(event) =>
                      onInfluence(
                        actor.party_id,
                        actor.bloc_id,
                        event.target.value === "" ? undefined : Number(event.target.value),
                      )
                    }
                    className="w-24 rounded border border-navy-800 bg-navy-950 px-2 py-1 text-right"
                  />,
                ],
              };
            })}
          />
        </div>
      ) : null}
    </div>
  );
}
