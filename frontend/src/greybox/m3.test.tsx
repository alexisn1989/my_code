/**
 * Gate 4A3 M-3: the bloc panel, through the real Parliament screen.
 *
 * 1. one bargain, party-wide, counted over DISTINCT blocs;
 * 2. replacement, announced; keeping changes nothing;
 * 3. each action changes only its own draft field;
 * 4. disabled states and their reasons; a refusing leader shows no price; no counterpart;
 * 5. influence follows the active slot; clearing to zero removes it; investment is not influence;
 * 6. focus: open, Close, Escape, a vanished invoker, swapping blocs, aria-expanded;
 * 7. an investment's effect only from a CURRENT preview;
 * 8. no "projected";
 * 9. a concluded campaign with a populated draft and options: every action disabled;
 * 10. lifecycle: closes on revision and campaign change; a vanished bloc closes safely; data is live.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { buildDecisions, previewRequestSignature } from "../state/buildDecisionSet";
import { useDraftStore } from "../state/draft";
import { usePreviewStore } from "../state/previewStore";
import { SessionProvider, useSession } from "../state/SessionContext";
import { stagedActions } from "../state/stagedActions";
import { OBJECTIVE_FIXTURE } from "../test/objectiveFixture";
import VALDRUN_OPTIONS from "../test/decision-options-valdrun.json";
import { offerLine } from "../format/parliament";
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

const TERMINAL = { bucket: "defeat", headline: "The campaign has ended.", reason_label: "Electoral defeat", turn: 3 };

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

/** Reform Opposition has ONE bloc seated in two chambers (Main) plus another distinct bloc
 * (Hardliners, lower only): three rows, two blocs. */
const BLOCS = [
  bloc("gov", "Crown Party", "core", "Crown Party Core", "lower", 40, "coalition"),
  bloc("gov", "Crown Party", "core", "Crown Party Core", "upper", 30, "coalition"),
  bloc("opp", "Reform Opposition", "main", "Reform Opposition Main", "lower", 30, "opposition"),
  bloc("opp", "Reform Opposition", "main", "Reform Opposition Main", "upper", 20, "opposition"),
  bloc("opp", "Reform Opposition", "hard", "Reform Opposition Hardliners", "lower", 10, "opposition"),
  bloc("rural", "Rural Alliance", "farmers", "Rural Alliance Farmers", "lower", 15, "confidence_and_supply"),
  bloc("rural", "Rural Alliance", "farmers", "Rural Alliance Farmers", "upper", 10, "confidence_and_supply"),
  bloc("nf", "National Front", "cons", "National Front Conservatives", "lower", 5, "opposition"),
];

function leader(party_id: string, party: string, id: string, name: string, price: number | null) {
  return {
    character_id: id,
    display_name: name,
    portrait_ref: "portrait_leader_opposition_party",
    party_id,
    party_display_name: party,
    loyalty_bps: 5000,
    independence_bps: 6100,
    ambition_bps: 4400,
    personal_trust_bps: 5200,
    will_deal: price !== null,
    asking_price: price,
    refusal_reason: price === null ? "refused_will_not_deal" : null,
  };
}

const LEADERS = [
  leader("opp", "Reform Opposition", "l-opp", "Ilsa Varn", 105),
  leader("rural", "Rural Alliance", "l-rural", "Maret Kuusk", 90),
  leader("nf", "National Front", "l-nf", "Gustav Reiner", null),
];

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
  legislative_bargain_counterparties: LEADERS,
  last_recorded_vote: null,
  relationship_investment_minimum: 1,
  relationship_investment_maximum: 200,
};

let dashboardBody: Record<string, unknown> = DASHBOARD;
let optionsBody: Record<string, unknown> = OPTIONS;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  dashboardBody = DASHBOARD;
  optionsBody = OPTIONS;
  useDraftStore.getState().clearDraft();
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return Promise.resolve(json(dashboardBody));
      if (url.includes("/api/game/decision-options")) return Promise.resolve(json(optionsBody));
      throw new Error(`unexpected fetch: ${url}`);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---- Harness -------------------------------------------------------------------------------------

const control: { setView: (r: string, c: string) => void; refetch: () => Promise<void> } = {
  setView: () => {},
  refetch: async () => {},
};

function SetView({ children }: { children: ReactNode }) {
  const { setCampaignView, revision } = useSession();
  control.setView = (r, c) => setCampaignView(r, c);
  useEffect(() => {
    if (revision === null) setCampaignView("rev-1", "campaign-1");
  }, [revision, setCampaignView]);
  return revision === null ? null : <>{children}</>;
}

function renderParliament() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  control.refetch = async () => {
    await act(async () => {
      await client.invalidateQueries();
    });
  };
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <SetView>
          <ParliamentScreen navigate={vi.fn()} />
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

/** The draft's DATA (no functions), for deep-equality checks. */
function draftData() {
  const s = useDraftStore.getState();
  return JSON.parse(JSON.stringify(s)) as Record<string, unknown>;
}

async function ready() {
  await screen.findAllByTestId("chamber-card");
}

function openButton(chamber: string, key: string): HTMLButtonElement {
  const cardNode = screen.getAllByTestId("chamber-card").find((c) => c.dataset.chamber === chamber)!;
  return cardNode.querySelector<HTMLButtonElement>(`[data-bloc-open="${key}"]`)!;
}

async function openPanel(chamber: string, key: string) {
  fireEvent.click(openButton(chamber, key));
  return screen.findByTestId("bloc-panel");
}

const panel = () => screen.getByTestId("bloc-panel");
const announcement = () => screen.getByTestId("parliament-announcement").textContent;

// ---- 1. One bargain, party-wide, over distinct blocs -----------------------------------------------

describe("1. one bargain, party-wide", () => {
  it("shows the same staged bargain under every bloc of the party, counting distinct blocs (2, not 3 rows)", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    fireEvent.click(within(panel()).getByRole("button", { name: "Stage this bargain · 105" }));
    expect(useDraftStore.getState().bargain).toEqual({ characterId: "l-opp", proposalKind: "budget" });
    expect(within(panel()).getByTestId("bargain-staged-here")).toHaveTextContent(
      "Staged: endorsement from Ilsa Varn, which applies to all 2 blocs of Reform Opposition.",
    );
    await openPanel("lower", "opp/hard");
    expect(within(panel()).getByTestId("bargain-staged-here")).toHaveTextContent("applies to all 2 blocs");
    // Opened from the upper chamber, where the party seats only one bloc: the count is still taken
    // across every chamber (2), never from the opening chamber alone (1).
    await openPanel("upper", "opp/main");
    expect(within(panel()).getByTestId("bargain-staged-here")).toHaveTextContent(
      "applies to all 2 blocs of Reform Opposition.",
    );
    expect(stagedActions(useDraftStore.getState()).filter((a) => a.kind === "bargain")).toHaveLength(1);
  });
});

// ---- 2. Replacement ---------------------------------------------------------------------------------

describe("2. replacement", () => {
  it("names the bargain it replaces, replaces it, and announces the replacement", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    fireEvent.click(within(panel()).getByRole("button", { name: "Stage this bargain · 105" }));
    await openPanel("lower", "rural/farmers");
    expect(within(panel()).getByTestId("bargain-replace")).toHaveTextContent(
      "You already have a bargain staged: Ilsa Varn's endorsement, for 105.",
    );
    const before = draftData();
    fireEvent.click(within(panel()).getByRole("button", { name: "Keep Ilsa Varn's bargain" }));
    expect(draftData()).toEqual(before);
    fireEvent.click(within(panel()).getByRole("button", { name: "Replace bargain with Maret Kuusk · 90" }));
    expect(useDraftStore.getState().bargain).toEqual({ characterId: "l-rural", proposalKind: "budget" });
    expect(announcement()).toBe("Replaced your staged bargain with Ilsa Varn by Maret Kuusk.");
  });
});

// ---- 3. Draft isolation -----------------------------------------------------------------------------

describe("3. each action changes only its own field", () => {
  function without(data: Record<string, unknown>, path: string[]) {
    const copy = JSON.parse(JSON.stringify(data)) as Record<string, any>;
    let node = copy;
    for (const key of path.slice(0, -1)) node = node[key];
    delete node[path[path.length - 1]!];
    return copy;
  }

  it("the bargain", async () => {
    draftBudget();
    act(() => useDraftStore.getState().setBudgetInfluence("gov", "core", 7));
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    const before = draftData();
    fireEvent.click(within(panel()).getByRole("button", { name: "Stage this bargain · 105" }));
    expect(without(draftData(), ["bargain"])).toEqual(without(before, ["bargain"]));
    expect(useDraftStore.getState().budget.influence).toEqual({ "gov/core": 7 });
  });

  it("influence", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    const before = draftData();
    fireEvent.change(within(panel()).getByTestId("panel-influence"), { target: { value: "40" } });
    expect(without(draftData(), ["budget", "influence"])).toEqual(without(before, ["budget", "influence"]));
    expect(useDraftStore.getState().budget.influence).toEqual({ "opp/main": 40 });
  });

  it("investment", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    const before = draftData();
    fireEvent.change(within(panel()).getByTestId("panel-investment"), { target: { value: "25" } });
    expect(without(draftData(), ["investments"])).toEqual(without(before, ["investments"]));
    expect(useDraftStore.getState().investments).toEqual({ "opp/main": 25 });
  });
});

// ---- 4. Disabled states --------------------------------------------------------------------------

describe("4. disabled states and their reasons", () => {
  it("with no proposal: the bargain and influence are disabled with the reason", async () => {
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    expect(within(panel()).getByRole("button", { name: "Stage this bargain · 105" })).toBeDisabled();
    // Gate 4A3 M-5 (F2): with nothing drafted there is no budget to name.
    expect(within(panel()).getByTestId("leader-offer")).toHaveTextContent(/^Endorse your proposal\. /);
    expect(panel().textContent ?? "").not.toContain("Endorse your budget");
    expect(within(panel()).getByTestId("bargain-blocked-reason")).toHaveTextContent("Put a budget or an amendment");
    expect(within(panel()).getByTestId("panel-influence")).toBeDisabled();
    expect(within(panel()).getByTestId("influence-blocked-reason")).toHaveTextContent("Put a budget or an amendment");
    fireEvent.click(within(panel()).getByRole("button", { name: "Stage this bargain · 105" }));
    expect(useDraftStore.getState().bargain).toBeNull();
  });

  it("names what is drafted in the offer, and only that (F2)", () => {
    expect([offerLine("budget"), offerLine("amendment"), offerLine(null)]).toEqual([
      "Endorse your budget.",
      "Endorse your constitutional amendment.",
      "Endorse your proposal.",
    ]);
  });

  it("on the decree route: disabled with the decree reason", async () => {
    draftBudget();
    act(() => useDraftStore.getState().setBudgetRoute("decree"));
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    expect(within(panel()).getByRole("button", { name: "Stage this bargain · 105" })).toBeDisabled();
    expect(within(panel()).getByTestId("bargain-blocked-reason")).toHaveTextContent("being decreed");
    expect(within(panel()).getByTestId("influence-blocked-reason")).toHaveTextContent("being decreed");
  });

  it("a refusing leader shows no price; a party with no counterpart says so", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "nf/cons");
    expect(within(panel()).getByTestId("leader-refuses")).toHaveTextContent("Will not deal at any price.");
    expect(within(panel()).queryByTestId("leader-offer")).toBeNull();
    expect(within(panel()).getByTestId("bloc-leader").textContent ?? "").not.toMatch(/\d+ political capital/);
    await openPanel("lower", "gov/core");
    expect(within(panel()).getByTestId("no-counterpart")).toHaveTextContent("No leader of Crown Party offers a bargain.");
  });
});

// ---- 5. Influence and investment -------------------------------------------------------------------

describe("5. influence follows the active slot; investment is not influence", () => {
  it("writes and summarises the active slot only", async () => {
    draftBudget();
    act(() => {
      useDraftStore.getState().setBudgetInfluence("opp", "main", 10);
      useDraftStore.getState().setAmendmentInfluence("opp", "main", 20);
    });
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    expect(within(panel()).getByTestId("bloc-staged")).toHaveTextContent("Influence on this vote: 10 capital (on your budget).");
    act(() => {
      useDraftStore.getState().setPolicySlot("amendment");
      useDraftStore.getState().setAmendmentTarget("decree_authority", "none");
    });
    expect(within(panel()).getByTestId("bloc-staged")).toHaveTextContent(
      "Influence on this vote: 20 capital (on your constitutional amendment).",
    );
    fireEvent.change(within(panel()).getByTestId("panel-influence"), { target: { value: "30" } });
    expect(useDraftStore.getState().amendment.influence).toEqual({ "opp/main": 30 });
    expect(useDraftStore.getState().budget.influence).toEqual({ "opp/main": 10 });
  });

  it("clearing to zero, or emptying the field, removes the entry and changes no staged-action count", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    const count = stagedActions(useDraftStore.getState()).length;
    const input = within(panel()).getByTestId("panel-influence");
    fireEvent.change(input, { target: { value: "40" } });
    expect(stagedActions(useDraftStore.getState()).length).toBe(count);
    fireEvent.change(input, { target: { value: "0" } });
    expect(useDraftStore.getState().budget.influence).toEqual({});
    expect(within(panel()).getByTestId("bloc-staged")).not.toHaveTextContent("Influence on this vote");
    const built = JSON.stringify(buildDecisions(useDraftStore.getState()));
    expect(built).not.toContain('"influence"');
    fireEvent.change(input, { target: { value: "15" } });
    fireEvent.change(input, { target: { value: "" } });
    expect(useDraftStore.getState().budget.influence).toEqual({});
    expect(stagedActions(useDraftStore.getState()).length).toBe(count);
  });

  it("an investment is written to investments, never to influence", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    fireEvent.change(within(panel()).getByTestId("panel-investment"), { target: { value: "25" } });
    expect(useDraftStore.getState().investments).toEqual({ "opp/main": 25 });
    expect(useDraftStore.getState().budget.influence).toEqual({});
    expect(useDraftStore.getState().amendment.influence).toEqual({});
  });
});

// ---- 6. Focus ---------------------------------------------------------------------------------------

describe("6. focus", () => {
  it("opens to its heading, and Close and Escape return to the invoking button", async () => {
    draftBudget();
    renderParliament();
    await ready();
    const invoker = openButton("lower", "opp/main");
    await openPanel("lower", "opp/main");
    await waitFor(() => expect(document.activeElement).toBe(within(panel()).getByRole("heading", { level: 3 })));
    expect(invoker).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(within(panel()).getByRole("button", { name: "Close Reform Opposition Main" }));
    await waitFor(() => expect(document.activeElement).toBe(openButton("lower", "opp/main")));
    expect(screen.queryByTestId("bloc-panel")).toBeNull();
    expect(openButton("lower", "opp/main")).toHaveAttribute("aria-expanded", "false");

    await openPanel("lower", "opp/main");
    fireEvent.keyDown(within(panel()).getByTestId("panel-investment"), { key: "Escape" });
    await waitFor(() => expect(document.activeElement).toBe(openButton("lower", "opp/main")));
  });

  it("staging moves focus to the staged line, and withdrawing back to Stage (focus never falls to the page)", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    const stageButton = within(panel()).getByRole("button", { name: "Stage this bargain · 105" });
    stageButton.focus();
    fireEvent.click(stageButton);
    await waitFor(() => expect(document.activeElement).toBe(within(panel()).getByTestId("bargain-staged-here")));
    fireEvent.click(within(panel()).getByRole("button", { name: "Withdraw bargain" }));
    await waitFor(() =>
      expect(document.activeElement).toBe(within(panel()).getByRole("button", { name: "Stage this bargain · 105" })),
    );
  });

  it("another bloc swaps the content and focuses its heading", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    fireEvent.click(openButton("upper", "rural/farmers"));
    await waitFor(() =>
      expect(document.activeElement).toBe(within(panel()).getByRole("heading", { level: 3, name: "Rural Alliance Farmers" })),
    );
    expect(screen.getAllByTestId("bloc-panel")).toHaveLength(1);
  });

  it("with the invoking button gone, Close sends focus to its chamber's heading", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    // The bloc leaves the lower chamber but still sits in the upper one: the panel stays, its invoker does not.
    optionsBody = { ...OPTIONS, blocs: BLOCS.filter((b) => !(b.bloc_id === "main" && b.chamber === "lower")) };
    await control.refetch();
    await waitFor(() => expect(openButton("lower", "gov/core")).toBeTruthy());
    expect(screen.getByTestId("bloc-panel")).toBeInTheDocument();
    fireEvent.click(within(panel()).getByRole("button", { name: "Close Reform Opposition Main" }));
    await waitFor(() => expect(document.activeElement?.id).toBe("chamber-lower"));
  });
});

// ---- 7. Effects only from a current preview --------------------------------------------------------

describe("7. an investment's effect comes only from a current preview", () => {
  const effectRow = {
    party_id: "opp",
    bloc_id: "main",
    bloc_display_name: "Reform Opposition Main",
    political_capital: 25,
    opening_relationship_bps: -2000,
    gain_bps: 300,
    chief_of_staff_bonus_bps: 0,
    no_effect: false,
  };

  function storePreview(signatureDraft: ReturnType<typeof useDraftStore.getState>) {
    const store = usePreviewStore.getState();
    const token = store.begin(previewRequestSignature(signatureDraft, "rev-1", "campaign-1"));
    store.accept(token, { chambers: [], investment_effects: [effectRow], route: "legislative" } as never);
  }

  it("shows the effect for a current preview and not for a stale one", async () => {
    draftBudget();
    act(() => useDraftStore.getState().setInvestment("opp", "main", 25));
    renderParliament();
    await ready();
    act(() => storePreview(useDraftStore.getState()));
    await openPanel("lower", "opp/main");
    expect(within(panel()).getByTestId("investment-effect")).toHaveTextContent("Reform Opposition Main: +3.00 points from 25 capital");
    act(() => useDraftStore.getState().setInvestment("opp", "main", 30));
    expect(within(panel()).getByTestId("investment-effect")).toHaveTextContent("Preview shows what it would add.");
  });
});

// ---- 8. Copy -------------------------------------------------------------------------------------

describe("8. copy", () => {
  it("never says 'projected'", async () => {
    draftBudget();
    const { container } = renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    expect(container.textContent?.toLowerCase()).not.toContain("projected");
  });
});

// ---- 9. A concluded campaign with a populated state ----------------------------------------------

describe("9. a concluded campaign", () => {
  it("disables every action even with a populated draft and options, and nothing changes", async () => {
    draftBudget();
    act(() => {
      useDraftStore.getState().setBargain("l-opp", "budget");
      useDraftStore.getState().setBudgetInfluence("opp", "main", 40);
      useDraftStore.getState().setInvestment("opp", "main", 25);
    });
    dashboardBody = { ...DASHBOARD, terminal: TERMINAL };
    renderParliament();
    await ready();
    const before = draftData();

    await openPanel("lower", "opp/main");
    const withdraw = within(panel()).getByRole("button", { name: "Withdraw bargain" });
    expect(withdraw).toBeDisabled();
    expect(within(panel()).getByTestId("panel-influence")).toBeDisabled();
    expect(within(panel()).getByTestId("panel-investment")).toBeDisabled();
    expect(within(panel()).getByTestId("influence-blocked-reason")).toHaveTextContent("The campaign has ended.");
    fireEvent.click(withdraw);
    fireEvent.change(within(panel()).getByTestId("panel-influence"), { target: { value: "99" } });
    fireEvent.change(within(panel()).getByTestId("panel-investment"), { target: { value: "99" } });

    await openPanel("lower", "rural/farmers");
    const replace = within(panel()).getByRole("button", { name: "Replace bargain with Maret Kuusk · 90" });
    const keep = within(panel()).getByRole("button", { name: "Keep Ilsa Varn's bargain" });
    expect(replace).toBeDisabled();
    expect(keep).toBeDisabled();
    expect(within(panel()).getByTestId("bargain-blocked-reason")).toHaveTextContent("The campaign has ended.");
    fireEvent.click(replace);

    expect(draftData()).toEqual(before);
  });
});

// ---- 10. Lifecycle ---------------------------------------------------------------------------------

describe("10. lifecycle", () => {
  it("closes when the revision changes, and when the campaign changes", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    act(() => control.setView("rev-2", "campaign-1"));
    await waitFor(() => expect(screen.queryByTestId("bloc-panel")).toBeNull());
    act(() => control.setView("rev-1", "campaign-1"));
    await ready();
    await openPanel("lower", "opp/main");
    act(() => control.setView("rev-1", "campaign-2"));
    await waitFor(() => expect(screen.queryByTestId("bloc-panel")).toBeNull());
  });

  it("a bloc gone from the options closes the panel safely; focus falls back to its chamber, then the screen", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "opp/hard");
    within(panel()).getByTestId("panel-investment").focus();
    optionsBody = { ...OPTIONS, blocs: BLOCS.filter((b) => b.bloc_id !== "hard") };
    await control.refetch();
    await waitFor(() => expect(screen.queryByTestId("bloc-panel")).toBeNull());
    expect(document.activeElement?.id).toBe("chamber-lower");

    // With its chamber gone too, focus falls back to the screen heading.
    optionsBody = OPTIONS;
    await control.refetch();
    await openPanel("upper", "rural/farmers");
    within(panel()).getByTestId("panel-investment").focus();
    optionsBody = {
      ...OPTIONS,
      chamber_details: OPTIONS.chamber_details.filter((d) => d.chamber !== "upper"),
      blocs: BLOCS.filter((b) => b.chamber !== "upper" && b.bloc_id !== "farmers"),
    };
    await control.refetch();
    await waitFor(() => expect(screen.queryByTestId("bloc-panel")).toBeNull());
    expect(document.activeElement?.id).toBe("parliament-heading");
  });

  it("reads the leader from the current options: a changed price shows at once", async () => {
    draftBudget();
    renderParliament();
    await ready();
    await openPanel("lower", "opp/main");
    expect(within(panel()).getByRole("button", { name: "Stage this bargain · 105" })).toBeInTheDocument();
    optionsBody = {
      ...OPTIONS,
      legislative_bargain_counterparties: LEADERS.map((l) => (l.party_id === "opp" ? { ...l, asking_price: 140 } : l)),
    };
    await control.refetch();
    await waitFor(() =>
      expect(within(panel()).getByRole("button", { name: "Stage this bargain · 140" })).toBeInTheDocument(),
    );
  });
});
