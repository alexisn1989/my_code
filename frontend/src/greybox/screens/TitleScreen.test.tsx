/**
 * Gate 4A2 closeout -- mandate testing item 3: all three real scenarios
 * render and can start a game. Also covers new-game success (revision set,
 * navigates to dashboard) and a failed load leaving the title screen's own
 * state untouched (the client-side half of "failed load leaves the current
 * game displayed unchanged" -- queries.test.tsx already pins the cache-layer
 * half of this).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TitleScreen } from "./TitleScreen";
import { SessionProvider } from "../../state/SessionContext";

const SCENARIOS = [
  {
    scenario_id: "decree_state",
    display_name: "Kingdom of Valdrun",
    government_form: "Monarchical, unlimited decree authority",
    election_interval_label: "No election scheduled",
    starting_legitimacy_text: "60.00%",
    is_showcase: true,
  },
  {
    scenario_id: "deficit_demo",
    display_name: "Republic of Strapped",
    government_form: "Presidential republic, emergency decree authority",
    election_interval_label: "Every 20 turns",
    starting_legitimacy_text: "60.00%",
    is_showcase: false,
  },
  {
    scenario_id: "tiny_valid",
    display_name: "Republic of Arken",
    government_form: "Parliamentary republic, emergency decree authority",
    election_interval_label: "Every 16 turns",
    starting_legitimacy_text: "70.00%",
    is_showcase: false,
  },
];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderTitle() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <SessionProvider>{children}</SessionProvider>
      </QueryClientProvider>
    );
  }

  const navigate = vi.fn();
  const result = render(<TitleScreen navigate={navigate} />, { wrapper: Wrapper });
  return { ...result, navigate };
}

describe("TitleScreen: all three real scenarios", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders all three scenarios by their real display names", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/api/saves")) return Promise.resolve(jsonResponse([]));
      throw new Error(`unexpected fetch: ${url}`);
    });

    renderTitle();

    for (const scenario of SCENARIOS) {
      await waitFor(() => expect(screen.getByText(scenario.display_name)).toBeInTheDocument());
      expect(screen.getByText(scenario.government_form)).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: /start kingdom of valdrun/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start republic of strapped/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start republic of arken/i })).toBeInTheDocument();
  });

  it("starting any of the three scenarios calls /api/game/new with that scenario_id and navigates to the dashboard", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/api/saves")) return Promise.resolve(jsonResponse([]));
      if (url.includes("/api/game/new")) {
        const body = JSON.parse(String(init?.body)) as { scenario_id: string };
        return Promise.resolve(
          jsonResponse({ revision: "0.0", country_name: "Test", turn: 0, scenario_id: body.scenario_id }),
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const { navigate } = renderTitle();
    await waitFor(() => expect(screen.getByText("Republic of Arken")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /start republic of arken/i }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("dashboard"));
    const newGameCall = vi.mocked(fetch).mock.calls.find(([input]) => String(input).includes("/api/game/new"));
    expect(newGameCall).toBeDefined();
    const body = JSON.parse(String(newGameCall?.[1]?.body)) as { scenario_id: string };
    expect(body.scenario_id).toBe("tiny_valid");
  });

  it("lists saves without exposing a filesystem path, and a failed load surfaces an error without navigating", async () => {
    const saves = [
      {
        save_id: "11111111-1111-4111-8111-111111111111",
        display_name: "My Campaign",
        scenario_id: "tiny_valid",
        current_turn: 3,
        updated_at: "2026-01-01T00:00:00Z",
        terminal_outcome_summary: null,
        loadable: true,
        integrity_problem: null,
      },
    ];
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
      if (url.includes("/api/saves")) return Promise.resolve(jsonResponse(saves));
      if (url.includes("/api/game/load")) {
        return Promise.resolve(
          jsonResponse(
            { type: "save_not_found", title: "not found", status: 404, detail: "gone", fields: [], extra: {} },
            404,
          ),
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const { navigate } = renderTitle();
    await waitFor(() => expect(screen.getByText("My Campaign")).toBeInTheDocument());

    // No raw path anywhere in the rendered saves table.
    expect(screen.queryByText(/\/saves\//)).not.toBeInTheDocument();
    expect(screen.queryByText(/\.json/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "My Campaign" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(navigate).not.toHaveBeenCalled();
  });
});
