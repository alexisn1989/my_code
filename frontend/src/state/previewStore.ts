/**
 * Gate 4A3 M-2 — the ONE preview, shared by Decisions and Parliament.
 *
 * Until M-2 the preview lived in `DecisionsScreen`'s own `useMutation`, so it vanished when the
 * player left the screen and no other screen could read it. Parliament shows the same estimate, so
 * the estimate moves here, under rules that make a wrong one impossible to display:
 *
 * - **Every part names the request it belongs to.** The result, the error and the loading state each
 *   carry the signature of the draft they were asked for (`previewRequestSignature`), so a screen
 *   shows them only while the CURRENT draft has that signature (`previewView`). A delayed failure for
 *   a draft the player has since edited never appears as an error against the new draft.
 * - **Only the latest request may write.** `begin` issues a request id; `accept`/`fail` are dropped
 *   unless their token is the latest issued, so an older response landing after a newer one changes
 *   nothing.
 * - **A lifecycle token (`epoch`).** `invalidate` advances it and clears everything. It is called on
 *   every resolve, load and new game, and whenever the campaign view actually changes
 *   (`SessionProvider`). A response requested under an older epoch is dropped whatever its timing.
 * - **The latest attempt decides (the retry-display rule).** `begin` clears the stored error, so a
 *   retry hides the old error at once; a retry that FAILS hides the older result for the same draft,
 *   so a verdict is never shown beside an error for the same request.
 *
 * Kept free of React and of the API client so it can be unit-tested directly and imported by the
 * session provider without a cycle; `useDraftPreview` is the hook screens use.
 */

import { create } from "zustand";

import type { PreviewProjection } from "../api/client";
import { nextCount } from "../format/counters";

export interface PreviewToken {
  epoch: number;
  requestId: number;
  signature: string;
}

export interface PreviewEntry extends PreviewToken {
  data: PreviewProjection;
}

export interface PreviewFailure extends PreviewToken {
  error: Error;
}

export interface PreviewStoreState {
  epoch: number;
  latestRequestId: number;
  pending: PreviewToken | null;
  error: PreviewFailure | null;
  entry: PreviewEntry | null;
  begin: (signature: string) => PreviewToken;
  /** Writes only for the latest request of the current epoch; returns whether it wrote. */
  accept: (token: PreviewToken, data: PreviewProjection) => boolean;
  /** Writes only for the latest request of the current epoch; returns whether it wrote. */
  fail: (token: PreviewToken, error: Error) => boolean;
  invalidate: () => void;
  /** Back to the initial state (tests). */
  reset: () => void;
}

const INITIAL = { epoch: 0, latestRequestId: 0, pending: null, error: null, entry: null };

function isLatest(state: PreviewStoreState, token: PreviewToken): boolean {
  return token.epoch === state.epoch && token.requestId === state.latestRequestId;
}

export const usePreviewStore = create<PreviewStoreState>((set, get) => ({
  ...INITIAL,
  begin: (signature) => {
    const state = get();
    const token: PreviewToken = { epoch: state.epoch, requestId: nextCount(state.latestRequestId), signature };
    set({ latestRequestId: token.requestId, pending: token, error: null });
    return token;
  },
  accept: (token, data) => {
    if (!isLatest(get(), token)) return false;
    set({ entry: { ...token, data }, pending: null, error: null });
    return true;
  },
  fail: (token, error) => {
    if (!isLatest(get(), token)) return false;
    set({ error: { ...token, error }, pending: null });
    return true;
  },
  invalidate: () => set((state) => ({ epoch: nextCount(state.epoch), pending: null, error: null, entry: null })),
  reset: () => set({ ...INITIAL }),
}));

export interface PreviewView {
  /** The estimate for the current draft, or null. */
  current: PreviewProjection | null;
  /** The request id of `current` (so a screen can tell whether it asked for it). */
  currentRequestId: number | null;
  /** A result exists, but for a different draft than the current one. */
  stale: boolean;
  /** A request for the CURRENT draft is outstanding. */
  pendingForDraft: boolean;
  /** The failure of the latest request for the CURRENT draft, or null. */
  errorForDraft: Error | null;
}

/** What a screen may show for the draft whose signature is `signature`. Pure; derived at render. */
export function previewView(
  state: Pick<PreviewStoreState, "entry" | "error" | "pending">,
  signature: string,
): PreviewView {
  const { entry, error, pending } = state;
  const errorForDraft = error !== null && error.signature === signature ? error : null;
  const newerFailure =
    errorForDraft !== null && (entry === null || errorForDraft.requestId > entry.requestId);
  const current = entry !== null && entry.signature === signature && !newerFailure ? entry : null;
  return {
    current: current === null ? null : current.data,
    currentRequestId: current === null ? null : current.requestId,
    stale: entry !== null && entry.signature !== signature,
    pendingForDraft: pending !== null && pending.signature === signature,
    errorForDraft: errorForDraft === null ? null : errorForDraft.error,
  };
}
