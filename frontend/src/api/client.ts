/**
 * One typed fetch wrapper over the eleven real endpoints -- the only place
 * `fetch` is called for game data. Types come from `./schema` (generated,
 * never hand-edited); nothing here re-declares a response shape by hand.
 *
 * Same-origin only, deliberately: `mandate-gui` serves this SPA and the API
 * from one process on one port, so every request is a bare path with no base
 * URL to configure, matching `LocalSecurityMiddleware`'s same-origin design
 * (backend `app/api/security.py`).
 */

import { apiErrorFromUnknown, NetworkError } from "./errors";
import type { components } from "./schema";

type Schemas = components["schemas"];

export type ScenarioSummary = Schemas["ScenarioSummary"];
export type SaveSummary = Schemas["SaveSummary"];
export type DashboardProjection = Schemas["DashboardProjection"];
export type DecisionOptionsProjection = Schemas["DecisionOptionsProjection"];
export type PreviewProjection = Schemas["PreviewProjection"];
export type ResolveResponse = Schemas["ResolveResponse"];
export type HistoryListEntry = Schemas["HistoryListEntry"];
export type HistoryDetailResponse = Schemas["HistoryDetailResponse"];
export type TurnResultProjection = Schemas["TurnResultProjection"];
export type ChamberPreview = Schemas["ChamberPreview"];
export type ConcernCard = Schemas["ConcernCard"];
export type Alert = Schemas["Alert"];

/** A raw, unvalidated decision payload. The server's own reject-not-normalize
 * validators are the only authority on whether one is legal; this client
 * never inspects, sorts, or repairs the contents. `buildDecisionSet.ts` is
 * the one place a `Decision` object is actually constructed, in canonical
 * order by construction. */
export type Decision = Record<string, unknown>;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (cause) {
    throw new NetworkError(cause);
  }

  const text = await response.text();
  const parsed: unknown = text.length > 0 ? JSON.parse(text) : null;

  if (!response.ok) {
    throw apiErrorFromUnknown(response.status, parsed);
  }
  return parsed as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export const api = {
  listScenarios: (): Promise<ScenarioSummary[]> => request("/api/scenarios"),

  newGame: (scenarioId: string, seed?: number): Promise<DashboardProjection> =>
    postJson("/api/game/new", { scenario_id: scenarioId, seed: seed ?? null }),

  loadGame: (saveId: string): Promise<DashboardProjection> =>
    postJson("/api/game/load", { save_id: saveId }),

  saveAs: (displayName: string): Promise<SaveSummary> =>
    postJson("/api/game/save-as", { display_name: displayName }),

  getState: (): Promise<DashboardProjection> => request("/api/game/state"),

  getDecisionOptions: (): Promise<DecisionOptionsProjection> =>
    request("/api/game/decision-options"),

  preview: (revision: string, decisions: readonly Decision[]): Promise<PreviewProjection> =>
    postJson("/api/game/preview", { revision, decisions }),

  resolve: (revision: string, decisions: readonly Decision[]): Promise<ResolveResponse> =>
    postJson("/api/game/resolve", { revision, decisions }),

  listHistory: (): Promise<HistoryListEntry[]> => request("/api/game/history"),

  getHistoryDetail: (turn: number): Promise<HistoryDetailResponse> =>
    request(`/api/game/history/${turn}`),

  listSaves: (): Promise<SaveSummary[]> => request("/api/saves"),
};
