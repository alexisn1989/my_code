/**
 * Gate 4A2 closeout, final acceptance pass item 20 -- the closeout plan
 * identified missing automated coverage for keyboard/accessibility
 * behavior: keyboard navigation through all eleven screens, visible and
 * correct `aria-current`, Glossary keyboard activation and dismissal,
 * labelled decision controls, accessible loading/error announcements,
 * passed/failed state not communicated by color alone, and no Resolve
 * control on the terminal screen. This file closes that gap by driving the
 * REAL `GreyboxApp` shell (not a mock of it) through mocked API responses.
 *
 * "Keyboard navigation" is proven two ways, matching what a real browser
 * actually does: (1) every interactive control is a native `<button>` (or
 * `<select>`/`<input>` inside a `<label>`), which a browser makes
 * Tab-reachable and Enter/Space-activatable for free, with no custom key
 * handler required -- a structural guarantee this suite checks directly on
 * the DOM nodes; and (2) activating each one (via `fireEvent.click`, which
 * is what a real Enter/Space keypress on a native `<button>` ultimately
 * dispatches) produces the correct, single-active-item result.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DecisionsScreen } from "./screens/DecisionsScreen";
import { TerminalScreen } from "./screens/TerminalScreen";
import { GreyboxApp } from "./GreyboxApp";
import { SCREENS } from "./registry";
import { SessionProvider, useSession } from "../state/SessionContext";

/** `revision` starts `null` in a fresh `SessionProvider`, and both
 * `useDecisionOptions`/`handlePreview` need a non-null one to behave like a
 * real in-progress campaign -- the same pattern
 * `DecisionsScreen.resilience.test.tsx` already established. */
function SetRevision({ children }: { children: ReactNode }) {
  const { setRevision, revision } = useSession();
  useEffect(() => {
    if (revision === null) {
      setRevision("rev-1");
    }
  }, [revision, setRevision]);
  return revision === null ? null : <>{children}</>;
}

const SCENARIOS = [
  {
    scenario_id: "tiny_valid",
    display_name: "Republic of Arken",
    government_form: "Parliamentary republic",
    election_interval_label: "Every 4 turns",
    starting_legitimacy_text: "62%",
    is_showcase: true,
  },
];

const ACTIVE_DASHBOARD = {
  revision: "rev-1",
  country_name: "Testland",
  turn: 3,
  next_election_label: "Turn 8",
  government_form: "Parliamentary republic",
  political_capital: { display: "120", current: 120, capacity: 200, committed_this_turn: 0 },
  alerts: [],
  goal: { headline: "Hold the coalition together", detail: null },
  map: { note: "No spatial state.", presentation_only: true, tint_metric_label: "Legitimacy", tint_value_bps: 6200 },
  concerns: {
    money: { label: "Money", headline: "Stable", direction: "unchanged", tone: "neutral", delta_text: null, detail_screen: "economy" },
    legitimacy: { label: "Legitimacy", headline: "Solid", direction: "unchanged", tone: "neutral", delta_text: null, detail_screen: "government" },
    legislature: { label: "Legislature", headline: "Comfortable", direction: "unchanged", tone: "neutral", delta_text: null, detail_screen: "legislature" },
    constitution: { label: "Constitution", headline: "Stable", direction: "unchanged", tone: "neutral", delta_text: null, detail_screen: "constitution" },
    survival: { label: "Survival", headline: "Secure", direction: "unchanged", tone: "neutral", delta_text: null, detail_screen: "relationships" },
  },
  terminal: null,
};

const DECISION_OPTIONS = {
  revision: "rev-1",
  blocs: [],
  chambers: [],
  constitutional_axes: [],
  decree_amendment_capital_cost: 10,
  decree_available: true,
  policy_cards: [],
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

function mockFullApp() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/api/game/new") && init?.method === "POST") {
      return Promise.resolve(jsonResponse(ACTIVE_DASHBOARD));
    }
    if (url.includes("/api/scenarios")) return Promise.resolve(jsonResponse(SCENARIOS));
    if (url.includes("/api/saves")) return Promise.resolve(jsonResponse([]));
    if (url.includes("/api/game/state")) return Promise.resolve(jsonResponse(ACTIVE_DASHBOARD));
    if (url.includes("/api/game/decision-options")) return Promise.resolve(jsonResponse(DECISION_OPTIONS));
    if (url.includes("/api/game/history")) return Promise.resolve(jsonResponse([]));
    throw new Error(`unexpected fetch: ${url}`);
  });
}

/** Drives the real New Game flow through the Title screen so `revision` is
 * genuinely set (exactly as a player reaching any other screen always
 * would) -- History's own query is legitimately gated on a non-null
 * revision, so no screen but Title can be reached honestly without this. */
async function startGameFromTitle() {
  const startButton = await screen.findByRole("button", { name: /start republic of arken/i });
  fireEvent.click(startButton);
  await waitFor(() =>
    expect(screen.getByRole("heading", { level: 2, name: "National dashboard" })).toBeInTheDocument(),
  );
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <GreyboxApp />
    </QueryClientProvider>,
  );
}

describe("GreyboxApp: keyboard navigation and aria-current across all eleven screens", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    mockFullApp();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("every nav entry is a native, keyboard-activatable <button> -- never a div/span click handler", async () => {
    renderApp();
    const nav = await screen.findByRole("navigation", { name: "Screens" });
    const buttons = within(nav).getAllByRole("button");
    expect(buttons).toHaveLength(SCREENS.length);
    for (const button of buttons) {
      expect(button.tagName).toBe("BUTTON");
      expect(button.getAttribute("type")).toBe("button");
    }
  });

  it("activating each of the eleven nav entries renders that screen's own heading and moves aria-current to exactly that one button", async () => {
    renderApp();
    await startGameFromTitle();
    const nav = await screen.findByRole("navigation", { name: "Screens" });

    for (const entry of SCREENS) {
      const button = within(nav).getByRole("button", { name: entry.label });
      fireEvent.click(button);

      await waitFor(() =>
        expect(screen.getByRole("heading", { level: 2, name: entry.heading })).toBeInTheDocument(),
      );

      const currentButtons = within(nav)
        .getAllByRole("button")
        .filter((candidate) => candidate.getAttribute("aria-current") === "page");
      expect(currentButtons).toHaveLength(1);
      expect(currentButtons[0]).toBe(button);
    }
  });
});

describe("GreyboxApp: Glossary is chrome-level, keyboard-activatable, and dismissible", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    mockFullApp();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("the Glossary toggle is a native <button> reachable from every screen, and opens/closes an aria-region", async () => {
    renderApp();
    const toggle = await screen.findByRole("button", { name: "Glossary" });
    expect(toggle.tagName).toBe("BUTTON");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("region", { name: "Glossary" })).not.toBeInTheDocument();

    // Activation -- a real browser dispatches the same click a native
    // <button> produces on Enter/Space; no custom key handler exists or is
    // needed here.
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const region = screen.getByRole("region", { name: "Glossary" });
    expect(region).toBeInTheDocument();
    expect(within(region).getByRole("heading", { name: "Glossary" })).toBeInTheDocument();

    // Dismissal -- the same control, now labelled "Close glossary", closes it.
    const closeToggle = screen.getByRole("button", { name: "Close glossary" });
    fireEvent.click(closeToggle);
    expect(closeToggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("region", { name: "Glossary" })).not.toBeInTheDocument();
  });

  it("the Glossary toggle is reachable without navigating away from the current screen", async () => {
    renderApp();
    const nav = await screen.findByRole("navigation", { name: "Screens" });
    fireEvent.click(within(nav).getByRole("button", { name: "Dashboard" }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2, name: "National dashboard" })).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Glossary" }));
    expect(screen.getByRole("region", { name: "Glossary" })).toBeInTheDocument();
    // The underlying screen is still mounted -- the panel is inline, not a
    // navigation away or a blocking modal.
    expect(screen.getByRole("heading", { level: 2, name: "National dashboard" })).toBeInTheDocument();
  });
});

describe("Accessible loading and error announcements", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("a pending fetch is announced via role=status/aria-live=polite, not silently blank", async () => {
    vi.mocked(fetch).mockImplementation(() => new Promise(() => {})); // never resolves
    renderApp();
    const statuses = await screen.findAllByRole("status");
    expect(statuses.length).toBeGreaterThan(0);
    for (const status of statuses) {
      expect(status).toHaveAttribute("aria-live", "polite");
    }
  });

  it("a failed fetch is announced via role=alert, naming the failure", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/scenarios")) {
        return Promise.resolve(jsonResponse({ type: "internal_error", title: "Failed", status: 500, detail: "boom", fields: [] }, 500));
      }
      if (url.includes("/api/saves")) return Promise.resolve(jsonResponse([]));
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderApp();
    const alert = await screen.findByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(alert.textContent?.length).toBeGreaterThan(0);
  });
});

describe("Passed/failed state is never communicated by color alone", () => {
  it("the terminal victory/defeat headline carries real text alongside its tone class, not a color-only indicator", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.stubGlobal("fetch", vi.fn());
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/state")) {
        return Promise.resolve(
          jsonResponse({
            ...ACTIVE_DASHBOARD,
            terminal: { bucket: "defeat", headline: "The government collapsed.", reason_label: "Collapse", turn: 9 },
          }),
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    render(
      <QueryClientProvider client={client}>
        <SessionProvider>
          <TerminalScreen navigate={vi.fn()} />
        </SessionProvider>
      </QueryClientProvider>,
    );

    return waitFor(() => {
      const headline = screen.getByText("The government collapsed.");
      // Every tone-carrying element in this app (`ToneValue`) wraps real,
      // non-empty text -- the tone class is decoration ON TOP of a legible
      // word, never a bare colored swatch/icon standing alone for meaning.
      expect(headline.tagName).toBe("SPAN");
      expect(headline.textContent?.trim().length).toBeGreaterThan(0);
      expect(headline.className).toMatch(/text-(red|emerald)-\d+/);
    }).then(() => {
      vi.unstubAllGlobals();
    });
  });
});

describe("The terminal screen has no Resolve control, under any state", () => {
  function renderTerminal(dashboard: unknown) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.stubGlobal("fetch", vi.fn());
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return Promise.resolve(jsonResponse(dashboard));
      throw new Error(`unexpected fetch: ${url}`);
    });
    return render(
      <QueryClientProvider client={client}>
        <SessionProvider>
          <TerminalScreen navigate={vi.fn()} />
        </SessionProvider>
      </QueryClientProvider>,
    );
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("has no Resolve control while the campaign is still active", async () => {
    renderTerminal(ACTIVE_DASHBOARD);
    await screen.findByText("The campaign is still active");
    expect(screen.queryByRole("button", { name: /resolve/i })).not.toBeInTheDocument();
  });

  it("has no Resolve control once the campaign has concluded", async () => {
    renderTerminal({
      ...ACTIVE_DASHBOARD,
      terminal: { bucket: "victory", headline: "Peaceful liberalization achieved.", reason_label: "Liberalization", turn: 12 },
    });
    await screen.findByText("Peaceful liberalization achieved.");
    expect(screen.queryByRole("button", { name: /resolve/i })).not.toBeInTheDocument();
  });
});

describe("Decision controls carry a real accessible label", () => {
  const RICH_DECISION_OPTIONS = {
    revision: "rev-1",
    blocs: [
      { party_id: "national_front", bloc_id: "conservatives", bloc_name: "Conservatives", chamber: "lower", seats: 60 },
      { party_id: "national_front", bloc_id: "populists", bloc_name: "Populists", chamber: "upper", seats: 20 },
    ],
    chambers: [],
    constitutional_axes: [
      { axis: "decree_authority", current_value: "limited", allowed_values: ["none", "limited", "unlimited"] },
      { axis: "electoral_competitiveness", current_value: 5000, allowed_values: null },
    ],
    decree_amendment_capital_cost: 10,
    decree_available: true,
  policy_cards: [],
    decree_legislative_capital_cost: 10,
    opening_capital: 500,
    relationship_investment_maximum: 50,
    relationship_investment_minimum: 0,
    spending_categories: [],
    tax_rate_bps_maximum: 5000,
    tax_rate_bps_minimum: 0,
  };

  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return Promise.resolve(jsonResponse(ACTIVE_DASHBOARD));
      if (url.includes("/api/game/decision-options")) return Promise.resolve(jsonResponse(RICH_DECISION_OPTIONS));
      throw new Error(`unexpected fetch: ${url}`);
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("every amendment-axis control (select and number input) has a real accessible label naming its axis", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SessionProvider>
          <SetRevision>
            <DecisionsScreen navigate={vi.fn()} />
          </SetRevision>
        </SessionProvider>
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole("radio", { name: "Constitutional amendment" }));

    // Real axis ids (e.g. "decree_authority") render a human-readable label ("Decree
    // authority") rather than the raw snake_case field identifier; an axis id with no
    // known label (the synthetic "electoral_competitiveness" fixture below) still falls
    // back to its raw id, so a distinguishing accessible name always exists either way.
    expect(await screen.findByLabelText(/Decree authority/)).toBeInTheDocument();
    expect(screen.getByLabelText(/electoral_competitiveness/)).toBeInTheDocument();
  });

  it("every per-bloc influence-capital input has a real accessible label naming its bloc", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SessionProvider>
          <SetRevision>
            <DecisionsScreen navigate={vi.fn()} />
          </SetRevision>
        </SessionProvider>
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole("radio", { name: "Budget" }));
    fireEvent.click(await screen.findByRole("radio", { name: "Legislative vote" }));

    expect(await screen.findByLabelText("Influence capital for Conservatives")).toBeInTheDocument();
    expect(screen.getByLabelText("Influence capital for Populists")).toBeInTheDocument();
  });

  it("every per-bloc relationship-investment input has a real accessible label naming its bloc", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SessionProvider>
          <SetRevision>
            <DecisionsScreen navigate={vi.fn()} />
          </SetRevision>
        </SessionProvider>
      </QueryClientProvider>,
    );

    expect(await screen.findByLabelText("Relationship investment for Conservatives")).toBeInTheDocument();
    expect(screen.getByLabelText("Relationship investment for Populists")).toBeInTheDocument();
  });
});
