/**
 * Gate 4A2 — Dashboard, over the real `DashboardProjection`: five summary
 * concern cards, alerts, goal, the national tint, and terminal state when
 * present. Every field here is a projection field;
 * nothing is recomputed.
 *
 * Also the one place a player can Save As: `useSaveAs` was already fully
 * wired to the backend (api/queries.ts) but had no UI control anywhere --
 * found while proving the two-tab stale-revision recovery experience
 * through the actual browser UI, since a second tab has no other honest way
 * to reach the same revision as the first (SessionContext's revision is set
 * only by New Game / Load / a successful Resolve, never by simply viewing
 * the dashboard). Dashboard is the natural home for it: the one gameplay
 * screen every active campaign returns to.
 */

import { useState } from "react";

import { useDashboard, useSaveAs } from "../../api/queries";
import { formatBpsPercent, tintAccessibleName, tintCaption, tintFill } from "../../format/format";
import { useSession } from "../../state/SessionContext";
import { ErrorPanel } from "../../status/ErrorPanel";
import { LoadingPanel } from "../../status/StatusPanels";
import { ConcernCardGrid, concernsOf } from "../ConcernCards";
import { EmptyNote, Panel, ToneValue } from "../components";
import type { ScreenProps } from "../registry";
import { WIN_AND_LOSS_LINE } from "./GlossaryScreen";

const SEVERITY_LABEL: Record<"critical" | "warning" | "info", string> = {
  critical: "Critical",
  warning: "Warning",
  info: "Info",
};

function SaveAsPanel() {
  const [displayName, setDisplayName] = useState("");
  const saveAs = useSaveAs();

  return (
    <Panel title="Save this campaign">
      <label className="flex flex-col gap-1 text-sm" htmlFor="save-as-display-name">
        <span>Save name</span>
        <input
          id="save-as-display-name"
          type="text"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          // Finding V1: `w-64` was a FIXED 256px, and at the 320px conformance width the panel's own
          // padding leaves less room than that, so the label's box overflowed. `w-full max-w-64` keeps
          // the identical appearance wherever it fits and lets it shrink where it does not.
          className="w-full max-w-64 rounded border border-navy-800 bg-navy-950 px-2 py-1"
        />
      </label>
      <button
        type="button"
        disabled={saveAs.isPending || displayName.trim() === ""}
        onClick={() => saveAs.mutate({ displayName: displayName.trim() })}
        className="mt-3 rounded border border-navy-800 px-3 py-1 text-sm disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
      >
        {saveAs.isPending ? "Saving…" : "Save As"}
      </button>
      {saveAs.isError ? (
        <div className="mt-3">
          <ErrorPanel error={saveAs.error} />
        </div>
      ) : null}
      {saveAs.isSuccess ? (
        <p role="status" aria-live="polite" className="mt-3 text-sm text-success-400">
          Saved as &ldquo;{saveAs.data.display_name}&rdquo;. Load it from the Title screen.
        </p>
      ) : null}
    </Panel>
  );
}

export function DashboardScreen({ navigate }: ScreenProps) {
  const { revision } = useSession();
  const dashboard = useDashboard(revision);

  if (dashboard.isPending) {
    return <LoadingPanel label="Loading the dashboard…" />;
  }
  if (dashboard.isError) {
    return <ErrorPanel error={dashboard.error} onRefresh={() => dashboard.refetch()} />;
  }

  const data = dashboard.data;
  const concerns = concernsOf(data);

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        National dashboard
      </h2>

      {data.terminal ? (
        <Panel title="The campaign has ended">
          <p>
            <ToneValue tone={data.terminal.bucket === "victory" ? "positive" : "negative"}>
              {data.terminal.headline}
            </ToneValue>
          </p>
          <button
            type="button"
            onClick={() => navigate("terminal")}
            className="mt-2 rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Review the outcome
          </button>
        </Panel>
      ) : null}

      {/* Gate 4A3 UX-3 (U1): the stakes and the first action, in the panel a new player reads first.
          The goal itself still comes from the server; the stakes line is the Glossary's own copy. */}
      <Panel title="Your current priority">
        <p>{data.goal.headline}</p>
        {data.goal.detail ? (
          <p className="mt-1 text-sm text-parchment-200/70">{data.goal.detail}</p>
        ) : null}
        <p data-testid="win-and-loss" className="mt-2 text-sm text-parchment-200/80">
          {WIN_AND_LOSS_LINE}
        </p>
        <button
          type="button"
          onClick={() => navigate("decisions")}
          className="mt-3 rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          Build a decision
        </button>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        {/* Gate 4A3 UX-3 (U10): this box used to say "map placeholder" under a caption about
            "province-level mechanics" -- developer copy, and an aria-label describing an outline
            that was never drawn. It now draws what the projection actually carries: one national
            value as a tint, with the country's name on it. The server's `map.note` is deliberately
            not rendered; the caption is the player-facing equivalent, composed from the label. */}
        <Panel title={data.country_name}>
          <div
            data-testid="national-tint"
            data-tint-bps={data.map.tint_value_bps}
            role="img"
            aria-label={tintAccessibleName(
              data.country_name,
              data.map.tint_metric_label,
              formatBpsPercent(data.map.tint_value_bps),
            )}
            style={{ backgroundColor: tintFill(data.map.tint_value_bps) }}
            className="flex h-48 items-center justify-center rounded border border-navy-800"
          >
            {/* The name sits on its own navy-950 label rather than on the mix itself: every text
                backdrop in this interface is one of the palette's authored surfaces, an invariant
                the contrast sweeps assert (`verify-commit3-fixes`, `terminal-coverage`), and the
                tint is a graphic, not a text surface. */}
            <span
              aria-hidden="true"
              className="rounded bg-navy-950 px-3 py-1 font-[family-name:var(--font-display)] text-2xl text-parchment-100"
            >
              {data.country_name}
            </span>
          </div>
          <p className="mt-2 text-xs text-parchment-200/70">
            {tintCaption(data.map.tint_metric_label)}
          </p>
        </Panel>

        <Panel title="Alerts">
          {data.alerts.length === 0 ? (
            <EmptyNote>Nothing needs your attention this turn.</EmptyNote>
          ) : (
            <ul className="flex flex-col gap-3">
              {data.alerts.map((alert) => (
                <li key={alert.id} className="text-sm">
                  <span className="uppercase tracking-wide text-xs text-parchment-200/60">
                    {SEVERITY_LABEL[alert.severity]}
                  </span>
                  <p>{alert.headline}</p>
                  {alert.detail ? <p className="text-parchment-200/70">{alert.detail}</p> : null}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <ConcernCardGrid concerns={concerns} navigate={navigate} />

      <div className="flex gap-3">
        <button
          type="button"
          onClick={() => navigate("history")}
          className="rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          Review history
        </button>
      </div>

      <SaveAsPanel />
    </div>
  );
}
