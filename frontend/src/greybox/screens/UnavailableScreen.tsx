/**
 * Gate 4A2 — the honest placeholder for Government, Economy, Legislature,
 * Constitution, and Relationships. `DashboardProjection` gives only five
 * SUMMARY concern cards; the real API builds no per-institution,
 * per-chamber, per-bloc, or per-budget-line breakdown, so these five screens
 * cannot render real detail yet. Rendering fabricated numbers here would be
 * exactly the "client computes/invents a value the server never returned"
 * problem Gate 4A2 exists to avoid -- an honest "not available in this gate"
 * state is the correct alternative, not an error and not silently fabricated
 * content.
 */

import { Panel } from "../components";
import type { ScreenProps } from "../registry";

export function UnavailableScreen({ heading, navigate }: ScreenProps & { heading: string }) {
  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        {heading}
      </h2>
      <Panel title="Not available in this gate">
        <p className="text-sm text-parchment-200/80">
          The dashboard's summary card for this topic is available now. A detailed breakdown
          screen for {heading.toLowerCase()} has not been built yet.
        </p>
        <button
          type="button"
          onClick={() => navigate("dashboard")}
          className="mt-3 rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          Back to Dashboard
        </button>
      </Panel>
    </div>
  );
}
