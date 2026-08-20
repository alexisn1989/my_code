/**
 * Gate 4A2 — every structured API error, rendered as a specific, actionable
 * panel rather than a raw message. `role="alert"` on every branch so a
 * screen reader announces the failure without the player having to find it.
 *
 * Behaviour per the mandate's error-behaviour list:
 *   - `stale_revision`: explains that another tab/session advanced the game,
 *     offers a "Refresh" action that REFETCHES rather than auto-resubmits,
 *     and never touches the caller's draft.
 *   - `resolution_in_progress`: explains a resolution is already running and
 *     offers Retry; the draft is untouched either way.
 *   - `decision_rejected` (422): names the invalid decision from the
 *     server's own `detail`/`fields`, never silently repaired or reordered.
 *   - `game_concluded`: explains the campaign ended and points at History.
 *   - persistence/internal failure: states the resolve failed and that the
 *     previous dashboard is unchanged -- never implies partial progress.
 *   - `NetworkError`: a recoverable "could not reach the local server"
 *     message, distinct from every mapped API failure.
 */

import type { ReactNode } from "react";

import {
  ApiError,
  DecisionRejectedError,
  GameConcludedError,
  NetworkError,
  ResolutionInProgressError,
  StaleRevisionError,
} from "../api/errors";

function Alert({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div
      role="alert"
      className="rounded border border-red-900/60 bg-red-950/40 p-4 text-sm text-parchment-100"
    >
      <p className="font-semibold">{title}</p>
      <div className="mt-1 text-parchment-200/80">{children}</div>
    </div>
  );
}

export function ErrorPanel({
  error,
  onRetry,
  onRefresh,
}: {
  error: unknown;
  /** Retries the SAME request (e.g. after `resolution_in_progress`). */
  onRetry?: () => void;
  /** Refetches current server state without resubmitting anything (the only
   * legal response to `stale_revision`). */
  onRefresh?: () => void;
}) {
  if (error instanceof NetworkError) {
    return (
      <Alert title="Could not reach the local server">
        <p>
          Check that <code>mandate-gui</code> is still running. Your game state is unchanged.
        </p>
      </Alert>
    );
  }

  if (error instanceof StaleRevisionError) {
    return (
      <Alert title="Another session advanced the game">
        <p>
          The game moved to revision {error.expected} while this view still showed{" "}
          {error.actual}. Your draft has been kept, but it needs to be checked against the current
          state before you can resolve again.
        </p>
        {onRefresh ? (
          <button
            type="button"
            onClick={onRefresh}
            className="mt-2 rounded border border-navy-800 px-3 py-1 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Refresh to the current state
          </button>
        ) : null}
      </Alert>
    );
  }

  if (error instanceof ResolutionInProgressError) {
    return (
      <Alert title="Already resolving">
        <p>Another action is being resolved for this session. Your draft has been kept.</p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 rounded border border-navy-800 px-3 py-1 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Try again
          </button>
        ) : null}
      </Alert>
    );
  }

  if (error instanceof DecisionRejectedError) {
    return (
      <Alert title="That decision was rejected">
        <p>{error.detail ?? error.message}</p>
        {error.fields.length > 0 ? (
          <ul className="mt-2 list-disc pl-5">
            {error.fields.map((field) => (
              <li key={field.path}>
                <code className="text-xs">{field.path}</code>: {field.message}
              </li>
            ))}
          </ul>
        ) : null}
      </Alert>
    );
  }

  if (error instanceof GameConcludedError) {
    return (
      <Alert title="The campaign has already ended">
        <p>No further turn can be resolved. Review the outcome on the terminal screen.</p>
      </Alert>
    );
  }

  if (error instanceof ApiError) {
    if (error.status >= 500) {
      return (
        <Alert title="That turn could not be saved">
          <p>{error.detail ?? "The server failed to persist the result. Nothing changed."}</p>
        </Alert>
      );
    }
    return (
      <Alert title={error.title !== "" ? error.title : "Request failed"}>
        <p>{error.detail ?? error.message}</p>
      </Alert>
    );
  }

  return (
    <Alert title="Something went wrong">
      <p>{error instanceof Error ? error.message : "An unexpected error occurred."}</p>
    </Alert>
  );
}
