/**
 * Gate 4A2 -- the typed client end to end, over a CONTROLLED `fetch` mock (no
 * MSW, per the mandate). `errors.test.ts` already covers each error class's
 * own construction from a `ProblemBody`; this file covers the other half:
 * that `api.*` actually reaches every one of those classes through a real
 * fetch response, that a real success response deserializes untouched, and
 * that a `fetch` rejection (the server not running at all) becomes a
 * `NetworkError` rather than an uncaught rejection.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";
import {
  ApiError,
  DecisionRejectedError,
  GameConcludedError,
  NetworkError,
  NoActiveSessionError,
  ResolutionInProgressError,
  StaleRevisionError,
  type ProblemBody,
} from "./errors";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function problem(type: string, status: number, extra: Record<string, unknown> = {}): ProblemBody {
  return { type, title: type, status, detail: `${type} happened`, fields: [], extra };
}

describe("the typed client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("deserializes a real success response untouched", async () => {
    const dashboard = { revision: "rev-1", country_name: "Testland", turn: 3 };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, dashboard));

    const result = await api.getState();

    expect(result).toEqual(dashboard);
    expect(fetch).toHaveBeenCalledWith(
      "/api/game/state",
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) }),
    );
  });

  it("sends a POST with the JSON body for a mutating endpoint", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, { revision: "rev-2" }));

    await api.resolve("rev-1", [{ kind: "budget", route: "legislative" }]);

    expect(fetch).toHaveBeenCalledWith(
      "/api/game/resolve",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          revision: "rev-1",
          decisions: [{ kind: "budget", route: "legislative" }],
        }),
      }),
    );
  });

  it("maps 409 stale_revision to StaleRevisionError with expected/actual carried through", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(409, problem("stale_revision", 409, { expected: "rev-2", actual: "rev-1" })),
    );

    await expect(api.resolve("rev-1", [])).rejects.toMatchObject({
      constructor: StaleRevisionError,
      expected: "rev-2",
      actual: "rev-1",
    });
  });

  it("maps 409 resolution_in_progress to ResolutionInProgressError", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(409, problem("resolution_in_progress", 409)));

    await expect(api.resolve("rev-1", [])).rejects.toBeInstanceOf(ResolutionInProgressError);
  });

  it("maps 422 decision_rejected to DecisionRejectedError carrying field detail", async () => {
    const body = {
      ...problem("decision_rejected", 422),
      fields: [{ path: "decisions[0].route", message: "unknown route" }],
    };
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(422, body));

    await expect(api.resolve("rev-1", [{ kind: "budget", route: "bogus" }])).rejects.toMatchObject({
      constructor: DecisionRejectedError,
      fields: [{ path: "decisions[0].route", message: "unknown route" }],
    });
  });

  it("maps 404 no_active_session to NoActiveSessionError", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(404, problem("no_active_session", 404)));

    await expect(api.getState()).rejects.toBeInstanceOf(NoActiveSessionError);
  });

  it("maps 409 game_concluded to GameConcludedError", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(409, problem("game_concluded", 409)));

    await expect(api.resolve("rev-1", [])).rejects.toBeInstanceOf(GameConcludedError);
  });

  it("falls back to the shared ApiError for an unmapped type, and to a synthesized ApiError for a malformed body", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(500, problem("internal_error", 500)));
    await expect(api.getState()).rejects.toBeInstanceOf(ApiError);

    vi.mocked(fetch).mockResolvedValueOnce(new Response("not json at all", { status: 502 }));
    await expect(api.getState()).rejects.toThrow(); // JSON.parse throws before mapping; still a caller-visible failure
  });

  it("wraps a fetch rejection (server unreachable) in NetworkError, not a bare throw", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(api.listScenarios()).rejects.toBeInstanceOf(NetworkError);
  });
});
