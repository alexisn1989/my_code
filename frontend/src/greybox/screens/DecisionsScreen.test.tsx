/**
 * Gate 4A2 -- proves the mandate's "terminal state disables Resolve and
 * directs to the terminal screen" guarantee holds on the actual composer
 * screen, not just by inspection: when the dashboard's `terminal` field is
 * set, DecisionsScreen must never render a Resolve control, and must offer a
 * way to reach the terminal screen instead. When the campaign is still
 * active, the ordinary composer (with its Resolve button) must render.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DecisionsScreen } from "./DecisionsScreen";
import { SessionProvider } from "../../state/SessionContext";

const ACTIVE_DASHBOARD = {
  revision: "rev-1",
  country_name: "Testland",
  turn: 3,
  terminal: null,
};

const CONCLUDED_DASHBOARD = {
  revision: "rev-1",
  country_name: "Testland",
  turn: 9,
  terminal: { bucket: "defeat", headline: "The government collapsed.", reason_label: "Collapse", turn: 9 },
};

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

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

function renderScreen(dashboard: unknown) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/game/state")) {
      return Promise.resolve(jsonResponse(dashboard));
    }
    if (url.includes("/api/game/decision-options")) {
      return Promise.resolve(jsonResponse(DECISION_OPTIONS));
    }
    throw new Error(`unexpected fetch: ${url}`);
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <SessionProvider>{children}</SessionProvider>
      </QueryClientProvider>
    );
  }

  return render(<DecisionsScreen navigate={vi.fn()} />, { wrapper: Wrapper });
}

describe("DecisionsScreen and terminal state", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("disables Resolve entirely and directs to the terminal screen once the campaign has concluded", async () => {
    renderScreen(CONCLUDED_DASHBOARD);

    await waitFor(() => expect(screen.getByText("The campaign has ended")).toBeInTheDocument());

    expect(screen.queryByRole("button", { name: /resolve turn/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /go to victory \/ defeat/i })).toBeInTheDocument();
  });

  it("renders the ordinary composer, with a Resolve control, while the campaign is still active", async () => {
    renderScreen(ACTIVE_DASHBOARD);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /resolve turn/i })).toBeInTheDocument(),
    );
    expect(screen.queryByText("The campaign has ended")).not.toBeInTheDocument();
  });
});
