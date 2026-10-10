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
import { useDraftStore } from "../state/draft";
import { OBJECTIVE_FIXTURE } from "../test/objectiveFixture";

/** `revision` starts `null` in a fresh `SessionProvider`, and both
 * `useDecisionOptions`/`handlePreview` need a non-null one to behave like a
 * real in-progress campaign -- the same pattern
 * `DecisionsScreen.resilience.test.tsx` already established. */
function SetRevision({ children }: { children: ReactNode }) {
  const { setCampaignView, revision } = useSession();
  useEffect(() => {
    if (revision === null) {
      setCampaignView("rev-1", "campaign-1");
    }
  }, [revision, setCampaignView]);
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
  objective: OBJECTIVE_FIXTURE,
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
  cabinet_posts: [],
  // The four counterparty collections Relationships reads. Empty rather than absent: the screen
  // renders its own "nobody to deal with" copy from an empty list, and an absent key would be a
  // shape the server cannot send.
  legislative_bargain_counterparties: [],
  foreign_assistance_counterparties: [],
  promise_options: [],
  active_promises: [],
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

const STRATEGIC_MAP = {
  map_id: "tiny_valid",
  capital_theater_id: "capital",
  theaters: [
    {
      theater_id: "capital",
      display_name: "Capital Theater",
      kind: "land",
      is_capital: true,
      is_player_owned: true,
      owner_id: "player",
      owner_namespace: "player_country",
      owner_display_name: "Testland",
      centroid_x: 0,
      centroid_y: 0,
      label_anchor: "center",
      outgoing_theater_ids: ["frontier"],
      incoming_theater_ids: ["frontier"],
    },
    {
      theater_id: "frontier",
      display_name: "Frontier Theater",
      kind: "coastal",
      is_capital: false,
      is_player_owned: false,
      owner_id: "neighbor",
      owner_namespace: "foreign_profile",
      owner_display_name: "Republic of Veskara",
      centroid_x: 10,
      centroid_y: 10,
      label_anchor: "n",
      outgoing_theater_ids: ["capital"],
      incoming_theater_ids: ["capital"],
    },
  ],
  routes: [{ from_theater_id: "capital", to_theater_id: "frontier", bidirectional: true }],
  shapes: [],
  rivers: [],
};

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
    if (url.includes("/api/game/map/strategic")) return Promise.resolve(jsonResponse(STRATEGIC_MAP));
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

describe("GreyboxApp: Strategic map nav entry is gated on an active game", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    mockFullApp();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("is disabled with an explanatory label before any game is loaded", async () => {
    renderApp();
    const nav = await screen.findByRole("navigation", { name: "Screens" });
    const button = within(nav).getByRole("button", { name: "Strategic map" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Load or start a game to view the strategic map.");
  });

  it("becomes enabled, keyboard-activatable, and reaches the screen once a game is loaded", async () => {
    renderApp();
    await startGameFromTitle();
    const nav = await screen.findByRole("navigation", { name: "Screens" });
    const button = within(nav).getByRole("button", { name: "Strategic map" });
    expect(button).not.toBeDisabled();

    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-current", "page");
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2, name: "Strategic map" })).toBeInTheDocument(),
    );
  });

  it("keyboard traversal of the theater list selects a theater and announces the live-region text verbatim", async () => {
    renderApp();
    await startGameFromTitle();
    const nav = await screen.findByRole("navigation", { name: "Screens" });
    fireEvent.click(within(nav).getByRole("button", { name: "Strategic map" }));

    const theaterButton = await screen.findByRole("button", {
      name: "Capital Theater — Land, Testland, capital",
    });
    // A native <button> is Tab-reachable and Enter/Space-activatable with no
    // custom key handler -- `fireEvent.click` is what that keypress
    // ultimately dispatches.
    fireEvent.click(theaterButton);
    expect(theaterButton).toHaveAttribute("aria-pressed", "true");

    await waitFor(() =>
      expect(
        screen.getByText("Capital Theater, land, owned by Testland, 1 routes out, 1 routes in"),
      ).toBeInTheDocument(),
    );
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

describe("Gate 4A3 Commit 4: the \"How to govern\" introduction", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    mockFullApp();
    // The flag is module-level Zustand and survives between tests in one file, so it is reset
    // explicitly rather than relying on the default -- a test that ran after a dismissal would
    // otherwise assert against an introduction that was already closed.
    // Both flags, not just the one under test: the store is module-level Zustand and a Glossary left
    // open by an earlier test in this file relabels its own toggle to "Close glossary", which is how
    // the header assertion below first failed. Leaked UI state is worth resetting explicitly rather
    // than working around with a looser matcher.
    useDraftStore.setState({ dismissedHelp: false, glossaryOpen: false });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /** The exact sentences, asserted as strings rather than matched by pattern. A pattern is what let
   * the previous wording go unexamined for two gates: `/build one decision/` would have passed
   * happily while teaching a player the wrong model of a turn. */
  const LOOP_SENTENCE =
    "Review your country, prepare your actions, preview their consequences, resolve the turn, " +
    "and read what happened.";

  it("states the turn loop correctly, and no longer says a turn is one decision", async () => {
    renderApp();
    const note = await screen.findByRole("complementary", { name: "How to govern" });
    expect(within(note).getByText(LOOP_SENTENCE)).toBeInTheDocument();
    // THE REGRESSION GUARD. "build one decision" was not merely thin -- it was wrong: a turn
    // combines a policy proposal with appointments, bargains, assistance requests, promises and
    // movement orders. If that wording returns, this fails.
    expect(note.textContent ?? "").not.toContain("build one decision");
  });

  it("leaves the one-budget-or-amendment limit on the Decisions screen, where it applies", async () => {
    renderApp();
    const note = await screen.findByRole("complementary", { name: "How to govern" });
    // Stating the limit in a GENERAL introduction would imply it governs the whole turn, which is
    // the same misstatement relocated. The limit belongs to the policy proposal alone.
    expect(note.textContent ?? "").not.toContain("amendment");
    expect(note.textContent ?? "").not.toContain("budget");
  });

  it("is a complementary landmark and never a dialog", async () => {
    renderApp();
    const note = await screen.findByRole("complementary", { name: "How to govern" });
    expect(note.tagName).toBe("ASIDE");
    expect(note.getAttribute("role")).toBeNull();
    expect(note.getAttribute("aria-modal")).toBeNull();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("can be dismissed AND reopened -- the defect this commit fixes", async () => {
    renderApp();
    const toggle = await screen.findByRole("button", { name: "How to govern" });
    expect(toggle.tagName).toBe("BUTTON");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("complementary", { name: "How to govern" })).not.toBeInTheDocument();
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    // Before this commit the introduction was dismissible and NOTHING ELSE: `dismissHelp` could only
    // set the flag true, so the one place the game explains itself was a single-use resource for the
    // whole session.
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const reopened = screen.getByRole("complementary", { name: "How to govern" });
    expect(within(reopened).getByText(LOOP_SENTENCE)).toBeInTheDocument();
  });

  it("never blocks play: Start is operable while the introduction is open", async () => {
    renderApp();
    await screen.findByRole("complementary", { name: "How to govern" });
    const start = await screen.findByRole("button", { name: /^Start / });
    expect(start).toBeEnabled();
    expect(start.getAttribute("aria-disabled")).toBeNull();
    // No inert ancestor and no modal: the note is in normal flow beside the screen, so nothing about
    // it removes the rest of the page from the accessibility tree.
    expect(start.closest("[inert]")).toBeNull();
    expect(start.closest("[aria-hidden=\"true\"]")).toBeNull();
  });

  it("the toggle sits beside the Glossary toggle and uses the same aria-expanded convention", async () => {
    renderApp();
    const banner = await screen.findByRole("banner");
    const help = within(banner).getByRole("button", { name: "How to govern" });
    const glossary = within(banner).getByRole("button", { name: "Glossary" });
    for (const control of [help, glossary]) {
      expect(control.getAttribute("aria-expanded")).not.toBeNull();
    }
    // One convention in the header rather than two, which is why the new control reuses the pattern
    // the Glossary control already established rather than inventing a second one.
    expect(help.parentElement).toBe(glossary.parentElement);
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
      // Gate 4A3 Commit 3 (finding F3): this pinned the Tailwind DEFAULT palette
      // (`text-red-*`/`text-emerald-*`), which the tone classes no longer use --
      // they are MANDATE tokens now, with measured contrast recorded in
      // tokens.css. The assertion's INTENT is unchanged and is deliberately not
      // weakened: the headline must still carry a tone colour on top of real
      // text. `tools/check-palette.mjs` is what now guarantees no default-palette
      // name can come back, so this expectation names the tokens rather than
      // matching anything colour-shaped.
      expect(headline.className).toMatch(/text-(danger|success|warning)-\d+/);
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
