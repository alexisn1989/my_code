/**
 * Gate 4A2 — Turn Result, live. Reads the most recent resolve's `turnResult`
 * from the cache `useResolve` seeded (`../../api/queries`'s
 * `liveTurnResultQueryKey`) and renders it through the SAME `TurnResultView`
 * the History detail screen uses -- one component, one presentation path.
 */

import { useLiveTurnResult } from "../../api/queries";
import { EmptyNote, Panel } from "../components";
import { TurnResultView } from "../TurnResultView";
import type { ScreenProps } from "../registry";

export function ResultScreen({ navigate }: ScreenProps) {
  const liveResult = useLiveTurnResult();

  if (!liveResult.data) {
    return (
      <div className="flex flex-col gap-6">
        <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
          Turn result
        </h2>
        <Panel title="No turn has been resolved yet">
          <EmptyNote>Resolve a turn from the Decision workspace to see a result here.</EmptyNote>
          <button
            type="button"
            onClick={() => navigate("decisions")}
            className="mt-3 rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Go to Decision workspace
          </button>
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Turn result
      </h2>
      <TurnResultView result={liveResult.data} context="live" />
      {liveResult.data.terminal ? (
        <Panel title="This turn ended the campaign">
          <button
            type="button"
            onClick={() => navigate("terminal")}
            className="rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Review the outcome
          </button>
        </Panel>
      ) : (
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => navigate("dashboard")}
            className="rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Back to Dashboard
          </button>
          <button
            type="button"
            onClick={() => navigate("history")}
            className="rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Review history
          </button>
        </div>
      )}
    </div>
  );
}
