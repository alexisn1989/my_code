/**
 * React Query hooks over `./client` -- the ONE place server state is fetched
 * and cached. Every hook here owns exactly the server data the mandate lists
 * as React Query's: scenarios, the current dashboard, decision options,
 * preview, resolution, history, saves. Nothing here is optimistic: a mutation
 * never predicts a new dashboard/turn value locally, it only invalidates or
 * replaces query data with what the server actually returned.
 *
 * Query keys follow the frozen plan's Sec 14.1 shape: `["state", revision]` /
 * `["history", turn, revision]`, so a resolve (which changes the revision)
 * naturally addresses a different cache entry than the one before it, and
 * `dashboardQueryKey`/`historyDetailQueryKey` are exported so mutations can
 * target the right key without re-deriving it.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  api,
  type Decision,
  type ResolveResponse,
  type SaveSummary,
} from "./client";
import { nextGeneration } from "../format/format";

/** No game loaded yet -- distinct from "loading" or "errored". Callers branch
 * on this via `NoActiveSessionError`, not on a magic revision value. */
export const NO_REVISION = null;

export function scenariosQueryKey() {
  return ["scenarios"] as const;
}

export function useScenarios() {
  return useQuery({
    queryKey: scenariosQueryKey(),
    queryFn: api.listScenarios,
  });
}

export function savesQueryKey() {
  return ["saves"] as const;
}

export function useSaves() {
  return useQuery({
    queryKey: savesQueryKey(),
    queryFn: api.listSaves,
  });
}

/** `revision` is included in the key so a stale-revision recovery (a plain
 * refetch after `/state`'s own revision moves) is a normal cache miss, not a
 * special case. `null` means "no active session is known yet" -- the initial
 * query, before any revision has been observed. */
export function dashboardQueryKey(revision: string | null) {
  return ["dashboard", revision] as const;
}

export function useDashboard(revision: string | null, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: dashboardQueryKey(revision),
    queryFn: api.getState,
    enabled: options?.enabled ?? true,
  });
}

export function decisionOptionsQueryKey(revision: string | null) {
  return ["decisionOptions", revision] as const;
}

export function useDecisionOptions(revision: string | null, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: decisionOptionsQueryKey(revision),
    queryFn: api.getDecisionOptions,
    enabled: options?.enabled ?? true,
  });
}

export function historyQueryKey() {
  return ["history"] as const;
}

export function useHistory(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: historyQueryKey(),
    queryFn: api.listHistory,
    enabled: options?.enabled ?? true,
  });
}

/**
 * No API response carries a stable "which loaded game is this" identity --
 * `revision` changes on every resolve, which is exactly why it is the WRONG
 * key for campaign-static data like the strategic map (keying on it would
 * refetch the map every turn for no reason). This is a small client-side
 * monotonic counter instead: bumped only by `useNewGame`/`useLoadGame`'s
 * `onSuccess` below (never `useResolve`'s), using the existing cache
 * mechanism (`setQueryData`), not a second cache.
 */
export function gameGenerationQueryKey() {
  return ["gameGeneration"] as const;
}

export function useGameGeneration() {
  return useQuery({
    queryKey: gameGenerationQueryKey(),
    queryFn: () => 0,
    initialData: 0,
  });
}

/** The strategic map is authored, immutable content for the loaded campaign
 * (frozen plan Sec 12): it never changes after a game is started or loaded,
 * so it is keyed on the generation counter above, not `revision`, and
 * `staleTime: Infinity` documents that it is never refetched on its own. */
export function strategicMapQueryKey(generation: number) {
  return ["strategicMap", generation] as const;
}

export function useStrategicMap(generation: number, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: strategicMapQueryKey(generation),
    queryFn: api.getStrategicMap,
    enabled: options?.enabled ?? true,
    staleTime: Infinity,
  });
}

export function historyDetailQueryKey(turn: number) {
  return ["historyDetail", turn] as const;
}

export function useHistoryDetail(turn: number | null) {
  return useQuery({
    queryKey: historyDetailQueryKey(turn ?? -1),
    queryFn: () => api.getHistoryDetail(turn as number),
    enabled: turn !== null,
  });
}

/** The most recent LIVE resolve's `turnResult` -- seeded into the cache by
 * `useResolve`'s `onSuccess` below, read (never fetched) by the Turn Result
 * screen. This is the one piece of "the result of the turn I just resolved"
 * state that genuinely has no other query to key off of: it is not
 * `/game/state` (that is the post-turn dashboard, a different shape) and not
 * `/game/history/{turn}` (that is a re-fetch of a stored entry, appropriate
 * for reviewing an OLDER turn, not for the one just produced by this exact
 * response body -- Sec 4.10 of the frozen plan is explicit that the response
 * from `/resolve` already contains one). */
export function liveTurnResultQueryKey() {
  return ["turnResult", "live"] as const;
}

export function useLiveTurnResult() {
  return useQuery<Awaited<ReturnType<typeof api.resolve>>["turnResult"]>({
    queryKey: liveTurnResultQueryKey(),
    queryFn: () => {
      throw new Error("no turn has been resolved yet");
    },
    enabled: false,
    retry: false,
  });
}

/**
 * `/game/preview` is deliberately NOT cached across drafts: every keystroke
 * that changes the draft should score the CURRENT draft, not a memoized one.
 * `useMutation`, not `useQuery`, models that -- a preview is an action taken
 * against a specific draft, not a piece of state to keep fresh.
 */
export function usePreview(): UseMutationResult<
  Awaited<ReturnType<typeof api.preview>>,
  Error,
  { revision: string; decisions: readonly Decision[] }
> {
  return useMutation({
    mutationFn: ({ revision, decisions }) => api.preview(revision, decisions),
  });
}

/**
 * On success, the returned dashboard REPLACES query data directly
 * (`setQueryData`, not `invalidateQueries`) -- the response body is already
 * the authoritative new state, so there is nothing to refetch. History and
 * saves are invalidated (a new entry now exists), and the resolved dashboard
 * is also seeded under the OLD revision's ancestor query removed, so a
 * still-mounted consumer keyed on the prior revision does not keep re-reading
 * stale data from cache.
 */
export function useResolve(): UseMutationResult<
  ResolveResponse,
  Error,
  { revision: string; decisions: readonly Decision[] }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ revision, decisions }) => api.resolve(revision, decisions),
    onSuccess: (response) => {
      const newRevision = response.dashboard.revision;
      queryClient.setQueryData(dashboardQueryKey(newRevision), response.dashboard);
      queryClient.setQueryData(liveTurnResultQueryKey(), response.turnResult);
      queryClient.invalidateQueries({ queryKey: historyQueryKey() });
      queryClient.invalidateQueries({ queryKey: savesQueryKey() });
      queryClient.invalidateQueries({ queryKey: decisionOptionsQueryKey(newRevision) });
    },
  });
}

export function useNewGame(): UseMutationResult<
  Awaited<ReturnType<typeof api.newGame>>,
  Error,
  { scenarioId: string; seed?: number }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ scenarioId, seed }) => api.newGame(scenarioId, seed),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(dashboardQueryKey(dashboard.revision), dashboard);
      queryClient.invalidateQueries({ queryKey: savesQueryKey() });
      queryClient.invalidateQueries({ queryKey: historyQueryKey() });
      queryClient.setQueryData(gameGenerationQueryKey(), nextGeneration);
    },
  });
}

/**
 * A failed load must leave the CURRENTLY DISPLAYED game exactly as it was
 * (mandate: "Failed load leaves the current game displayed unchanged"). This
 * mutation therefore never touches query data on failure -- `onSuccess` is
 * the only place cache is written, so a rejected promise leaves every
 * existing `dashboard`/`decisionOptions` cache entry untouched, and whatever
 * revision the UI was already rendering keeps rendering it.
 */
export function useLoadGame(): UseMutationResult<
  Awaited<ReturnType<typeof api.loadGame>>,
  Error,
  { saveId: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ saveId }) => api.loadGame(saveId),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(dashboardQueryKey(dashboard.revision), dashboard);
      queryClient.invalidateQueries({ queryKey: historyQueryKey() });
      queryClient.setQueryData(gameGenerationQueryKey(), nextGeneration);
    },
  });
}

export function useSaveAs(): UseMutationResult<SaveSummary, Error, { displayName: string }> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ displayName }) => api.saveAs(displayName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: savesQueryKey() });
    },
  });
}

export type { UseQueryResult };
