/**
 * Gate 4A2 -- React Query hook behaviour that the mandate calls out
 * explicitly and that a component-level test would only exercise
 * incidentally: a successful resolve REPLACES cache data (never predicts
 * it) and invalidates history/saves/decision-options; a FAILED resolve or
 * load touches no cache at all, which is what "draft/game state retained on
 * every failure" actually rests on structurally, one layer below the
 * screens that consume these hooks.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  dashboardQueryKey,
  decisionOptionsQueryKey,
  historyQueryKey,
  liveTurnResultQueryKey,
  savesQueryKey,
  useLoadGame,
  useNewGame,
  useResolve,
} from "./queries";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

const OLD_REVISION = "rev-old";
const NEW_REVISION = "rev-new";

const DASHBOARD_BEFORE = { revision: OLD_REVISION, country_name: "Testland", turn: 1 };
const DASHBOARD_AFTER = { revision: NEW_REVISION, country_name: "Testland", turn: 2 };
const TURN_RESULT = { turn: 1, outcome_headline: "It passed", outcome_tone: "positive" };

describe("useResolve", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("on success, seeds the new dashboard and live turn result, and invalidates history/saves/decisionOptions -- never predicting a value locally", async () => {
    const client = makeClient();
    client.setQueryData(dashboardQueryKey(OLD_REVISION), DASHBOARD_BEFORE);
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, { turnResult: TURN_RESULT, dashboard: DASHBOARD_AFTER }),
    );

    const { result } = renderHook(() => useResolve(), { wrapper: wrapperFor(client) });
    result.current.mutate({ revision: OLD_REVISION, decisions: [] });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // The NEW revision's dashboard cache entry holds exactly what the server
    // returned -- not a value computed from the old one.
    expect(client.getQueryData(dashboardQueryKey(NEW_REVISION))).toEqual(DASHBOARD_AFTER);
    expect(client.getQueryData(liveTurnResultQueryKey())).toEqual(TURN_RESULT);
    // The OLD revision's cache entry is untouched -- a still-mounted consumer
    // keyed on it does not silently see the new turn's data.
    expect(client.getQueryData(dashboardQueryKey(OLD_REVISION))).toEqual(DASHBOARD_BEFORE);

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: historyQueryKey() });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: savesQueryKey() });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: decisionOptionsQueryKey(NEW_REVISION) });
  });

  it("on failure (e.g. stale_revision), writes NOTHING to the cache -- the prior dashboard stays exactly as it was", async () => {
    const client = makeClient();
    client.setQueryData(dashboardQueryKey(OLD_REVISION), DASHBOARD_BEFORE);

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(409, {
        type: "stale_revision",
        title: "stale_revision",
        status: 409,
        detail: "moved on",
        fields: [],
        extra: { expected: NEW_REVISION, actual: OLD_REVISION },
      }),
    );

    const { result } = renderHook(() => useResolve(), { wrapper: wrapperFor(client) });
    result.current.mutate({ revision: OLD_REVISION, decisions: [] });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(client.getQueryData(dashboardQueryKey(OLD_REVISION))).toEqual(DASHBOARD_BEFORE);
    expect(client.getQueryData(dashboardQueryKey(NEW_REVISION))).toBeUndefined();
    expect(client.getQueryData(liveTurnResultQueryKey())).toBeUndefined();
  });
});

describe("useLoadGame", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("a failed load leaves the currently displayed game's cache entry exactly as it was", async () => {
    const client = makeClient();
    client.setQueryData(dashboardQueryKey(OLD_REVISION), DASHBOARD_BEFORE);

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(404, {
        type: "save_not_found",
        title: "save_not_found",
        status: 404,
        detail: "no such save",
        fields: [],
        extra: {},
      }),
    );

    const { result } = renderHook(() => useLoadGame(), { wrapper: wrapperFor(client) });
    result.current.mutate({ saveId: "does-not-exist" });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(client.getQueryData(dashboardQueryKey(OLD_REVISION))).toEqual(DASHBOARD_BEFORE);
  });

  it("a successful load seeds the loaded game's dashboard", async () => {
    const client = makeClient();
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, DASHBOARD_AFTER));

    const { result } = renderHook(() => useLoadGame(), { wrapper: wrapperFor(client) });
    result.current.mutate({ saveId: "save-1" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(client.getQueryData(dashboardQueryKey(NEW_REVISION))).toEqual(DASHBOARD_AFTER);
  });
});

describe("useNewGame", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("on success seeds the new game's dashboard and invalidates saves/history", async () => {
    const client = makeClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, DASHBOARD_BEFORE));

    const { result } = renderHook(() => useNewGame(), { wrapper: wrapperFor(client) });
    result.current.mutate({ scenarioId: "scenario-1" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(client.getQueryData(dashboardQueryKey(OLD_REVISION))).toEqual(DASHBOARD_BEFORE);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: savesQueryKey() });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: historyQueryKey() });
  });
});
