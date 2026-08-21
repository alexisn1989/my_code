/**
 * Gate 4A2 closeout -- mandate testing item 16: nullable election/survival
 * fields render safely. `ConcernCard.delta_text` (used by the Survival card
 * before any assessment has run) and `DashboardProjection.terminal` are both
 * `| null` on the generated schema; this pins that a null value renders as
 * an absent element (or an honest label), never as the literal string
 * "null"/"undefined" and never a render crash.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardScreen } from "./DashboardScreen";
import { SessionProvider, useSession } from "../../state/SessionContext";

function concern(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    label: "Survival",
    headline: "Not yet assessed",
    delta_text: null,
    direction: "unchanged",
    tone: "neutral",
    detail_screen: "constitution",
    ...overrides,
  };
}

const DASHBOARD_NO_TERMINAL_NO_DELTA = {
  revision: "rev-1",
  turn: 0,
  country_name: "Testland",
  government_form: "Monarchical, unlimited decree authority",
  next_election_label: "No election scheduled",
  concerns: {
    money: concern({ label: "Money", headline: "100000000.00" }),
    legitimacy: concern({ label: "Legitimacy", headline: "60.00%" }),
    legislature: concern({ label: "Legislature", headline: "2 parties, 100 seats" }),
    constitution: concern({ label: "Constitution", headline: "Supermajority" }),
    survival: concern({ label: "Survival", headline: "Not yet assessed", delta_text: null }),
  },
  goal: { headline: "Nothing is pressing.", detail: null },
  map: { note: "presentation only", tint_metric_label: "Legitimacy" },
  political_capital: { display: "500 / 1000" },
  alerts: [],
  terminal: null,
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

function SetRevision({ children }: { children: ReactNode }) {
  const { setRevision, revision } = useSession();
  useEffect(() => {
    if (revision === null) {
      setRevision("rev-1");
    }
  }, [revision, setRevision]);
  return revision === null ? null : <>{children}</>;
}

function renderDashboard(dashboard: unknown) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    if (String(input).includes("/api/game/state")) return Promise.resolve(jsonResponse(dashboard));
    throw new Error(`unexpected fetch: ${String(input)}`);
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <SessionProvider>
          <SetRevision>{children}</SetRevision>
        </SessionProvider>
      </QueryClientProvider>
    );
  }

  return render(<DashboardScreen navigate={vi.fn()} />, { wrapper: Wrapper });
}

describe("DashboardScreen: nullable election/survival fields", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a null survival delta_text and null terminal safely -- no crash, no literal 'null'/'undefined' text", async () => {
    renderDashboard(DASHBOARD_NO_TERMINAL_NO_DELTA);

    await waitFor(() => expect(screen.getByText("Not yet assessed")).toBeInTheDocument());

    expect(screen.queryByText("null")).not.toBeInTheDocument();
    expect(screen.queryByText("undefined")).not.toBeInTheDocument();
    expect(screen.queryByText("NaN")).not.toBeInTheDocument();
    // No terminal banner when the campaign is still active.
    expect(screen.queryByText("The campaign has ended")).not.toBeInTheDocument();
  });

  it("renders a real terminal outcome once the field is populated", async () => {
    const concluded = {
      ...DASHBOARD_NO_TERMINAL_NO_DELTA,
      terminal: { bucket: "defeat", headline: "The government collapsed.", reason_label: "Collapse", turn: 9 },
    };
    renderDashboard(concluded);

    await waitFor(() => expect(screen.getByText("The campaign has ended")).toBeInTheDocument());
    expect(screen.getByText("The government collapsed.")).toBeInTheDocument();
  });
});

describe("DashboardScreen: Save As", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls /api/game/save-as with the entered name, and confirms success without exposing a filesystem path", async () => {
    let saveAsBody: unknown;
    renderDashboard(DASHBOARD_NO_TERMINAL_NO_DELTA);
    await waitFor(() => expect(screen.getByLabelText("Save name")).toBeInTheDocument());

    // renderDashboard's own mock only knows /api/game/state; override it here
    // with the fuller one this test actually needs, now that the initial
    // dashboard fetch has already resolved.
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return Promise.resolve(jsonResponse(DASHBOARD_NO_TERMINAL_NO_DELTA));
      if (url.includes("/api/game/save-as") && init?.method === "POST") {
        saveAsBody = JSON.parse(String(init.body));
        return Promise.resolve(
          jsonResponse({
            save_id: "save-1",
            display_name: "My Campaign",
            scenario_id: "tiny_valid",
            current_turn: 0,
            loadable: true,
          }),
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    fireEvent.change(screen.getByLabelText("Save name"), { target: { value: "My Campaign" } });
    fireEvent.click(screen.getByRole("button", { name: "Save As" }));

    await waitFor(() => expect(screen.getByText(/Saved as/)).toBeInTheDocument());
    expect(saveAsBody).toEqual({ display_name: "My Campaign" });
    expect(screen.getByText(/Saved as/).textContent).not.toMatch(/\/|\\|save-1/);
  });

  it("disables Save As until a name is entered", async () => {
    renderDashboard(DASHBOARD_NO_TERMINAL_NO_DELTA);
    await waitFor(() => expect(screen.getByRole("button", { name: "Save As" })).toBeDisabled());

    fireEvent.change(screen.getByLabelText("Save name"), { target: { value: "  " } });
    expect(screen.getByRole("button", { name: "Save As" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Save name"), { target: { value: "Real Name" } });
    expect(screen.getByRole("button", { name: "Save As" })).not.toBeDisabled();
  });
});
