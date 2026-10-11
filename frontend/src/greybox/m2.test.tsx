/**
 * Gate 4A3 M-2: Parliament and the shared preview, through the real screens.
 *
 * Every preview response here is a controlled promise, so each test decides exactly when (and in
 * what order, and after which lifecycle event) a response lands. The checks:
 * - Parliament's content: the engine's thresholds, two chambers, before and after Preview, rows
 *   that sum, decree, a failing chamber, the last recorded vote (budget and amendment), no history
 *   drawn onto today's chamber, a concluded campaign with a stored preview, no legislature;
 * - freshness across Decisions AND Parliament: an edit of each kind, a late response, every
 *   lifecycle event, an unchanged view, signature-bound errors and loading, the retry-display rule;
 * - focus: a response landing after the player left moves no focus.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useEffect, useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useLoadGame, useNewGame, useResolve } from "../api/queries";
import { previewRequestSignature } from "../state/buildDecisionSet";
import { useDraftStore } from "../state/draft";
import { previewView, usePreviewStore } from "../state/previewStore";
import { SessionProvider, useSession } from "../state/SessionContext";
import { OBJECTIVE_FIXTURE } from "../test/objectiveFixture";
import VALDRUN_OPTIONS from "../test/decision-options-valdrun.json";
import { DecisionsScreen } from "./screens/DecisionsScreen";
import { ParliamentScreen } from "./screens/ParliamentScreen";

// ---- Fixtures ------------------------------------------------------------------------------------

function card(label: string, headline: string, detail_screen: string) {
  return { label, headline, delta_text: null, direction: "unchanged", tone: "neutral", detail_screen };
}

const DASHBOARD = {
  revision: "rev-1",
  campaign_id: "campaign-1",
  turn: 3,
  country_name: "Kingdom of Testland",
  government_form: "Parliamentary republic",
  next_election_label: "Turn 8",
  concerns: {
    money: card("Money", "100,000,000.00", "economy"),
    legitimacy: card("Legitimacy", "61.25%", "government"),
    legislature: card("Legislature", "2 parties, 160 seats", "legislature"),
    constitution: card("Constitution", "Supermajority", "constitution"),
    survival: card("Survival", "Coup risk 4.00%", "government"),
  },
  political_capital: { current: 500, capacity: 1000, committed_this_turn: 0, display: "500 / 1,000" },
  alerts: [],
  goal: { headline: "Nothing is pressing.", detail: null },
  objective: OBJECTIVE_FIXTURE,
  map: { presentation_only: true, tint_metric_label: "Legitimacy", tint_value_bps: 6125, note: "" },
  terminal: null,
};

const TERMINAL = {
  bucket: "defeat",
  headline: "The campaign has ended.",
  reason_label: "Electoral defeat",
  turn: 3,
};

const LOWER_BLOCS = VALDRUN_OPTIONS.blocs;
const UPPER_BLOCS = VALDRUN_OPTIONS.blocs.map((b) => ({
  ...b,
  chamber: "upper",
  seats: b.bloc_id === "core" ? 25 : 35,
}));

/** Two chambers. The upper chamber's budget threshold is 37, NOT floor(60 / 2) + 1 = 31: the screen
 * must show the engine's value, never a calculation of its own. */
const OPTIONS = {
  ...VALDRUN_OPTIONS,
  revision: "rev-1",
  campaign_id: "campaign-1",
  chambers: ["lower", "upper"],
  chamber_details: [
    { chamber: "lower", total_seats: 100, budget_required_seats: 51, amendment_required_seats: 67 },
    { chamber: "upper", total_seats: 60, budget_required_seats: 37, amendment_required_seats: 40 },
  ],
  blocs: [...LOWER_BLOCS, ...UPPER_BLOCS],
  last_recorded_vote: null,
};

const RECORDED_BUDGET = {
  turn: 4,
  vote: {
    proposal_kind: "budget",
    outcome: "failed_legislative",
    blocs_recorded: true,
    budget: {
      tax_direction: "decrease",
      tax_delta_bps: -200,
      spending_direction: "unchanged",
      opening_total_program_spending: 1000,
      proposed_total_program_spending: 1000,
    },
    amendment_targets: [],
    chambers: [
      {
        chamber: "lower",
        total_seats: 100,
        supporting_seats: 45,
        required_seats: 51,
        passed: false,
        blocs: [
          { party_id: "governing_party", bloc_id: "core", bloc_display_name: "Crown Party Core", seats: 45, supporting_seats: 45 },
          { party_id: "opposition_party", bloc_id: "main", bloc_display_name: "Reform Opposition Main", seats: 55, supporting_seats: 0 },
        ],
      },
    ],
  },
};

const RECORDED_AMENDMENT = {
  turn: 6,
  vote: {
    proposal_kind: "constitutional_amendment",
    outcome: "passed_legislative",
    blocs_recorded: false,
    budget: null,
    amendment_targets: [{ axis: "decree_authority", opening_value: "unlimited", proposed_value: "none" }],
    chambers: [{ chamber: "lower", total_seats: 100, supporting_seats: 70, required_seats: 67, passed: true, blocs: [] }],
  },
};

function previewBody(overrides: Record<string, unknown> = {}) {
  return {
    affordable: true,
    committed_capital: 0,
    estimate: true,
    excludes_stochastic_channels: ["election_swing"],
    has_proposal: true,
    influence_capital: 0,
    investment_capital: 0,
    cabinet_capital: 0,
    legislative_bargain_capital: 0,
    promise_release_capital: 0,
    foreign_assistance_estimate: 0,
    opening_capital: 500,
    route: "legislative",
    route_capital_cost: 0,
    would_pass: false,
    investment_effects: [],
    objective_effect_if_enacted: null,
    chambers: [
      {
        chamber: "lower",
        supporting_seats: 61,
        required_seats: 51,
        total_seats: 100,
        carries: true,
        blocs: [
          { party_id: "governing_party", bloc_id: "core", seats: 45, supporting_seats: 45 },
          { party_id: "opposition_party", bloc_id: "main", seats: 55, supporting_seats: 16 },
        ],
      },
      {
        chamber: "upper",
        supporting_seats: 25,
        required_seats: 37,
        total_seats: 60,
        carries: false,
        blocs: [
          { party_id: "governing_party", bloc_id: "core", seats: 25, supporting_seats: 25 },
          { party_id: "opposition_party", bloc_id: "main", seats: 35, supporting_seats: 0 },
        ],
      },
    ],
    ...overrides,
  };
}

// ---- Controlled fetch ----------------------------------------------------------------------------

interface Deferred {
  succeed: (body?: unknown) => Promise<void>;
  failWithServerError: () => Promise<void>;
}

let previewRequests: Deferred[] = [];
let dashboardBody: Record<string, unknown> = DASHBOARD;
let optionsBody: Record<string, unknown> = OPTIONS;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  previewRequests = [];
  dashboardBody = DASHBOARD;
  optionsBody = OPTIONS;
  useDraftStore.getState().clearDraft();
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return Promise.resolve(json(dashboardBody));
      if (url.includes("/api/game/decision-options")) return Promise.resolve(json(optionsBody));
      if (url.includes("/api/game/preview") && init?.method === "POST") {
        return new Promise<Response>((resolve) => {
          previewRequests.push({
            succeed: async (body = previewBody()) => {
              await act(async () => {
                resolve(json(body));
              });
            },
            failWithServerError: async () => {
              await act(async () => {
                resolve(json({ detail: { code: "internal_error", message: "The preview failed." } }, 500));
              });
            },
          });
        });
      }
      if (url.includes("/api/game/resolve")) {
        return Promise.resolve(json({ dashboard: { ...dashboardBody, revision: "rev-2" }, turnResult: { turn: 4 } }));
      }
      if (url.includes("/api/game/load") || url.includes("/api/game/new")) {
        // The SAME campaign at the SAME revision: only the lifecycle token can tell the difference.
        return Promise.resolve(json(dashboardBody));
      }
      if (url.includes("/api/game/history") || url.includes("/api/saves") || url.includes("/api/game/military")) {
        return Promise.resolve(json([]));
      }
      throw new Error(`unexpected fetch: ${url}`);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---- Harness -------------------------------------------------------------------------------------

type Shown = "parliament" | "decisions" | "none";

const control: {
  show: (screen: Shown) => void;
  resolve: () => void;
  load: () => void;
  newGame: () => void;
  setView: (revision: string, campaignId: string) => void;
} = { show: () => {}, resolve: () => {}, load: () => {}, newGame: () => {}, setView: () => {} };

function Controls() {
  const { setCampaignView } = useSession();
  const resolve = useResolve();
  const load = useLoadGame();
  const newGame = useNewGame();
  control.setView = (revision, campaignId) => setCampaignView(revision, campaignId);
  control.resolve = () =>
    resolve.mutate({ revision: "rev-1", campaignId: "campaign-1", decisions: [] });
  control.load = () => load.mutate({ saveId: "save-1" });
  control.newGame = () => newGame.mutate({ scenarioId: "tiny_valid" });
  return null;
}

function SetView({ children }: { children: ReactNode }) {
  const { setCampaignView, revision } = useSession();
  useEffect(() => {
    if (revision === null) setCampaignView("rev-1", "campaign-1");
  }, [revision, setCampaignView]);
  return revision === null ? null : <>{children}</>;
}

function Stage({ initial }: { initial: Shown }) {
  const [shown, setShown] = useState<Shown>(initial);
  control.show = (next) => act(() => setShown(next));
  return (
    <>
      <button type="button" data-testid="elsewhere">
        Elsewhere
      </button>
      {shown === "parliament" ? <ParliamentScreen navigate={vi.fn()} /> : null}
      {shown === "decisions" ? <DecisionsScreen navigate={vi.fn()} /> : null}
    </>
  );
}

function renderStage(initial: Shown = "parliament") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <SetView>
          <Controls />
          <Stage initial={initial} />
        </SetView>
      </SessionProvider>
    </QueryClientProvider>,
  );
}

function draftBudget() {
  act(() => {
    useDraftStore.getState().setPolicySlot("budget");
    useDraftStore.getState().setBudgetRateTarget("personalIncomeRateBps", 1800);
  });
}

async function parliamentReady() {
  await screen.findAllByTestId("chamber-card");
}

async function pressPreview() {
  fireEvent.click(await screen.findByRole("button", { name: "Preview" }));
  await waitFor(() => expect(previewRequests.length).toBeGreaterThan(0));
  return previewRequests[previewRequests.length - 1]!;
}

const parliamentShowsEstimate = () => screen.queryAllByTestId("chamber-supporting").length > 0;
const decisionsShowsEstimate = () => screen.queryByTestId("consequences-panel") !== null;

async function expectNoEstimateOnEitherScreen() {
  control.show("parliament");
  await parliamentReady();
  expect(parliamentShowsEstimate()).toBe(false);
  expect(screen.queryAllByTestId("chamber-verdict")).toHaveLength(0);
  control.show("decisions");
  await screen.findByText("Decision workspace");
  expect(decisionsShowsEstimate()).toBe(false);
}

// ---- Parliament's content ------------------------------------------------------------------------

describe("Parliament", () => {
  it("shows each chamber with the engine's own thresholds, seats by bloc before any preview", async () => {
    draftBudget();
    renderStage();
    await parliamentReady();
    const cards = screen.getAllByTestId("chamber-card");
    expect(cards.map((c) => c.dataset.chamber)).toEqual(["lower", "upper"]);
    expect(within(cards[1]!).getByTestId("budget-threshold")).toHaveTextContent("A budget needs 37");
    expect(within(cards[1]!).getByTestId("amendment-threshold")).toHaveTextContent("An amendment needs 40");
    for (const c of cards) {
      expect(c.dataset.mode).toBe("seats");
      expect(within(c).getByTestId("chamber-tally")).toHaveTextContent("Preview your draft to see expected support.");
      expect(within(c).getAllByTestId("bloc-supporting").map((n) => n.textContent)).toEqual(["—", "—"]);
    }
    expect(screen.getByTestId("draft-status")).toHaveTextContent("Not previewed yet");
  });

  it("after Preview shows each chamber's own tally, with bloc rows that sum to it", async () => {
    draftBudget();
    renderStage();
    await parliamentReady();
    await (await pressPreview()).succeed();
    await waitFor(() => expect(parliamentShowsEstimate()).toBe(true));
    const [lower, upper] = screen.getAllByTestId("chamber-card");
    expect(within(lower!).getByTestId("chamber-supporting")).toHaveTextContent("61 supporting if resolved now");
    expect(within(lower!).getByTestId("chamber-verdict")).toHaveTextContent("Would carry");
    expect(within(upper!).getByTestId("chamber-supporting")).toHaveTextContent("25 supporting if resolved now");
    expect(within(upper!).getByTestId("chamber-verdict")).toHaveTextContent("Would not carry");
    for (const [cardNode, total] of [
      [lower!, 61],
      [upper!, 25],
    ] as const) {
      const rows = within(cardNode).getAllByTestId("bloc-supporting").map((n) => Number(n.textContent));
      expect(rows.reduce((a, b) => a + b, 0)).toBe(total);
      const filled = cardNode.querySelectorAll('[data-seat][data-filled="true"]').length;
      expect(filled).toBe(total);
    }
    expect(screen.getByTestId("draft-status")).toHaveTextContent("Preview is current for this draft");
    expect(screen.getByTestId("parliament-announcement")).toHaveTextContent("Preview updated");
  });

  it("draws every seat of each chamber", async () => {
    draftBudget();
    renderStage();
    await parliamentReady();
    const [lower, upper] = screen.getAllByTestId("chamber-card");
    expect(lower!.querySelectorAll("[data-seat]")).toHaveLength(100);
    expect(upper!.querySelectorAll("[data-seat]")).toHaveLength(60);
  });

  it("on the decree route shows no tallies, even after Preview", async () => {
    draftBudget();
    act(() => useDraftStore.getState().setBudgetRoute("decree"));
    renderStage();
    await parliamentReady();
    expect(screen.getByText("No vote is held on a decree, so the legislature is bypassed.")).toBeInTheDocument();
    await (await pressPreview()).succeed(previewBody({ route: "decree", chambers: [], would_pass: true }));
    await waitFor(() => expect(screen.getByTestId("draft-status")).toHaveTextContent("Preview is current"));
    expect(parliamentShowsEstimate()).toBe(false);
    for (const c of screen.getAllByTestId("chamber-card")) {
      expect(within(c).getByTestId("chamber-tally")).toHaveTextContent("No vote is held on a decree.");
    }
  });

  it("says when no vote has been recorded", async () => {
    renderStage();
    await parliamentReady();
    expect(screen.getByTestId("last-recorded-vote")).toHaveTextContent("No recorded vote yet.");
    expect(screen.getByTestId("draft-proposal")).toHaveTextContent("No proposal drafted for this turn.");
  });

  it("shows a recorded budget vote ONLY under Last recorded vote, never drawn onto today's chamber", async () => {
    optionsBody = { ...OPTIONS, last_recorded_vote: RECORDED_BUDGET };
    renderStage();
    await parliamentReady();
    expect(screen.getByRole("heading", { name: "Last recorded vote · turn 4" })).toBeInTheDocument();
    const last = screen.getByTestId("last-recorded-vote");
    expect(last).toHaveTextContent("A budget, failed: taxes lowered (-2.00 points); spending unchanged.");
    expect(within(last).getByTestId("recorded-chamber")).toHaveTextContent(
      "Lower chamber: 45 supporting; 51 required — did not carry",
    );
    expect(within(last).getByText("Reform Opposition Main")).toBeInTheDocument();
    // Today's chambers carry no supporting count of any kind.
    for (const c of screen.getAllByTestId("chamber-card")) {
      expect(c.dataset.mode).toBe("seats");
      expect(c.querySelectorAll('[data-seat][data-filled="false"]')).toHaveLength(0);
      expect(within(c).getAllByTestId("bloc-supporting").every((n) => n.textContent === "—")).toBe(true);
    }
    expect(parliamentShowsEstimate()).toBe(false);
  });

  it("an amendment's recorded vote has chamber totals and a note, and no invented bloc rows", async () => {
    optionsBody = { ...OPTIONS, last_recorded_vote: RECORDED_AMENDMENT };
    renderStage();
    await parliamentReady();
    const last = screen.getByTestId("last-recorded-vote");
    expect(last).toHaveTextContent("A constitutional amendment, passed: Decree authority: unlimited → none.");
    expect(within(last).getByTestId("amendment-blocs-note")).toHaveTextContent(
      "Per-bloc votes are not recorded for amendments.",
    );
    expect(within(last).queryByRole("table")).toBeNull();
  });

  it("a concluded campaign shows no live estimate, even with a matching preview stored", async () => {
    // The preview is stored AFTER the campaign view is adopted (adopting a view correctly clears the
    // store, which is what made the first version of this test vacuous: mutation P4 survived it).
    draftBudget();
    renderStage();
    await parliamentReady();
    await (await pressPreview()).succeed();
    await waitFor(() => expect(parliamentShowsEstimate()).toBe(true));
    // The campaign ends while the player is elsewhere; the view does not change, so the store keeps it.
    control.show("none");
    dashboardBody = { ...DASHBOARD, terminal: TERMINAL };
    const signature = previewRequestSignature(useDraftStore.getState(), "rev-1", "campaign-1");
    expect(previewView(usePreviewStore.getState(), signature).current, "a matching preview is stored").not.toBeNull();
    control.show("parliament");
    await waitFor(() => expect(screen.getByTestId("parliament-draft")).toHaveTextContent("The campaign has ended."));
    await parliamentReady();
    expect(previewView(usePreviewStore.getState(), signature).current, "still stored while shown").not.toBeNull();
    expect(screen.queryByRole("button", { name: "Preview" })).toBeNull();
    expect(parliamentShowsEstimate()).toBe(false);
    expect(screen.queryAllByTestId("chamber-verdict")).toHaveLength(0);
    for (const c of screen.getAllByTestId("chamber-card")) {
      expect(c.dataset.mode).toBe("seats");
      expect(within(c).getByTestId("chamber-tally")).toHaveTextContent("The campaign has ended.");
    }
  });

  it("says so when no legislature sits", async () => {
    optionsBody = { ...OPTIONS, chamber_details: [], chambers: [], blocs: [] };
    renderStage();
    await screen.findByText("No legislature sits in Kingdom of Testland.");
    expect(screen.queryAllByTestId("chamber-card")).toHaveLength(0);
  });

  it("never says 'projected'", async () => {
    draftBudget();
    const { container } = renderStage();
    await parliamentReady();
    await (await pressPreview()).succeed();
    await waitFor(() => expect(parliamentShowsEstimate()).toBe(true));
    expect(container.textContent?.toLowerCase()).not.toContain("projected");
  });
});

// ---- Freshness across both screens ---------------------------------------------------------------

const EDITS: [string, () => void][] = [
  ["the proposal", () => useDraftStore.getState().setBudgetRateTarget("personalIncomeRateBps", 1700)],
  ["the route", () => useDraftStore.getState().setBudgetRoute("decree")],
  ["influence", () => useDraftStore.getState().setBudgetInfluence("opposition_party", "main", 10)],
  ["the bargain", () => useDraftStore.getState().setBargain("leader-1", "budget")],
  ["an investment", () => useDraftStore.getState().setInvestment("opposition_party", "main", 20)],
];

describe("an edit after Preview hides the estimate on both screens", () => {
  for (const [kind, edit] of EDITS) {
    it(`editing ${kind}`, async () => {
      draftBudget();
      renderStage();
      await parliamentReady();
      await (await pressPreview()).succeed();
      await waitFor(() => expect(parliamentShowsEstimate()).toBe(true));
      act(edit);
      expect(parliamentShowsEstimate()).toBe(false);
      control.show("decisions");
      await screen.findByText("Decision workspace");
      expect(decisionsShowsEstimate()).toBe(false);
    });
  }
});

describe("the shared preview's lifecycle", () => {
  it("a response that lands after an edit is not shown as current", async () => {
    draftBudget();
    renderStage();
    await parliamentReady();
    const request = await pressPreview();
    act(() => useDraftStore.getState().setBudgetRateTarget("personalIncomeRateBps", 1700));
    await request.succeed();
    expect(parliamentShowsEstimate()).toBe(false);
    expect(screen.getByTestId("draft-status")).toHaveTextContent("Your draft has changed since the last preview");
    control.show("decisions");
    await screen.findByTestId("preview-outdated");
    expect(decisionsShowsEstimate()).toBe(false);
  });

  it("the latest of two requests wins, whatever order they land in", async () => {
    draftBudget();
    renderStage();
    await parliamentReady();
    const first = await pressPreview();
    act(() => useDraftStore.getState().setBudgetRateTarget("personalIncomeRateBps", 1700));
    const second = await pressPreview();
    await second.succeed();
    await waitFor(() => expect(parliamentShowsEstimate()).toBe(true));
    await first.succeed(previewBody({ chambers: [] }));
    // The older response was dropped: the newer estimate is still the one shown.
    expect(screen.getAllByTestId("chamber-supporting")).toHaveLength(2);
  });

  const EVENTS: [string, () => Promise<void>][] = [
    ["a resolve", async () => {
      act(() => control.resolve());
      await waitFor(() => expect(usePreviewStore.getState().epoch).toBeGreaterThan(1));
      // Back to the original view, so only the lifecycle token can drop the old response.
      act(() => control.setView("rev-1", "campaign-1"));
    }],
    ["a load", async () => {
      act(() => control.load());
      await waitFor(() => expect(usePreviewStore.getState().epoch).toBeGreaterThan(1));
    }],
    ["a new game", async () => {
      act(() => control.newGame());
      await waitFor(() => expect(usePreviewStore.getState().epoch).toBeGreaterThan(1));
    }],
    ["a stale-view refresh that adopts a new view", async () => {
      act(() => control.setView("rev-2", "campaign-1"));
      act(() => control.setView("rev-1", "campaign-1"));
    }],
  ];
  for (const [name, event] of EVENTS) {
    it(`a response held across ${name} is never shown`, async () => {
      draftBudget();
      renderStage();
      await parliamentReady();
      const before = usePreviewStore.getState().epoch;
      const request = await pressPreview();
      await event();
      expect(usePreviewStore.getState().epoch).toBeGreaterThan(before);
      // The same draft, so the signature matches again: only the epoch stands between the old
      // response and the screen.
      draftBudget();
      await request.succeed();
      await expectNoEstimateOnEitherScreen();
    });
  }

  it("re-adopting the unchanged view keeps a valid preview", async () => {
    draftBudget();
    renderStage();
    await parliamentReady();
    await (await pressPreview()).succeed();
    await waitFor(() => expect(parliamentShowsEstimate()).toBe(true));
    const epoch = usePreviewStore.getState().epoch;
    act(() => control.setView("rev-1", "campaign-1"));
    expect(usePreviewStore.getState().epoch).toBe(epoch);
    expect(parliamentShowsEstimate()).toBe(true);
  });
});

describe("errors and loading follow the draft they were asked for", () => {
  for (const shown of ["parliament", "decisions"] as const) {
    it(`on ${shown}: no loading state or error against an edited draft; the right one comes back`, async () => {
      draftBudget();
      renderStage(shown);
      if (shown === "parliament") await parliamentReady();
      const request = await pressPreview();
      expect(screen.getByRole("button", { name: "Previewing…" })).toBeDisabled();
      act(() => useDraftStore.getState().setBudgetRateTarget("personalIncomeRateBps", 1700));
      expect(screen.getByRole("button", { name: "Preview" })).toBeEnabled();
      await request.failWithServerError();
      expect(screen.queryAllByRole("alert")).toHaveLength(0);
      // Back to the draft that failed: its error is its own.
      act(() => useDraftStore.getState().setBudgetRateTarget("personalIncomeRateBps", 1800));
      expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
    });
  }
});

describe("the retry-display rule (the latest attempt decides)", () => {
  for (const shown of ["parliament", "decisions"] as const) {
    const hasEstimate = shown === "parliament" ? parliamentShowsEstimate : decisionsShowsEstimate;

    it(`on ${shown}: (a) a retry hides the old error at once; its success shows with no error`, async () => {
      draftBudget();
      renderStage(shown);
      if (shown === "parliament") await parliamentReady();
      await (await pressPreview()).failWithServerError();
      expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
      fireEvent.click(screen.getByRole("button", { name: "Preview" }));
      expect(screen.queryAllByRole("alert")).toHaveLength(0);
      expect(screen.getByRole("button", { name: "Previewing…" })).toBeInTheDocument();
      await previewRequests[1]!.succeed();
      await waitFor(() => expect(hasEstimate()).toBe(true));
      expect(screen.queryAllByRole("alert")).toHaveLength(0);
    });

    it(`on ${shown}: (b) a failed retry hides the earlier verdict for the same draft`, async () => {
      draftBudget();
      renderStage(shown);
      if (shown === "parliament") await parliamentReady();
      await (await pressPreview()).succeed();
      await waitFor(() => expect(hasEstimate()).toBe(true));
      fireEvent.click(screen.getByRole("button", { name: "Preview" }));
      await previewRequests[1]!.failWithServerError();
      expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
      expect(hasEstimate()).toBe(false);
    });

    it(`on ${shown}: (c) a failure for an edited-away draft never shows during or after a new preview`, async () => {
      draftBudget();
      renderStage(shown);
      if (shown === "parliament") await parliamentReady();
      await (await pressPreview()).failWithServerError();
      act(() => useDraftStore.getState().setBudgetRateTarget("personalIncomeRateBps", 1700));
      expect(screen.queryAllByRole("alert")).toHaveLength(0);
      fireEvent.click(screen.getByRole("button", { name: "Preview" }));
      expect(screen.queryAllByRole("alert")).toHaveLength(0);
      await previewRequests[1]!.succeed();
      await waitFor(() => expect(hasEstimate()).toBe(true));
      expect(screen.queryAllByRole("alert")).toHaveLength(0);
    });
  }
});

describe("focus", () => {
  it("a Decisions preview landing after the player left moves no focus, now or on return", async () => {
    draftBudget();
    renderStage("decisions");
    const request = await pressPreview();
    control.show("none");
    const elsewhere = screen.getByTestId("elsewhere");
    elsewhere.focus();
    await request.succeed();
    expect(document.activeElement).toBe(elsewhere);
    control.show("decisions");
    await screen.findByTestId("consequences-panel");
    expect(document.activeElement?.id).not.toBe("preview-result-heading");
  });

  it("a Parliament preview never moves focus, and is announced only by the screen that asked", async () => {
    draftBudget();
    renderStage("decisions");
    const request = await pressPreview();
    control.show("parliament");
    await parliamentReady();
    const elsewhere = screen.getByTestId("elsewhere");
    elsewhere.focus();
    await request.succeed();
    await waitFor(() => expect(parliamentShowsEstimate()).toBe(true));
    expect(document.activeElement).toBe(elsewhere);
    expect(screen.getByTestId("parliament-announcement")).toHaveTextContent("");
  });
});

describe("the heading survives loading", () => {
  it("keeps the focused heading element when the data arrives (a place's focus is not lost)", async () => {
    let releaseOptions: () => void = () => {};
    const held = new Promise<void>((resolve) => {
      releaseOptions = resolve;
    });
    const base = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes("/api/game/decision-options")) await held;
      return base(input, init);
    });
    renderStage();
    const loadingHeading = await screen.findByRole("heading", { level: 2, name: "Legislature" });
    await screen.findByText("Loading the legislature…");
    loadingHeading.setAttribute("tabindex", "-1");
    loadingHeading.focus();
    await act(async () => {
      releaseOptions();
    });
    await parliamentReady();
    expect(screen.getByRole("heading", { level: 2, name: "Legislature" })).toBe(loadingHeading);
    expect(document.activeElement).toBe(loadingHeading);
  });
});
