/**
 * Gate 4A3 UX-3 (U10) — the concern cards, as ONE component.
 *
 * The Dashboard's five summary cards each link "Details" to a screen (`ConcernCard.detail_screen`).
 * Three of those screens -- Economy, Legislature, Constitution -- have no full version in this game,
 * so a player who followed the link used to land on a page that said only that. `ConcernSummaries`
 * puts the card they followed at the top of that destination (and Legitimacy and Survival at the top
 * of Government), so every link lands on what it was linked for.
 *
 * The SAME component renders the Dashboard grid and the destination summaries, from the SAME
 * revision-keyed dashboard projection: nothing is recomputed, and the two cannot drift. It keeps the
 * `concern-cards` test id because it is the same grid; the icon-coverage spec's placement and
 * backdrop expectation for it therefore hold wherever it appears.
 */

import type { DashboardProjection } from "../api/client";
import { useDashboard } from "../api/queries";
import { useSession } from "../state/SessionContext";
import { Panel, ToneValue } from "./components";
import type { ScreenId } from "./types";

type Concern = DashboardProjection["concerns"]["money"];

/** The five concerns in the Dashboard's own order. */
export function concernsOf(dashboard: DashboardProjection): Concern[] {
  return [
    dashboard.concerns.money,
    dashboard.concerns.legitimacy,
    dashboard.concerns.legislature,
    dashboard.concerns.constitution,
    dashboard.concerns.survival,
  ];
}

export function ConcernCardGrid({
  concerns,
  navigate,
}: {
  concerns: readonly Concern[];
  /** When given, each card links "Details" to its `detail_screen`; omitted on a destination screen,
   * where the link would point at the page the player is already on. */
  navigate?: (screen: ScreenId) => void;
}) {
  return (
    <div data-testid="concern-cards" className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
      {concerns.map((concern) => (
        <Panel key={concern.label} title={concern.label}>
          <p className="text-xl tabular-nums">
            <ToneValue tone={concern.tone}>{concern.headline}</ToneValue>
          </p>
          {concern.delta_text ? (
            <p className="mt-1 text-xs text-parchment-200/70">{concern.delta_text}</p>
          ) : null}
          {navigate === undefined ? null : (
            <button
              type="button"
              onClick={() => navigate(concern.detail_screen as ScreenId)}
              aria-label={`Details: ${concern.label}`}
              className="mt-2 text-xs underline focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
            >
              Details
            </button>
          )}
        </Panel>
      ))}
    </div>
  );
}

/** Every concern whose Details link points at `screen`, read from the current dashboard. Renders
 * nothing without a campaign or before the dashboard has loaded -- a destination screen's own
 * content stands on its own either way. */
export function ConcernSummaries({ screen }: { screen: ScreenId }) {
  const { revision } = useSession();
  const dashboard = useDashboard(revision, { enabled: revision !== null });
  if (revision === null || !dashboard.data) {
    return null;
  }
  const concerns = concernsOf(dashboard.data).filter((concern) => concern.detail_screen === screen);
  if (concerns.length === 0) {
    return null;
  }
  return (
    <section aria-labelledby={`concern-summary-${screen}`} data-testid="concern-summaries">
      <h3
        id={`concern-summary-${screen}`}
        className="mb-3 font-[family-name:var(--font-display)] text-lg text-parchment-100"
      >
        Summary
      </h3>
      <ConcernCardGrid concerns={concerns} />
    </section>
  );
}
