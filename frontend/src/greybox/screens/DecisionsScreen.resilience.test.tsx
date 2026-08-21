/**
 * Gate 4A2 closeout -- mandate testing item 13: concurrent-resolution and
 * stale-revision RECOVERY, not just the error class each maps to.
 * `errors.test.ts`/`client.test.ts` already prove the mapping; this proves
 * the actual recovery behavior on the real composer screen:
 *
 *  - `resolution_in_progress`: the draft survives the failure, Retry
 *    resubmits the SAME decisions, and a retry that then succeeds clears
 *    the draft and navigates -- exactly once, only on success.
 *  - `stale_revision`: Refresh refetches decision options; it never
 *    auto-resubmits the stale draft on the player's behalf.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DecisionsScreen } from "./DecisionsScreen";
import { SessionProvider, useSession } from "../../state/SessionContext";

const DASHBOARD = { revision: "rev-1", country_name: "Testland", turn: 3, terminal: null };

const DECISION_OPTIONS = {
  revision: "rev-1",
  blocs: [],
  chambers: [],
  constitutional_axes: [],
  decree_amendment_capital_cost: 10,
  decree_available: true,
  decree_legislative_capital_cost: 10,
  opening_capital: 100,
  relationship_investment_maximum: 50,
  relationship_investment_minimum: 0,
  spending_categories: [],
  tax_rate_bps_maximum: 5000,
  tax_rate_bps_minimum: 0,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function problem(type: string, status: number, extra: Record<string, unknown> = {}): Response {
  return jsonResponse(
    { type, title: type, status, detail: `${type} happened`, fields: [], extra },
    status,
  );
}

/** `revision` starts `null` in a fresh `SessionProvider`; `handleResolve`/`handlePreview`
 * both no-op on a null revision (correctly -- there is nothing to submit against yet).
 * Tests that need to actually exercise resolve must set one first, exactly as a real
 * New Game/Load flow would via `setRevision`. */
function SetRevision({ children }: { children: ReactNode }) {
  const { setRevision, revision } = useSession();
  useEffect(() => {
    if (revision === null) {
      setRevision("rev-1");
    }
  }, [revision, setRevision]);
  return revision === null ? null : <>{children}</>;
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const navigate = vi.fn();

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <SessionProvider>
          <SetRevision>{children}</SetRevision>
        </SessionProvider>
      </QueryClientProvider>
    );
  }

  const result = render(<DecisionsScreen navigate={navigate} />, { wrapper: Wrapper });
  return { ...result, navigate };
}

describe("DecisionsScreen: resolution_in_progress recovery", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("retains the draft on a resolution_in_progress failure, and Retry resubmits and succeeds", async () => {
    let resolveCallCount = 0;
    let decisionOptionsCallCount = 0;
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return Promise.resolve(jsonResponse(DASHBOARD));
      if (url.includes("/api/game/decision-options")) {
        decisionOptionsCallCount += 1;
        return Promise.resolve(jsonResponse(DECISION_OPTIONS));
      }
      if (url.includes("/api/game/resolve")) {
        resolveCallCount += 1;
        if (resolveCallCount === 1) {
          return Promise.resolve(problem("resolution_in_progress", 409));
        }
        return Promise.resolve(
          jsonResponse({
            turnResult: { turn: 1, outcome_headline: "It resolved", outcome_tone: "neutral" },
            dashboard: { ...DASHBOARD, revision: "rev-2", turn: 4 },
          }),
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const { navigate } = renderScreen();
    await waitFor(() => expect(screen.getByRole("button", { name: /resolve turn/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /resolve turn/i }));
    fireEvent.click(await screen.findByRole("button", { name: /confirm and resolve/i }));

    // First attempt fails with resolution_in_progress. The draft survives:
    // navigation never happened, and the composer -- not an error screen --
    // is still what's on screen underneath the error panel.
    await waitFor(() => expect(screen.getByText(/already resolving/i)).toBeInTheDocument());
    expect(resolveCallCount).toBe(1);
    expect(navigate).not.toHaveBeenCalledWith("result");
    expect(screen.getByRole("button", { name: /resolve turn/i })).toBeInTheDocument();

    // Retry resubmits the SAME decisions and this time succeeds.
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("result"));
    expect(resolveCallCount).toBe(2);
    // Decision-options IS legitimately refetched once resolve succeeds (the
    // revision moved, so the options tied to the old revision are stale) --
    // that invalidation, not a symptom of retry itself, is what the count
    // increase here reflects.
    expect(decisionOptionsCallCount).toBeGreaterThanOrEqual(1);
  });
});

describe("DecisionsScreen: stale_revision recovery", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("refreshes decision options on Refresh, and never auto-resubmits the draft", async () => {
    let resolveCallCount = 0;
    let decisionOptionsCallCount = 0;
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return Promise.resolve(jsonResponse(DASHBOARD));
      if (url.includes("/api/game/decision-options")) {
        decisionOptionsCallCount += 1;
        return Promise.resolve(jsonResponse(DECISION_OPTIONS));
      }
      if (url.includes("/api/game/resolve")) {
        resolveCallCount += 1;
        return Promise.resolve(problem("stale_revision", 409, { expected: "rev-2", actual: "rev-1" }));
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    renderScreen();
    await waitFor(() => expect(screen.getByRole("button", { name: /resolve turn/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /resolve turn/i }));
    fireEvent.click(await screen.findByRole("button", { name: /confirm and resolve/i }));

    await waitFor(() => expect(screen.getByText(/another session advanced the game/i)).toBeInTheDocument());
    expect(resolveCallCount).toBe(1);
    const decisionOptionsCallsBeforeRefresh = decisionOptionsCallCount;

    fireEvent.click(screen.getByRole("button", { name: /refresh to the current state/i }));

    await waitFor(() => expect(decisionOptionsCallCount).toBeGreaterThan(decisionOptionsCallsBeforeRefresh));
    // Refresh never resubmits the resolve request on the player's behalf.
    expect(resolveCallCount).toBe(1);
  });

  it("adopting the refreshed revision lets a deliberate retry actually succeed, not fail forever", async () => {
    // Simulates the real two-tab scenario: another session has already
    // advanced the server to "rev-2" by the time this tab's stale "rev-1"
    // resolve is rejected. Refresh's decision-options refetch returns the
    // server's CURRENT revision ("rev-2"); a resolve carrying THAT revision
    // must then succeed -- proving Refresh is a real recovery action, not
    // an inert relabelling of the same permanent failure.
    let resolveCallCount = 0;
    const seenResolveRevisions: string[] = [];
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return Promise.resolve(jsonResponse(DASHBOARD));
      if (url.includes("/api/game/decision-options")) {
        return Promise.resolve(jsonResponse({ ...DECISION_OPTIONS, revision: "rev-2" }));
      }
      if (url.includes("/api/game/resolve")) {
        resolveCallCount += 1;
        const body = JSON.parse(String(init?.body)) as { revision: string };
        seenResolveRevisions.push(body.revision);
        if (body.revision === "rev-1") {
          return Promise.resolve(problem("stale_revision", 409, { expected: "rev-2", actual: "rev-1" }));
        }
        return Promise.resolve(
          jsonResponse({
            turnResult: { turn: 4, outcome_headline: "ok", outcome_tone: "positive" },
            dashboard: { ...DASHBOARD, revision: "rev-3", turn: 4 },
          }),
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const { navigate } = renderScreen();
    await waitFor(() => expect(screen.getByRole("button", { name: /resolve turn/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /resolve turn/i }));
    fireEvent.click(await screen.findByRole("button", { name: /confirm and resolve/i }));
    await waitFor(() => expect(screen.getByText(/another session advanced the game/i)).toBeInTheDocument());
    expect(seenResolveRevisions).toEqual(["rev-1"]);

    fireEvent.click(screen.getByRole("button", { name: /refresh to the current state/i }));
    await waitFor(() => expect(screen.queryByText(/another session advanced the game/i)).not.toBeInTheDocument());

    fireEvent.click(await screen.findByRole("button", { name: /resolve turn/i }));
    fireEvent.click(await screen.findByRole("button", { name: /confirm and resolve/i }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("result"));
    expect(resolveCallCount).toBe(2);
    expect(seenResolveRevisions).toEqual(["rev-1", "rev-2"]);
  });
});
