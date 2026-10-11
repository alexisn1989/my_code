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

import { useDashboard, useGameGeneration, useSaveAs, useStrategicMap } from "../../api/queries";
import { useSession } from "../../state/SessionContext";
import { ErrorPanel } from "../../status/ErrorPanel";
import { LoadingPanel } from "../../status/StatusPanels";
import { ConcernCardGrid, concernsOf } from "../ConcernCards";
import { CountryMap, PlacesList } from "../map/CountryMap";
import { ObjectiveCard } from "../ObjectivePanels";
import { Panel, ToneValue } from "../components";
import type { ScreenProps } from "../registry";

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
  const generation = useGameGeneration();
  const strategicMap = useStrategicMap(generation.data, { enabled: revision !== null });

  if (dashboard.isPending) {
    return <LoadingPanel label="Loading the dashboard…" />;
  }
  if (dashboard.isError) {
    return <ErrorPanel error={dashboard.error} onRefresh={() => dashboard.refetch()} />;
  }

  const data = dashboard.data;
  const concerns = concernsOf(data);

  return (
    <div className="flex flex-col gap-4 sm:gap-6">
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

      {/* Gate 4A3 M-1: two compact cards side by side on wide screens, so the country comes forward.
          The priority card keeps the server's goal and the first action; the win-and-loss stakes are
          stated once, in the objective card (UX-3's U1 line, moved, not dropped). */}
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Panel title="Your current priority">
          <p>{data.goal.headline}</p>
          {data.goal.detail ? (
            <p className="mt-1 text-sm text-parchment-200/70">{data.goal.detail}</p>
          ) : null}
          <button
            type="button"
            onClick={() => navigate("decisions")}
            className="mt-3 rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Build a decision
          </button>
        </Panel>

        {/* Gate 4A3 victory path: the campaign objective, separate from the current priority. Its
            stage comes from the server, which derives it from the engine's own victory rule. */}
        <ObjectiveCard dashboard={data} navigate={navigate} />
      </div>

      {/* Gate 4A3 M-1: the country map, with the national tint as its title plate, and its
          ordinary twin, the Places list. (UX-3's U10 box -- one national value as a tint, with the
          country's name on it -- lives on as that plate; the server's developer-facing `map.note`
          is still not rendered.) */}
      <section aria-label="The country" className="flex flex-col gap-6">
        <Panel title="The country and its institutions">
          <CountryMap dashboard={data} map={strategicMap.data ?? null} navigate={navigate} />
        </Panel>
        <div className="rounded border border-navy-800 bg-navy-900 p-4">
          <PlacesList navigate={navigate} />
        </div>
      </section>

      {/* Alerts are shown when there are any; an empty panel repeated nothing useful. */}
      {data.alerts.length === 0 ? null : (
        <Panel title="Alerts">
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
        </Panel>
      )}

      {/* Gate 4A3 M-1: the five summary cards repeat the status bar's treasury and legitimacy, so on
          the Dashboard they are folded away (every Details link still inside). Each summary's own
          screen still shows its card openly. */}
      <details data-testid="national-summaries" className="rounded border border-navy-800 bg-navy-900 p-4">
        <summary className="cursor-pointer font-[family-name:var(--font-display)] text-lg text-parchment-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500">
          National summaries
        </summary>
        <div className="mt-3">
          <ConcernCardGrid concerns={concerns} navigate={navigate} />
        </div>
      </details>

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
