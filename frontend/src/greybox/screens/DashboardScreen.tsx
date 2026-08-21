/**
 * Gate 4A2 — Dashboard, over the real `DashboardProjection`: five summary
 * concern cards, alerts, goal, the presentation-only map placeholder, and
 * terminal state when present. Every field here is a projection field;
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
import { useSession } from "../../state/SessionContext";
import { ErrorPanel } from "../../status/ErrorPanel";
import { LoadingPanel } from "../../status/StatusPanels";
import { EmptyNote, Panel, ToneValue } from "../components";
import type { ScreenProps } from "../registry";
import type { ScreenId } from "../types";

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
          className="w-64 rounded border border-navy-800 bg-navy-950 px-2 py-1"
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
        <p role="status" aria-live="polite" className="mt-3 text-sm text-emerald-300">
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
  const concerns = [
    data.concerns.money,
    data.concerns.legitimacy,
    data.concerns.legislature,
    data.concerns.constitution,
    data.concerns.survival,
  ];

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

      <Panel title="Your current priority">
        <p>{data.goal.headline}</p>
        {data.goal.detail ? (
          <p className="mt-1 text-sm text-parchment-200/70">{data.goal.detail}</p>
        ) : null}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <Panel title={data.country_name}>
          <div
            data-testid="map-placeholder"
            role="img"
            aria-label={`Stylised outline of ${data.country_name}. Presentation only.`}
            className="flex h-48 items-center justify-center rounded border border-dashed border-navy-800 bg-navy-950 text-parchment-200/40"
          >
            map placeholder
          </div>
          <p className="mt-2 text-xs text-parchment-200/60">{data.map.note}</p>
          <p className="mt-1 text-xs text-parchment-200/60">
            Presentation only — tinted by {data.map.tint_metric_label}.
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
                    {alert.severity}
                  </span>
                  <p>{alert.headline}</p>
                  {alert.detail ? <p className="text-parchment-200/70">{alert.detail}</p> : null}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div data-testid="concern-cards" className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
        {concerns.map((concern) => (
          <Panel key={concern.label} title={concern.label}>
            <p className="text-xl tabular-nums">
              <ToneValue tone={concern.tone}>{concern.headline}</ToneValue>
            </p>
            {concern.delta_text ? (
              <p className="mt-1 text-xs text-parchment-200/70">{concern.delta_text}</p>
            ) : null}
            <button
              type="button"
              onClick={() => navigate(concern.detail_screen as ScreenId)}
              className="mt-2 text-xs underline focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
            >
              Details
            </button>
          </Panel>
        ))}
      </div>

      <div className="flex gap-3">
        <button
          type="button"
          onClick={() => navigate("decisions")}
          className="rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          Build a decision
        </button>
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
