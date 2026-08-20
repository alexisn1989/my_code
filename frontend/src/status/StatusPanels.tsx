import type { ReactNode } from "react";

/**
 * Gate 4A2 — the shared loading/empty states every live screen uses instead
 * of inventing its own. `aria-live="polite"` on the loading panel so a
 * screen reader announces a fetch in progress without interrupting whatever
 * the player was doing.
 */

export function LoadingPanel({ label }: { label: string }) {
  return (
    <p role="status" aria-live="polite" className="text-sm text-parchment-200/60">
      {label}
    </p>
  );
}

export function EmptyPanel({ children }: { children: ReactNode }) {
  return <p className="text-sm text-parchment-200/60">{children}</p>;
}
