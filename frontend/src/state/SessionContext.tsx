/**
 * The one piece of "which game am I looking at" state that lives above React
 * Query's own cache: the CURRENT revision, used to pick which
 * `["dashboard", revision]` / `["decisionOptions", revision]` cache entry is
 * active (frozen plan Sec 14.1's key shape). This is deliberately thin --
 * just a revision string and its setter -- so it is not a second copy of
 * authoritative state, only a pointer to which React Query entry currently
 * is.
 *
 * Every screen that starts, loads, or resolves a game calls `setRevision`
 * with the value the server actually returned, never a value it invented
 * or advanced itself.
 */

import { createContext, type ReactNode, useContext, useState } from "react";

interface SessionContextValue {
  revision: string | null;
  setRevision: (revision: string) => void;
  clearRevision: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [revision, setRevisionState] = useState<string | null>(null);
  const value: SessionContextValue = {
    revision,
    setRevision: setRevisionState,
    clearRevision: () => setRevisionState(null),
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
