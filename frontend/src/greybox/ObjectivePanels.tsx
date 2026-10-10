/**
 * Gate 4A3 victory path — the campaign objective, as the player reads it.
 *
 * Everything shown comes from `DashboardProjection.objective`, which the server derives from the
 * engine's own eligibility predicates and its recorded transition marker (`app/api/objective.py`).
 * Nothing here decides a stage, counts a condition or estimates support: the stage, the headline,
 * the "K of 3" text and every link are server fields. There is deliberately no progress bar or
 * percentage -- meeting the conditions is not victory, and the card says so in words.
 *
 * Two surfaces share these pieces: the Dashboard's "Your campaign objective" card and the
 * Constitution screen.
 */

import type { DashboardProjection } from "../api/client";
import { metText } from "../format/format";
import { Panel } from "./components";
import type { ScreenId } from "./types";

export type Objective = DashboardProjection["objective"];

/** The headline, its detail, and the two facts kept apart: conditions, and the recorded transition. */
export function ObjectiveSummary({ objective }: { objective: Objective }) {
  return (
    <div data-testid="objective-summary" data-stage={objective.stage} className="flex flex-col gap-1">
      <p data-testid="objective-headline" className="text-parchment-100">
        {objective.headline}
      </p>
      {objective.detail ? (
        <p className="text-sm text-parchment-200/80">{objective.detail}</p>
      ) : null}
      <ul className="mt-1 flex flex-col gap-0.5 text-sm text-parchment-200/80">
        <li data-testid="objective-conditions-text">{objective.conditions_text}</li>
        <li data-testid="objective-transition-text">{objective.transition_text}</li>
      </ul>
      {objective.election_note ? (
        <p data-testid="objective-election-note" className="text-sm text-parchment-200/70">
          {objective.election_note}
        </p>
      ) : null}
    </div>
  );
}

/** The three conditions as short met / not-yet words -- text, never colour alone. */
export function ConditionWords({ objective }: { objective: Objective }) {
  return (
    <ul data-testid="objective-condition-words" className="flex flex-col gap-0.5 text-sm">
      {objective.conditions.map((condition) => (
        <li key={condition.id} data-condition={condition.id} data-met={condition.met}>
          <span className="text-parchment-200/70">{condition.label}:</span>{" "}
          <span className="text-parchment-100">{metText(condition.met)}</span>
        </li>
      ))}
    </ul>
  );
}

/** The Dashboard card: persistent, separate from "Your current priority" (which stays the most
 * urgent problem), with one action -- "Review reforms" -- that opens the Constitution screen. */
export function ObjectiveCard({
  dashboard,
  navigate,
}: {
  dashboard: DashboardProjection;
  navigate: (screen: ScreenId) => void;
}) {
  const objective = dashboard.objective;
  return (
    <Panel title="Your campaign objective">
      <div data-testid="objective-card" data-stage={objective.stage} className="flex flex-col gap-3">
        <ObjectiveSummary objective={objective} />
        {objective.stage === "concluded" ? null : <ConditionWords objective={objective} />}
        {objective.stage === "qualifying_election" ? (
          // The existing survival and legitimacy headlines, reused as they are: no new estimate.
          <ul data-testid="objective-risks" className="flex flex-col gap-0.5 text-sm">
            {[dashboard.concerns.survival, dashboard.concerns.legitimacy].map((concern) => (
              <li key={concern.label}>
                <span className="text-parchment-200/70">{concern.label}:</span> {concern.headline}
              </li>
            ))}
          </ul>
        ) : null}
        {objective.stage === "concluded" ? null : (
          <div>
            <button
              type="button"
              onClick={() => navigate("constitution")}
              className="rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
            >
              Review reforms
            </button>
          </div>
        )}
      </div>
    </Panel>
  );
}
