/**
 * The one piece of "which game am I looking at" state that lives above React
 * Query's own cache: the CURRENT revision, used to pick which
 * `["dashboard", revision]` / `["decisionOptions", revision]` cache entry is
 * active (frozen plan Sec 14.1's key shape). This is deliberately thin --
 * just a revision string and its setter -- so it is not a second copy of
 * authoritative state, only a pointer to which React Query entry currently
 * is.
 *
 * Every screen that starts, loads, or resolves a game calls `setCampaignView`
 * with the values the server actually returned, never values it invented
 * or advanced itself -- and always both together, because a revision means
 * nothing without the campaign it counts turns within.
 */

import { createContext, type ReactNode, useContext, useRef, useState } from "react";

import { usePreviewStore } from "./previewStore";

interface SessionContextValue {
  revision: string | null;
  /** WHICH campaign `revision` counts turns within (review defect #1).
   *
   * `revision` alone says only WHEN a view was taken. Two campaigns at the same turn issue
   * identical tokens, so without this a tab left open on one campaign could resolve a turn of
   * another. Every request that echoes a revision echoes this beside it. */
  campaignId: string | null;
  /** Adopt both together, and the ONLY way to adopt either.
   *
   * There is deliberately no revision-only setter: they are meaningful only as a pair, and a
   * fresh revision carried alongside a stale campaign id is exactly the stuck-tab state this
   * exists to prevent. Removing that setter removes the way to reach it. */
  setCampaignView: (revision: string, campaignId: string | null | undefined) => void;
  clearRevision: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [revision, setRevisionState] = useState<string | null>(null);
  const [campaignId, setCampaignId] = useState<string | null>(null);
  // Gate 4A3 M-2: the shared preview belongs to one view of one campaign. When the view actually
  // CHANGES, the preview's lifecycle token advances, so a response requested before the change is
  // dropped whenever it lands. Re-adopting the SAME view (a refresh that finds nothing new) keeps a
  // still-valid preview. A ref, not the rendered values: two calls in one tick must compare against
  // each other, not against a stale render.
  const view = useRef<{ revision: string | null; campaignId: string | null }>({ revision: null, campaignId: null });
  function adoptView(nextRevision: string | null, nextCampaignId: string | null): void {
    if (view.current.revision !== nextRevision || view.current.campaignId !== nextCampaignId) {
      usePreviewStore.getState().invalidate();
    }
    view.current = { revision: nextRevision, campaignId: nextCampaignId };
  }
  const value: SessionContextValue = {
    revision,
    campaignId,
    setCampaignView: (nextRevision, nextCampaignId) => {
      adoptView(nextRevision, nextCampaignId ?? null);
      setRevisionState(nextRevision);
      // `campaign_id` is optional in the generated type -- the projection declares it nullable
      // because `/scenarios` builds one campaign-less dashboard that never leaves the server.
      // Normalized to `null` here so callers hold one absent-value shape, not two.
      setCampaignId(nextCampaignId ?? null);
    },
    clearRevision: () => {
      adoptView(null, null);
      setRevisionState(null);
      setCampaignId(null);
    },
  };
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (context === null) {
    throw new Error("useSession must be used inside a SessionProvider");
  }
  return context;
}
