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
  gameGenerationQueryKey,
  historyQueryKey,
  liveTurnResultQueryKey,
  savesQueryKey,
  strategicMapQueryKey,
  useGameGeneration,
  useLoadGame,
  usePreview,
  useNewGame,
  useResolve,
} from "./queries";
import { useDraftStore } from "../state/draft";

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
    result.current.mutate({ revision: OLD_REVISION, campaignId: "campaign-1", decisions: [] });

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
    result.current.mutate({ revision: OLD_REVISION, campaignId: "campaign-1", decisions: [] });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(client.getQueryData(dashboardQueryKey(OLD_REVISION))).toEqual(DASHBOARD_BEFORE);
    expect(client.getQueryData(dashboardQueryKey(NEW_REVISION))).toBeUndefined();
    expect(client.getQueryData(liveTurnResultQueryKey())).toBeUndefined();
  });

  it("does NOT bump the game generation counter -- the strategic map must not refetch on turn resolution", async () => {
    const client = makeClient();
    client.setQueryData(gameGenerationQueryKey(), 1);

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, { turnResult: TURN_RESULT, dashboard: DASHBOARD_AFTER }),
    );

    const { result } = renderHook(() => useResolve(), { wrapper: wrapperFor(client) });
    result.current.mutate({ revision: OLD_REVISION, campaignId: "campaign-1", decisions: [] });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(client.getQueryData(gameGenerationQueryKey())).toBe(1);
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

  it("bumps the game generation counter on success", async () => {
    const client = makeClient();
    client.setQueryData(gameGenerationQueryKey(), 1);
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, DASHBOARD_AFTER));

    const { result } = renderHook(() => useLoadGame(), { wrapper: wrapperFor(client) });
    result.current.mutate({ saveId: "save-1" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(client.getQueryData(gameGenerationQueryKey())).toBe(2);
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

  it("bumps the game generation counter on success", async () => {
    const client = makeClient();
    client.setQueryData(gameGenerationQueryKey(), 1);
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, DASHBOARD_BEFORE));

    const { result } = renderHook(() => useNewGame(), { wrapper: wrapperFor(client) });
    result.current.mutate({ scenarioId: "scenario-1" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(client.getQueryData(gameGenerationQueryKey())).toBe(2);
  });
});

/**
 * Campaign-scoped client state must not survive a campaign replacement.
 *
 * A draft belongs to the campaign it was drafted against, and the live turn result belongs to the
 * turn that produced it. Starting or loading a different campaign invalidates both: decisions
 * staged in campaign A must not be carried into B, and B's Result screen must not render A's
 * outcome -- which, for a campaign that ended, means rendering another campaign's ending.
 *
 * Asserted through the mutations rather than through the screens: `onSuccess` is where campaign
 * replacement is centrally known, so a second caller of these hooks inherits the behaviour instead
 * of having to remember it.
 */
describe("campaign replacement clears campaign-scoped client state", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    useDraftStore.getState().clearDraft();
    useDraftStore.setState({ dismissedHelp: false, glossaryOpen: false });
  });

  /** Stage a draft and a live turn result, as a player mid-campaign would have. */
  function stageCampaignState(client: QueryClient): void {
    useDraftStore.getState().setPolicySlot("budget");
    useDraftStore.getState().setBudgetRateTarget("personalIncomeRateBps", 2_500);
    useDraftStore.getState().setInvestment("party-1", "bloc-1", 5);
    client.setQueryData(liveTurnResultQueryKey(), TURN_RESULT);
  }

  function draftIsEmpty(): boolean {
    const draft = useDraftStore.getState();
    return (
      draft.policySlot === null &&
      draft.budget.personalIncomeRateBps === undefined &&
      Object.keys(draft.investments).length === 0
    );
  }

  it("a successful new game clears the staged draft and the previous live turn result", async () => {
    const client = makeClient();
    stageCampaignState(client);
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, DASHBOARD_BEFORE));

    const { result } = renderHook(() => useNewGame(), { wrapper: wrapperFor(client) });
    result.current.mutate({ scenarioId: "scenario-1" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(draftIsEmpty()).toBe(true);
    expect(client.getQueryData(liveTurnResultQueryKey())).toBeUndefined();
  });

  it("a successful load clears the staged draft and the previous live turn result", async () => {
    const client = makeClient();
    stageCampaignState(client);
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, DASHBOARD_AFTER));

    const { result } = renderHook(() => useLoadGame(), { wrapper: wrapperFor(client) });
    result.current.mutate({ saveId: "save-1" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(draftIsEmpty()).toBe(true);
    expect(client.getQueryData(liveTurnResultQueryKey())).toBeUndefined();
  });

  it("a FAILED load clears nothing -- the campaign on screen is still the one being played", async () => {
    const client = makeClient();
    stageCampaignState(client);
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

    expect(draftIsEmpty()).toBe(false);
    expect(client.getQueryData(liveTurnResultQueryKey())).toEqual(TURN_RESULT);
  });

  it("UI preferences are NOT campaign-scoped and survive a campaign change", async () => {
    const client = makeClient();
    useDraftStore.getState().dismissHelp();
    useDraftStore.getState().setGlossaryOpen(true);
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, DASHBOARD_BEFORE));

    const { result } = renderHook(() => useNewGame(), { wrapper: wrapperFor(client) });
    result.current.mutate({ scenarioId: "scenario-1" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(useDraftStore.getState().dismissedHelp).toBe(true);
    expect(useDraftStore.getState().glossaryOpen).toBe(true);
  });
});

/**
 * The map generation counter must never reset itself.
 *
 * The strategic map is campaign-static content cached with `staleTime: Infinity`, keyed on this
 * counter, and bumped only when the campaign is replaced. That makes the counter the only thing
 * standing between a campaign change and a map cached under the previous campaign's key -- and a
 * cache entry that is never refetched is never corrected, so a counter that reverts serves the
 * WRONG campaign's map with no path back.
 *
 * The defect only appears on a real remount: React Query refetches a stale entry when a new
 * observer subscribes, so a test that calls the hook once, or reads `getQueryData` directly, never
 * sees it. These mount, unmount and mount again against one shared client, exactly as navigating
 * away from the map screen and back does.
 */
describe("useGameGeneration", () => {
  it("survives an unmount and remount of its consumer without reverting", async () => {
    const client = makeClient();
    client.setQueryData(gameGenerationQueryKey(), 3);

    const first = renderHook(() => useGameGeneration(), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(first.result.current.data).toBe(3));
    first.unmount();

    const second = renderHook(() => useGameGeneration(), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(second.result.current.isFetching).toBe(false));

    expect(second.result.current.data).toBe(3);
    expect(client.getQueryData(gameGenerationQueryKey())).toBe(3);
  });

  it("never fetches, so nothing can overwrite a bumped counter with a computed one", async () => {
    const client = makeClient();
    client.setQueryData(gameGenerationQueryKey(), 2);

    const { result } = renderHook(() => useGameGeneration(), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(result.current.data).toBe(2));

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.isError).toBe(false);
  });

  it("keeps the strategic map keyed to the campaign that cached it", async () => {
    // The end-to-end statement: campaign one's map is cached under generation 0; a campaign
    // change bumps the key; remounting the map consumer must NOT land back on generation 0.
    const client = makeClient();
    client.setQueryData(strategicMapQueryKey(0), { map_id: "campaign-one-map" });

    vi.stubGlobal("fetch", vi.fn());
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, DASHBOARD_AFTER));
    const load = renderHook(() => useLoadGame(), { wrapper: wrapperFor(client) });
    load.result.current.mutate({ saveId: "save-2" });
    await waitFor(() => expect(load.result.current.isSuccess).toBe(true));
    vi.unstubAllGlobals();

    const generation = renderHook(() => useGameGeneration(), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(generation.result.current.isFetching).toBe(false));
    generation.unmount();
    const remounted = renderHook(() => useGameGeneration(), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(remounted.result.current.isFetching).toBe(false));

    expect(remounted.result.current.data).not.toBe(0);
    expect(client.getQueryData(strategicMapQueryKey(remounted.result.current.data))).toBeUndefined();
  });
});

/**
 * Every request that echoes a revision echoes the campaign it belongs to (review defect #1).
 *
 * `revision` alone says only WHEN a client's view was taken. Two campaigns sitting at the same
 * turn issue identical tokens, so the server now requires the campaign alongside it and refuses a
 * request built against a different one. These assert the wire payload, because that is the part
 * the server actually checks.
 */
describe("mutations carry the campaign the view belongs to", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function sentBody(): Record<string, unknown> {
    const call = vi.mocked(fetch).mock.calls.at(-1);
    const init = call?.[1] as RequestInit | undefined;
    return JSON.parse(String(init?.body)) as Record<string, unknown>;
  }

  it("useResolve sends campaign_id alongside the revision", async () => {
    const client = makeClient();
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(200, { turnResult: TURN_RESULT, dashboard: DASHBOARD_AFTER }),
    );

    const { result } = renderHook(() => useResolve(), { wrapper: wrapperFor(client) });
    result.current.mutate({ revision: OLD_REVISION, campaignId: "campaign-1", decisions: [] });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(sentBody()).toMatchObject({ revision: OLD_REVISION, campaign_id: "campaign-1" });
  });

  it("usePreview sends campaign_id alongside the revision", async () => {
    const client = makeClient();
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(200, { estimate: true }));

    const { result } = renderHook(() => usePreview(), { wrapper: wrapperFor(client) });
    result.current.mutate({ revision: OLD_REVISION, campaignId: "campaign-1", decisions: [] });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(sentBody()).toMatchObject({ revision: OLD_REVISION, campaign_id: "campaign-1" });
  });
});
