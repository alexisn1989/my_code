/**
 * Gate 4A2 -- regression for a real bug found during the manual walkthrough:
 * `/api/game/decision-options` lists one `BlocOption` row PER CHAMBER a bloc
 * holds seats in (`build_decision_options`, backend/app/api/projections.py),
 * so a bloc seated in both the lower and upper chamber appears TWICE with
 * the SAME `(party_id, bloc_id)`. `InfluenceAllocation`/investment both
 * target a bloc globally by that same pair (its own docstring says so), so
 * two raw rows are one editable target, not two -- rendering one input per
 * raw row bound two table rows to the same underlying value (confusing,
 * and a duplicate React list key besides). This pins the fix: the composer
 * groups raw rows back into one actor per unique bloc before building any
 * input, and shows each chamber's ALREADY-SERVER-PROVIDED seat count next
 * to it without summing them (summing chambers client-side is exactly what
 * the format boundary forbids).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DecisionsScreen } from "./DecisionsScreen";
import { SessionProvider } from "../../state/SessionContext";

const DASHBOARD = { revision: "rev-1", country_name: "Testland", turn: 3, terminal: null };

const DECISION_OPTIONS = {
  revision: "rev-1",
  blocs: [
    {
      party_id: "civic_union",
      party_name: "Civic Union",
      bloc_id: "mainstream",
      bloc_name: "Civic Union Mainstream",
      chamber: "lower",
      seats: 40,
    },
    {
      party_id: "civic_union",
      party_name: "Civic Union",
      bloc_id: "mainstream",
      bloc_name: "Civic Union Mainstream",
      chamber: "upper",
      seats: 24,
    },
  ],
  chambers: ["lower", "upper"],
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

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/game/state")) return Promise.resolve(jsonResponse(DASHBOARD));
    if (url.includes("/api/game/decision-options")) return Promise.resolve(jsonResponse(DECISION_OPTIONS));
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

describe("the relationship-investment table groups a bloc's chamber rows into one target", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders exactly one investment input for a bloc seated in two chambers, with both seat counts shown unsummed", async () => {
    renderScreen();

    await waitFor(() =>
      expect(screen.getByText("Civic Union Mainstream")).toBeInTheDocument(),
    );

    // Exactly one row -> exactly one editable investment amount for this bloc,
    // not one per raw (bloc, chamber) row from the server.
    const table = screen.getByRole("table", { name: /relationship investment/i });
    const investmentInputs = table.querySelectorAll('input[type="number"]');
    expect(investmentInputs).toHaveLength(1);

    // Both chambers' server-given seat counts are shown, unsummed (no "64").
    expect(screen.getByText(/lower 40/)).toBeInTheDocument();
    expect(screen.getByText(/upper 24/)).toBeInTheDocument();
    expect(screen.queryByText("64")).not.toBeInTheDocument();
  });
});
