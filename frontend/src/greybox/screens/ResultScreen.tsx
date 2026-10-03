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
      {/* On the concluding turn `TurnResultView` already renders the "This turn ended the campaign"
          panel with the headline. This used to wrap the button in a SECOND Panel with the identical
          title, so the page carried two adjacent headings saying the same thing -- found by the
          Gate 4A3 Commit 5b T21 walkthrough, the first test to reach this branch in a browser. The
          action is now a plain button row, exactly like the branch below. */}
      {liveResult.data.terminal ? (
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => navigate("terminal")}
            className="rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Review the outcome
          </button>
        </div>
      ) : (
        // Gate 4A3 UX-3 (U5): the next thing to do is play the next turn, so that is the primary
        // action. `turn` is the turn this result PRODUCED -- the state's turn after resolution, the
        // same number the national header now shows -- so it names the turn being planned with no
        // arithmetic here.
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => navigate("decisions")}
            className="rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Plan turn {liveResult.data.turn}
          </button>
          <button
            type="button"
            onClick={() => navigate("dashboard")}
            className="rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
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
