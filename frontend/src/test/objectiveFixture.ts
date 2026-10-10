/**
 * Gate 4A3 victory path: real `DashboardProjection.objective` values for every stage, for unit tests.
 *
 * `objective-stages.json` is the server's own output (`build_objective`) for states reached by real
 * resolved turns, and `backend/tests/test_objective_fixtures.py` fails if it ever differs from what
 * the backend now produces. Nothing here is hand-written.
 */

import type { DashboardProjection } from "../api/client";
import stages from "./objective-stages.json";

export type ObjectiveFixture = DashboardProjection["objective"];

export const OBJECTIVE_STAGES = stages as unknown as Record<
  | "reform"
  | "reformDeficitDemo"
  | "afterDecreeNone"
  | "qualifyingElection"
  | "concludedVictory"
  | "cannotQualifyMissingInterval"
  | "cannotQualifyAlreadyCompetitive"
  | "concludedElectoralDefeat"
  | "concludedTermLimitExit",
  ObjectiveFixture
>;

/** `DashboardProjection.objective` is required, so every dashboard fixture carries one: Valdrun's
 * opening state. */
export const OBJECTIVE_FIXTURE: ObjectiveFixture = OBJECTIVE_STAGES.reform;
