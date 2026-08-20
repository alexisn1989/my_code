/**
 * Gate 4A2 — Victory/Defeat, live. Reads `terminal` off the current
 * dashboard -- the same field `DashboardScreen` and `ResultScreen` already
 * check for `null`-ness. No Resolve action exists anywhere on this screen:
 * a concluded game cannot resolve a further turn (the server's own
 * `game_concluded` 409 is the authority; this screen simply never offers
 * the button in the first place).
 */

import { useDashboard } from "../../api/queries";
import { useSession } from "../../state/SessionContext";
import { ErrorPanel } from "../../status/ErrorPanel";
import { LoadingPanel } from "../../status/StatusPanels";
import { EmptyNote, Panel, ToneValue } from "../components";
import type { ScreenProps } from "../registry";

export function TerminalScreen({ navigate }: ScreenProps) {
  const { revision } = useSession();
  const dashboard = useDashboard(revision);

  if (dashboard.isPending) {
    return <LoadingPanel label="Loading…" />;
  }
  if (dashboard.isError) {
    return <ErrorPanel error={dashboard.error} onRefresh={() => dashboard.refetch()} />;
  }

  const terminal = dashboard.data.terminal;

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Victory / defeat
      </h2>

      {!terminal ? (
        <Panel title="The campaign is still active">
          <EmptyNote>No terminal outcome has been reached yet.</EmptyNote>
        </Panel>
      ) : (
        <Panel title={terminal.bucket === "victory" ? "Victory" : "Defeat"}>
          <p className="text-lg">
            <ToneValue tone={terminal.bucket === "victory" ? "positive" : "negative"}>
              {terminal.headline}
            </ToneValue>
          </p>
          <p className="mt-1 text-sm text-parchment-200/70">
            {terminal.reason_label}, turn {terminal.turn}
          </p>
        </Panel>
      )}

      <Panel title="What you can do now">
        <p className="mb-3 text-sm text-parchment-200/70">
          {terminal
            ? "The campaign is over. No further turn can be resolved."
            : "Review the campaign so far, or start a new one."}
        </p>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => navigate("title")}
            className="rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            New campaign
          </button>
          <button
            type="button"
            onClick={() => navigate("history")}
            className="rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Review history
          </button>
        </div>
      </Panel>
    </div>
  );
}
