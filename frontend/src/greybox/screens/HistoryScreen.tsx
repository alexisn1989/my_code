/**
 * Gate 4A2 — History: the timeline from `/api/game/history`, and per-turn
 * detail from `/api/game/history/{turn}` rendered through the SAME
 * `TurnResultView` the live Turn Result screen uses. Selecting a turn only
 * ever fetches that turn's stored detail -- it never reads or mutates the
 * active game's current state (`useHistoryDetail` is a plain read-only
 * query, and nothing on this screen calls a mutation).
 */

import { useState } from "react";

import { useHistory, useHistoryDetail } from "../../api/queries";
import { useSession } from "../../state/SessionContext";
import { ErrorPanel } from "../../status/ErrorPanel";
import { LoadingPanel } from "../../status/StatusPanels";
import { EmptyNote, Panel } from "../components";
import { TurnResultView } from "../TurnResultView";
import type { ScreenProps } from "../registry";

export function HistoryScreen(_props: ScreenProps) {
  const { revision } = useSession();
  const history = useHistory({ enabled: revision !== null });
  const [selectedTurn, setSelectedTurn] = useState<number | null>(null);
  const detail = useHistoryDetail(selectedTurn);

  if (history.isPending) {
    return <LoadingPanel label="Loading history…" />;
  }
  if (history.isError) {
    return <ErrorPanel error={history.error} onRefresh={() => history.refetch()} />;
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        History
      </h2>

      <Panel title="Timeline">
        {history.data.length === 0 ? (
          <EmptyNote>No turns have been resolved yet.</EmptyNote>
        ) : (
          <ul className="flex flex-col gap-2">
            {history.data.map((entry) => (
              <li key={entry.turn}>
                <button
                  type="button"
                  aria-pressed={selectedTurn === entry.turn}
                  onClick={() => setSelectedTurn(entry.turn)}
                  className="w-full rounded border border-navy-800 px-3 py-2 text-left text-sm aria-pressed:border-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                >
                  Turn {entry.turn} — {entry.outcome_line}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {selectedTurn === null ? null : detail.isPending ? (
        <LoadingPanel label={`Loading turn ${selectedTurn}…`} />
      ) : detail.isError ? (
        <ErrorPanel error={detail.error} onRefresh={() => detail.refetch()} />
      ) : (
        <TurnResultView result={detail.data.turnResult} context="history" />
      )}
    </div>
  );
}
