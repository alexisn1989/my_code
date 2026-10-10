/**
 * Gate 4A3 W-1: decision reliability, from the playtest feedback.
 *
 *   1. Leaving Decisions used to lose the displayed card while its draft stayed staged: the
 *      selection was the screen's own state. It now lives in the draft store beside the draft.
 *   2. "Take no major action" used to change nothing: it has no routes, so the select handler's
 *      no-available-route guard returned before applying it. It now clears the proposal.
 *
 * Options are the server's real Valdrun catalogue (`src/test/decision-options-valdrun.json`).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DecisionOptionsProjection } from "../api/client";
import { cardMatchesDraft } from "../state/applyPolicyCard";
import { buildDecisions } from "../state/buildDecisionSet";
import { useDraftStore } from "../state/draft";
import { SessionProvider, useSession } from "../state/SessionContext";
import optionsJson from "../test/decision-options-valdrun.json";
import { OBJECTIVE_FIXTURE, OBJECTIVE_STAGES } from "../test/objectiveFixture";
import { ObjectiveCard } from "./ObjectivePanels";
import { DecisionsScreen } from "./screens/DecisionsScreen";

const OPTIONS = optionsJson as unknown as DecisionOptionsProjection;
const TAX_CARD = OPTIONS.policy_cards.find((card) => card.category === "taxation" && card.available)!;
const RESTRAINT = OPTIONS.policy_cards.find((card) => card.clears_proposal_slot)!;
const QUALIFYING = OPTIONS.policy_cards.find((card) => card.card_id === "constitution_qualifying_reform")!;

function concern(label: string) {
  return { label, headline: "x", delta_text: null, direction: "unchanged", tone: "neutral", detail_screen: "government" };
}

const DASHBOARD = {
  revision: "0.0",
  campaign_id: "campaign-1",
  turn: 0,
  country_name: "Kingdom of Valdrun",
  government_form: "Hereditary monarchy, unlimited decree authority",
  next_election_label: "None scheduled",
  concerns: {
    money: concern("Money"),
    legitimacy: concern("Legitimacy"),
    legislature: concern("Legislature"),
    constitution: concern("Constitution"),
    survival: concern("Survival"),
  },
  political_capital: { current: 500, capacity: 1000, committed_this_turn: 0, display: "500 / 1,000" },
  alerts: [],
  goal: { headline: "Nothing is pressing.", detail: null },
  objective: OBJECTIVE_FIXTURE,
  map: { presentation_only: true, tint_metric_label: "Legitimacy", tint_value_bps: 6000, note: "" },
  terminal: null,
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  useDraftStore.getState().clearDraft();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return json(DASHBOARD);
      if (url.includes("/api/game/decision-options")) return json(OPTIONS);
      return new Response(JSON.stringify({ detail: "not in this test" }), { status: 404 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function SetRevision({ children }: { children: ReactNode }) {
  const { setCampaignView, revision } = useSession();
  useEffect(() => {
    if (revision === null) setCampaignView("0.0", "campaign-1");
  }, [revision, setCampaignView]);
  return revision === null ? null : <>{children}</>;
}

function renderDecisions() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <SetRevision>
          <DecisionsScreen navigate={vi.fn()} />
        </SetRevision>
      </SessionProvider>
    </QueryClientProvider>,
  );
}

async function selectCard(major: RegExp, title: string): Promise<void> {
  fireEvent.click(await screen.findByRole("tab", { name: major }));
  const card = await screen.findByRole("group", { name: title });
  fireEvent.click(within(card).getByRole("button", { name: "Select" }));
}

describe("the displayed card survives leaving Decisions", () => {
  it("shows the same card, on its own tab, after Decisions unmounts and mounts again", async () => {
    const first = renderDecisions();
    await selectCard(/^Budget policy/, TAX_CARD.title);
    expect(useDraftStore.getState().selectedCardId).toBe(TAX_CARD.card_id);
    expect(screen.getByTestId("policy-selection-summary")).toHaveTextContent(TAX_CARD.title);
    first.unmount();

    renderDecisions();
    const summary = await screen.findByTestId("policy-selection-summary");
    expect(summary).toHaveTextContent(TAX_CARD.title);
    const card = await screen.findByRole("group", { name: TAX_CARD.title });
    expect(within(card).getByRole("button", { name: "Selected" })).toHaveAttribute("aria-pressed", "true");
    expect(useDraftStore.getState().policySlot).toBe("budget");
  });

  it("is cleared with the draft, and when the slot is changed by hand", async () => {
    useDraftStore.getState().setSelectedCardId(TAX_CARD.card_id);
    useDraftStore.getState().clearDraft();
    expect(useDraftStore.getState().selectedCardId).toBeNull();

    useDraftStore.getState().setSelectedCardId(TAX_CARD.card_id);
    useDraftStore.getState().setPolicySlot("amendment");
    expect(useDraftStore.getState().selectedCardId).toBeNull();
  });
});

describe('"Take no major action" clears the proposal', () => {
  it("replaces a staged budget with no proposal, and shows the restraint card selected", async () => {
    renderDecisions();
    await selectCard(/^Budget policy/, TAX_CARD.title);
    expect(useDraftStore.getState().policySlot).toBe("budget");
    expect(buildDecisions(useDraftStore.getState()).some((d) => d.kind === "budget")).toBe(true);

    fireEvent.click(screen.getByRole("tab", { name: /^Take no major action/ }));
    const restraint = await screen.findByRole("group", { name: RESTRAINT.title });
    fireEvent.click(within(restraint).getByRole("button", { name: "Select" }));

    await waitFor(() => expect(useDraftStore.getState().policySlot).toBeNull());
    const draft = useDraftStore.getState();
    expect(draft.selectedCardId).toBe(RESTRAINT.card_id);
    expect(draft.budget.personalIncomeRateBps).toBeUndefined();
    expect(buildDecisions(draft).filter((d) => d.kind === "budget" || d.kind === "constitutional_amendment")).toEqual([]);
    expect(screen.getByTestId("policy-selection-summary")).toHaveTextContent(RESTRAINT.title);
  });
});

describe("the displayed card is derived from the draft, so it cannot drift", () => {
  it("hides a budget card once its rate is edited by hand, and shows it again if the edit is undone", async () => {
    renderDecisions();
    await selectCard(/^Budget policy/, TAX_CARD.title);
    const original = useDraftStore.getState().budget.personalIncomeRateBps!;
    expect(cardMatchesDraft(TAX_CARD, useDraftStore.getState())).toBe(true);

    act(() => useDraftStore.getState().setBudgetRateTarget("personalIncomeRateBps", original + 1));
    expect(cardMatchesDraft(TAX_CARD, useDraftStore.getState())).toBe(false);
    await waitFor(() => expect(screen.getByTestId("policy-selection-summary")).toHaveTextContent("No policy selected yet."));
    expect(screen.getByTestId("policy-selection-summary")).not.toHaveTextContent(TAX_CARD.title);

    act(() => useDraftStore.getState().setBudgetRateTarget("personalIncomeRateBps", original));
    await waitFor(() => expect(screen.getByTestId("policy-selection-summary")).toHaveTextContent(TAX_CARD.title));
  });

  it("hides an amendment card once an axis is added by hand", async () => {
    renderDecisions();
    await selectCard(/^Constitutional reform/, QUALIFYING.title);
    expect(screen.getByTestId("policy-selection-summary")).toHaveTextContent(QUALIFYING.title);
    act(() => useDraftStore.getState().setAmendmentTarget("executive_term_limit_terms", 2));
    await waitFor(() => expect(screen.getByTestId("policy-selection-summary")).toHaveTextContent("No policy selected yet."));
  });

  it("matches 'Take no major action' exactly when no proposal is drafted", () => {
    const draft = useDraftStore.getState();
    expect(cardMatchesDraft(RESTRAINT, draft)).toBe(true);
    expect(cardMatchesDraft(TAX_CARD, draft)).toBe(false);
  });
});

describe('"Take no major action" clears the proposal and nothing else', () => {
  it("keeps appointments, investments, promises, assistance and movement; drops the bargain, and says so", async () => {
    const store = useDraftStore.getState();
    store.setInvestment("opposition_party", "main", 100);
    store.confirmAppointment("chief_of_staff", "someone");
    store.setPromise({ action: "make", characterId: "leader", termKind: "legislative_support", subjectId: "budget", deadlineTurn: 4 } as never);
    store.setAssistanceRequest("marnil");
    store.setMovementOrder("formation-1", "theater-2");
    renderDecisions();
    await selectCard(/^Budget policy/, TAX_CARD.title);
    act(() => useDraftStore.getState().setBargain("leader_independents", "budget"));
    const before = useDraftStore.getState();
    const kept = {
      investments: before.investments,
      cabinetOrders: before.cabinetOrders,
      promise: before.promise,
      assistance: before.assistance,
      movement: before.movement,
    };

    fireEvent.click(screen.getByRole("tab", { name: /^Take no major action/ }));
    const restraint = await screen.findByRole("group", { name: RESTRAINT.title });
    fireEvent.click(within(restraint).getByRole("button", { name: "Select" }));

    await waitFor(() => expect(useDraftStore.getState().policySlot).toBeNull());
    const after = useDraftStore.getState();
    expect({
      investments: after.investments,
      cabinetOrders: after.cabinetOrders,
      promise: after.promise,
      assistance: after.assistance,
      movement: after.movement,
    }).toEqual(kept);
    expect(after.investments).toEqual({ "opposition_party/main": 100 });
    expect(after.bargain).toBeNull();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your staged leader bargain was dropped too: it endorsed the proposal you cleared.",
    );
  });
});

describe("a finished campaign says how the transition ended", () => {
  it.each([
    ["concludedVictory", /^Qualifying transition: completed — the election on turn \d+ was won\.$/],
    ["concludedElectoralDefeat", /^Qualifying transition: not completed — the campaign ended by electoral defeat on turn \d+\.$/],
    ["concludedTermLimitExit", /^Qualifying transition: not completed — the campaign ended by term limit exit on turn \d+\.$/],
  ] as const)("%s", (name, expected) => {
    const objective = OBJECTIVE_STAGES[name];
    render(<ObjectiveCard dashboard={{ ...DASHBOARD, objective } as never} navigate={vi.fn()} />);
    const line = screen.getByTestId("objective-transition-text");
    expect(line.textContent).toMatch(expected);
    expect(screen.getByTestId("objective-card")).not.toHaveTextContent("not recorded");
    if (name !== "concludedVictory") {
      expect(screen.getByTestId("objective-card").textContent).not.toMatch(/transition: completed|was won/);
    }
  });
});
