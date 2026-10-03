/**
 * Gate 4A3 UX-3: orientation (U1), the next action (U5) and no dead ends (U10).
 *
 * The concern destinations are tested GENERATIVELY: for every concern in the fixture dashboard, the
 * screen its `detail_screen` names is rendered through the real registry, and must show that concern's
 * card. So all five Dashboard "Details" links are covered, Government's two included, and a sixth
 * concern or a changed destination is covered without editing this file.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { liveTurnResultQueryKey } from "../api/queries";
import { SessionProvider, useSession } from "../state/SessionContext";
import { ConcernSummaries } from "./ConcernCards";
import { GreyboxApp } from "./GreyboxApp";
import { screenById } from "./registry";
import { DashboardScreen } from "./screens/DashboardScreen";
import { GLOSSARY_ENTRIES, WIN_AND_LOSS_LINE, glossaryDefinition } from "./screens/GlossaryScreen";
import { ResultScreen } from "./screens/ResultScreen";
import type { ScreenId } from "./types";

function card(label: string, headline: string, detail_screen: string, delta_text: string | null = null) {
  return { label, headline, delta_text, direction: "unchanged", tone: "neutral", detail_screen };
}

const DASHBOARD = {
  revision: "1.1",
  campaign_id: "campaign-1",
  turn: 1,
  country_name: "Kingdom of Testland",
  government_form: "Hereditary monarchy, unlimited decree authority",
  next_election_label: "None scheduled",
  concerns: {
    money: card("Money", "100000000.00", "economy", "3150000.00"),
    legitimacy: card("Legitimacy", "61.25%", "government"),
    legislature: card("Legislature", "2 parties, 100 seats", "legislature"),
    constitution: card("Constitution", "Supermajority", "constitution"),
    survival: card("Survival", "Coup risk 4.00%", "government", "None of that comes from the shape of the government itself."),
  },
  political_capital: { current: 500, capacity: 1000, committed_this_turn: 0, display: "500 / 1,000" },
  alerts: [],
  goal: { headline: "Nothing is pressing.", detail: null },
  map: {
    presentation_only: true,
    tint_metric_label: "Legitimacy",
    tint_value_bps: 6125,
    note: "This is a national identity tint, not a geographic map. No province-level mechanics exist.",
  },
  terminal: null,
};

const CONCERNS = Object.values(DASHBOARD.concerns);
const FORBIDDEN = ["placeholder", "outline", "province", "mechanics"];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return json(DASHBOARD);
      if (url.includes("/api/scenarios")) return json([]);
      if (url.includes("/api/saves")) return json([]);
      // Government's own cabinet data is not what these tests are about.
      return json({ detail: "not in this test" }, 404);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function SetRevision({ children }: { children: ReactNode }) {
  const { setCampaignView, revision } = useSession();
  useEffect(() => {
    if (revision === null) setCampaignView("1.1", "campaign-1");
  }, [revision, setCampaignView]);
  return revision === null ? null : <>{children}</>;
}

function withCampaign(ui: ReactNode, client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <SetRevision>{ui}</SetRevision>
      </SessionProvider>
    </QueryClientProvider>,
  );
}

/** The whole app, as `main.tsx` mounts it: the shell brings its own session, not its query client. */
function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <GreyboxApp />
    </QueryClientProvider>,
  );
}

/** Every rendered text and accessible-name-bearing attribute on the page. */
function playerVisibleText(root: HTMLElement): string {
  const attributes = Array.from(root.querySelectorAll("*")).flatMap((el) =>
    ["aria-label", "aria-description", "title", "alt", "placeholder"].map((a) => el.getAttribute(a) ?? ""),
  );
  return [root.textContent ?? "", ...attributes].join(" ").toLowerCase();
}

describe("U1: the stakes and the first action", () => {
  it("quotes the Glossary's own entries rather than restating them", () => {
    expect(glossaryDefinition("Political capital")).toBe(
      GLOSSARY_ENTRIES.find((e) => e.term === "Political capital")!.definition,
    );
    expect(() => glossaryDefinition("No such term")).toThrow();
  });

  it("states how to win and every way to lose, exactly", () => {
    expect(WIN_AND_LOSS_LINE).toBe(
      "You win by turning this into a competitive constitution and then winning the first election " +
        "held under it. You lose if you are removed by coup, forced abdication, assassination, " +
        "impeachment, electoral defeat or term limit exit.",
    );
  });

  it("puts the stakes and Build a decision inside the priority card", async () => {
    const navigate = vi.fn();
    withCampaign(<DashboardScreen navigate={navigate} />);
    const heading = await screen.findByRole("heading", { name: "Your current priority" });
    const priority = heading.closest("section") as HTMLElement;
    expect(within(priority).getByTestId("win-and-loss")).toHaveTextContent(WIN_AND_LOSS_LINE);
    fireEvent.click(within(priority).getByRole("button", { name: "Build a decision" }));
    expect(navigate).toHaveBeenCalledWith("decisions");
    expect(screen.getAllByRole("button", { name: "Build a decision" })).toHaveLength(1);
  });

  it("states the stakes in How to govern, and explains Capital with the Glossary's definition", async () => {
    renderApp();
    const aside = screen.getByRole("complementary", { name: "How to govern" });
    expect(within(aside).getByTestId("win-and-loss")).toHaveTextContent(WIN_AND_LOSS_LINE);

    fireEvent.click(screen.getByRole("button", { name: "Dashboard" }));
    const meter = await screen.findByTestId("capital-meter");
    expect(meter).toHaveTextContent("Capital 500 / 1,000");
    expect(meter).toHaveAttribute("title", glossaryDefinition("Political capital"));
    expect(meter).toHaveAttribute("aria-description", glossaryDefinition("Political capital"));
  });
});

describe("U10: every Details link lands on what it was linked for", () => {
  it.each(CONCERNS.map((c) => [c.label, c.detail_screen] as const))(
    "%s → %s shows that card",
    async (label, detailScreen) => {
      const Screen = screenById(detailScreen as ScreenId).component;
      withCampaign(<Screen navigate={vi.fn()} />);
      const summaries = await screen.findByTestId("concern-summaries");
      const concern = CONCERNS.find((c) => c.label === label)!;
      const cardHeading = within(summaries).getByRole("heading", { name: label });
      const cardSection = cardHeading.closest("section") as HTMLElement;
      expect(cardSection).toHaveTextContent(concern.headline);
      // Exactly the concerns that link here, and no Details button pointing back at this screen.
      const expected = CONCERNS.filter((c) => c.detail_screen === detailScreen).map((c) => c.label);
      expect(within(summaries).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
        "Summary",
        ...expected,
      ]);
      expect(within(summaries).queryByRole("button", { name: /^Details/ })).toBeNull();
    },
  );

  it("Government shows Legitimacy AND Survival, under the screen's own heading", async () => {
    const Screen = screenById("government").component;
    withCampaign(<Screen navigate={vi.fn()} />);
    const summaries = await screen.findByTestId("concern-summaries");
    expect(within(summaries).getByRole("heading", { name: "Legitimacy" })).toBeInTheDocument();
    expect(within(summaries).getByRole("heading", { name: "Survival" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Government", level: 2 })).toHaveLength(1);
    const order = screen.getAllByRole("heading").map((h) => h.textContent);
    expect(order.indexOf("Government")).toBeLessThan(order.indexOf("Summary"));
  });

  it("renders nothing without a campaign", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={client}>
        <SessionProvider>
          <ConcernSummaries screen="economy" />
        </SessionProvider>
      </QueryClientProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("groups the three summary screens under a visible caption, keeping every control's name", () => {
    renderApp();
    const nav = screen.getByRole("navigation", { name: "Screens" });
    const group = within(nav).getByRole("list", { name: "Summaries" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Economy",
      "Legislature",
      "Constitution",
    ]);
    // The disabled controls name their own screen, not the strategic map.
    expect(within(nav).getByRole("button", { name: "Government" })).toHaveAttribute(
      "title",
      "Load or start a game to view the government.",
    );
    expect(within(nav).getByRole("button", { name: "Relationships" })).toHaveAttribute(
      "title",
      "Load or start a game to view the relationships.",
    );
  });
});

describe("U10: the national tint draws what it claims", () => {
  it("fills the box from the server's value, names the country, and says nothing developer-facing", async () => {
    withCampaign(<DashboardScreen navigate={vi.fn()} />);
    const box = await screen.findByTestId("national-tint");
    expect(box).toHaveAttribute("data-tint-bps", "6125");
    expect(box.style.backgroundColor).toContain("var(--color-gold-600)");
    expect(box).toHaveAccessibleName("Kingdom of Testland: national tint by legitimacy, 61.25%.");
    expect(box).toHaveTextContent("Kingdom of Testland");
    const page = screen.getByRole("heading", { name: "National dashboard" }).parentElement as HTMLElement;
    expect(page).toHaveTextContent(
      "The colour shows national legitimacy: the stronger it is, the deeper the tint.",
    );
    const visible = playerVisibleText(page);
    for (const word of FORBIDDEN) expect(visible, word).not.toContain(word);
    expect(page).not.toHaveTextContent(DASHBOARD.map.note);
  });
});

describe("U5: the next action after a turn", () => {
  function renderResult(result: unknown) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    client.setQueryData(liveTurnResultQueryKey(), result);
    const navigate = vi.fn();
    render(
      <QueryClientProvider client={client}>
        <ResultScreen navigate={navigate} />
      </QueryClientProvider>,
    );
    return navigate;
  }

  const RESULT = {
    revision: "3.3",
    turn: 3,
    outcome_headline: "The turn was resolved.",
    outcome_tone: "neutral",
    drivers: [],
    ledger: [],
    unchanged: [],
    trace: [],
    terminal: null,
  };

  it("offers Plan turn N, which opens Decisions, ahead of the secondary actions", () => {
    const navigate = renderResult(RESULT);
    const buttons = screen.getAllByRole("button").map((b) => b.textContent);
    expect(buttons.slice(-3)).toEqual(["Plan turn 3", "Back to Dashboard", "Review history"]);
    fireEvent.click(screen.getByRole("button", { name: "Plan turn 3" }));
    expect(navigate).toHaveBeenCalledWith("decisions");
  });

  it("offers no next turn once the campaign has ended", async () => {
    renderResult({
      ...RESULT,
      terminal: { bucket: "defeat", reason_label: "Coup", turn: 3, headline: "Removed from office: coup, turn 3." },
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Review the outcome" })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /^Plan turn/ })).toBeNull();
  });
});
