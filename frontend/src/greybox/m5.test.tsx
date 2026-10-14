/**
 * Gate 4A3 M-5 (consolidation, gap G2): staging from the bloc panel is the SAME draft as staging the
 * same things on the existing screens, and the draft survives moving between screens.
 *
 * 1. Equality: Maret Kuusk's bargain, influence on her bloc and an investment in it, staged
 *    (a) through Parliament's bloc panel and (b) through Relationships (the bargain) and Decisions
 *    (influence and investment), give a deep-equal `buildDecisions()` and `stagedActions()`.
 * 2. Persistence: Decisions -> Dashboard -> Parliament -> Decisions -> Parliament, mounting each
 *    real screen in turn: the selected card and every staged action survive every step, Decisions
 *    still shows the card as selected, and the panel still shows the bargain as staged.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { buildDecisions } from "../state/buildDecisionSet";
import { useDraftStore } from "../state/draft";
import { SessionProvider, useSession } from "../state/SessionContext";
import { stagedActions } from "../state/stagedActions";
import { OBJECTIVE_FIXTURE } from "../test/objectiveFixture";
import VALDRUN_OPTIONS from "../test/decision-options-valdrun.json";
import { DashboardScreen } from "./screens/DashboardScreen";
import { DecisionsScreen } from "./screens/DecisionsScreen";
import { MeetingScreen } from "./screens/MeetingScreen";
import { ParliamentScreen } from "./screens/ParliamentScreen";

// ---- Fixtures (the M-3 shapes) ---------------------------------------------------------------------

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
    legislature: card("Legislature", "4 parties, 160 seats", "legislature"),
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

function bloc(party_id: string, party_name: string, bloc_id: string, bloc_name: string, chamber: string, seats: number, role: string) {
  return {
    party_id,
    party_name,
    bloc_id,
    bloc_name,
    chamber,
    seats,
    government_role: role,
    government_relationship_bps: role === "opposition" ? -2000 : 4000,
    tax_preference_bps: -1000,
    spending_preference_bps: 3000,
  };
}

const BLOCS = [
  bloc("gov", "Crown Party", "core", "Crown Party Core", "lower", 40, "coalition"),
  bloc("gov", "Crown Party", "core", "Crown Party Core", "upper", 30, "coalition"),
  bloc("opp", "Reform Opposition", "main", "Reform Opposition Main", "lower", 45, "opposition"),
  bloc("opp", "Reform Opposition", "main", "Reform Opposition Main", "upper", 20, "opposition"),
  bloc("rural", "Rural Alliance", "farmers", "Rural Alliance Farmers", "lower", 15, "confidence_and_supply"),
  bloc("rural", "Rural Alliance", "farmers", "Rural Alliance Farmers", "upper", 10, "confidence_and_supply"),
];

const MARET = {
  character_id: "l-rural",
  display_name: "Maret Kuusk",
  portrait_ref: "portrait_leader_rural_alliance",
  party_id: "rural",
  party_display_name: "Rural Alliance",
  loyalty_bps: 5000,
  independence_bps: 6100,
  ambition_bps: 4400,
  personal_trust_bps: 5200,
  will_deal: true,
  asking_price: 90,
  refusal_reason: null,
};

const OPTIONS = {
  ...VALDRUN_OPTIONS,
  revision: "rev-1",
  campaign_id: "campaign-1",
  chambers: ["lower", "upper"],
  chamber_details: [
    { chamber: "lower", total_seats: 100, budget_required_seats: 51, amendment_required_seats: 67 },
    { chamber: "upper", total_seats: 60, budget_required_seats: 31, amendment_required_seats: 40 },
  ],
  blocs: BLOCS,
  legislative_bargain_counterparties: [MARET],
  last_recorded_vote: null,
  relationship_investment_minimum: 1,
  relationship_investment_maximum: 200,
};

const TAX_CARD = "Lower the personal income tax";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  useDraftStore.getState().clearDraft();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return json(DASHBOARD);
      if (url.includes("/api/game/decision-options")) return json(OPTIONS);
      // Anything else (the strategic map behind the Dashboard's country picture) is not what these
      // tests are about; a 404 leaves those parts in their error state and touches no draft.
      return json({ detail: "not in this test" }, 404);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  useDraftStore.getState().clearDraft();
});

// ---- Harness -------------------------------------------------------------------------------------

function SetView({ children }: { children: ReactNode }) {
  const { setCampaignView, revision } = useSession();
  useEffect(() => {
    if (revision === null) setCampaignView("rev-1", "campaign-1");
  }, [revision, setCampaignView]);
  return revision === null ? null : <>{children}</>;
}

function mount(element: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <SetView>{element}</SetView>
      </SessionProvider>
    </QueryClientProvider>,
  );
}

/** The submitted decisions and the staged actions -- the two things every surface must agree on. */
function snapshot() {
  const state = useDraftStore.getState();
  return {
    decisions: JSON.parse(JSON.stringify(buildDecisions(state))) as unknown,
    staged: JSON.parse(JSON.stringify(stagedActions(state))) as unknown,
  };
}

/** The draft's DATA (no functions). */
function draftData() {
  return JSON.parse(JSON.stringify(useDraftStore.getState())) as Record<string, unknown>;
}

async function selectTaxCardOnDecisions() {
  fireEvent.click(await screen.findByRole("tab", { name: /^Budget policy/ }));
  const group = await screen.findByRole("group", { name: TAX_CARD });
  fireEvent.click(within(group).getByRole("button", { name: "Select" }));
}

async function openFarmers() {
  const cardNode = (await screen.findAllByTestId("chamber-card")).find((c) => c.dataset.chamber === "lower")!;
  fireEvent.click(cardNode.querySelector<HTMLButtonElement>('[data-bloc-open="rural/farmers"]')!);
  return screen.findByTestId("bloc-panel");
}

// ---- 1. Equality -----------------------------------------------------------------------------------

describe("staging from the bloc panel is the same draft as staging on the existing screens", () => {
  it("bargain + influence + investment: deep-equal decisions and staged actions", async () => {
    // (a) The bloc panel.
    let view = mount(<DecisionsScreen navigate={vi.fn()} />);
    await selectTaxCardOnDecisions();
    view.unmount();
    view = mount(<ParliamentScreen navigate={vi.fn()} />);
    const panel = await openFarmers();
    fireEvent.click(within(panel).getByRole("button", { name: "Stage this bargain · 90" }));
    fireEvent.change(within(screen.getByTestId("bloc-panel")).getByTestId("panel-influence"), { target: { value: "25" } });
    fireEvent.change(within(screen.getByTestId("bloc-panel")).getByTestId("panel-investment"), { target: { value: "30" } });
    const fromPanel = snapshot();
    view.unmount();

    // Anti-vacuity: all three actions (and the proposal) are really there.
    const kinds = (fromPanel.decisions as { kind: string }[]).map((d) => d.kind).sort();
    expect(kinds).toEqual(["bloc_relationship_investment", "budget", "legislative_bargain"]);
    expect(JSON.stringify(fromPanel.decisions)).toContain('"political_capital":25');

    // (b) Relationships for the bargain, Decisions for influence and investment.
    act(() => useDraftStore.getState().clearDraft());
    view = mount(<DecisionsScreen navigate={vi.fn()} />);
    await selectTaxCardOnDecisions();
    fireEvent.change(await screen.findByLabelText("Influence capital for Rural Alliance Farmers"), { target: { value: "25" } });
    fireEvent.change(screen.getByLabelText("Relationship investment for Rural Alliance Farmers"), { target: { value: "30" } });
    view.unmount();
    view = mount(<MeetingScreen navigate={vi.fn()} />);
    await screen.findByTestId("meeting-panel");
    fireEvent.click(document.querySelector<HTMLButtonElement>("[data-leader-option='l-rural']")!);
    fireEvent.click(await screen.findByTestId("confirm-meeting"));
    const fromScreens = snapshot();
    view.unmount();

    expect(fromScreens).toEqual(fromPanel);
  });
});

// ---- 2. Persistence across screens ---------------------------------------------------------------

describe("the draft survives Dashboard -> Parliament -> Decisions -> back", () => {
  it("keeps the selected card and every staged action at every step", async () => {
    let view = mount(<DecisionsScreen navigate={vi.fn()} />);
    await selectTaxCardOnDecisions();
    const cardId = useDraftStore.getState().selectedCardId;
    expect(cardId).not.toBeNull();
    view.unmount();

    view = mount(<DashboardScreen navigate={vi.fn()} />);
    await screen.findByTestId("objective-card");
    view.unmount();
    expect(useDraftStore.getState().selectedCardId).toBe(cardId);

    view = mount(<ParliamentScreen navigate={vi.fn()} />);
    const panel = await openFarmers();
    fireEvent.click(within(panel).getByRole("button", { name: "Stage this bargain · 90" }));
    fireEvent.change(within(screen.getByTestId("bloc-panel")).getByTestId("panel-influence"), { target: { value: "25" } });
    const staged = draftData();
    view.unmount();

    view = mount(<DecisionsScreen navigate={vi.fn()} />);
    const group = await screen.findByRole("group", { name: TAX_CARD });
    expect(within(group).getByRole("button", { name: "Selected" })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByTestId("staged-actions")).toHaveTextContent("Maret Kuusk");
    expect(screen.getByLabelText("Influence capital for Rural Alliance Farmers")).toHaveValue(25);
    expect(draftData()).toEqual(staged);
    view.unmount();

    view = mount(<ParliamentScreen navigate={vi.fn()} />);
    const again = await openFarmers();
    expect(within(again).getByTestId("bargain-staged-here")).toHaveTextContent("Maret Kuusk");
    expect(draftData()).toEqual(staged);
    expect(useDraftStore.getState().selectedCardId).toBe(cardId);
    view.unmount();
  });
});
