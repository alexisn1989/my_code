/**
 * Gate 4A3 victory path (V-2): the objective card, the Constitution screen, the links into
 * Decisions, the preview's "If enacted" sentence and the result's objective line.
 *
 * Every objective, option set, preview and result here is the SERVER'S output for a state reached
 * by real resolved turns (`src/test/*.json`, pinned by `backend/tests/test_objective_fixtures.py`).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DecisionOptionsProjection, PreviewProjection, TurnResultProjection } from "../api/client";
import { useDraftStore } from "../state/draft";
import { SessionProvider, useSession } from "../state/SessionContext";
import optionsJson from "../test/decision-options-valdrun.json";
import { OBJECTIVE_STAGES, type ObjectiveFixture } from "../test/objectiveFixture";
import results from "../test/objective-results.json";
import { ObjectiveCard } from "./ObjectivePanels";
import { ConsequencesPanel } from "./policy/ConsequencesPanel";
import { QUALIFYING_REFORM_CARD_ID } from "./policy/groupPolicyCards";
import { ConstitutionScreen } from "./screens/ConstitutionScreen";
import { DecisionsScreen } from "./screens/DecisionsScreen";
import { TurnResultView } from "./TurnResultView";

const OPTIONS = optionsJson as unknown as DecisionOptionsProjection;

function concern(label: string, headline: string, detail_screen: string) {
  return { label, headline, delta_text: null, direction: "unchanged", tone: "neutral", detail_screen };
}

function dashboard(objective: ObjectiveFixture) {
  return {
    revision: "0.0",
    campaign_id: "campaign-1",
    turn: 0,
    country_name: "Kingdom of Valdrun",
    government_form: "Hereditary monarchy, unlimited decree authority",
    next_election_label: "None scheduled",
    concerns: {
      money: concern("Money", "100,000,000.00", "economy"),
      legitimacy: concern("Legitimacy", "60.00%", "government"),
      legislature: concern("Legislature", "2 parties, 100 seats", "legislature"),
      constitution: concern("Constitution", "Supermajority", "constitution"),
      survival: concern("Survival", "Coup risk 10.72%", "government"),
    },
    political_capital: { current: 500, capacity: 1000, committed_this_turn: 0, display: "500 / 1,000" },
    alerts: [],
    goal: { headline: "Nothing is pressing.", detail: null },
    objective,
    map: { presentation_only: true, tint_metric_label: "Legitimacy", tint_value_bps: 6000, note: "" },
    terminal: null,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

let currentDashboard = dashboard(OBJECTIVE_STAGES.reform);
let currentOptions: DecisionOptionsProjection = OPTIONS;

beforeEach(() => {
  currentDashboard = dashboard(OBJECTIVE_STAGES.reform);
  currentOptions = OPTIONS;
  useDraftStore.getState().clearDraft();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return json(currentDashboard);
      if (url.includes("/api/game/decision-options")) return json(currentOptions);
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
    if (revision === null) setCampaignView("0.0", "campaign-1");
  }, [revision, setCampaignView]);
  return revision === null ? null : <>{children}</>;
}

function withCampaign(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <SetRevision>{ui}</SetRevision>
      </SessionProvider>
    </QueryClientProvider>,
  );
}

async function axeClean(container: HTMLElement, what: string): Promise<void> {
  // jsdom cannot judge colour contrast (no layout); the browser `victory` project does.
  const outcome = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(outcome.passes.length + outcome.inapplicable.length, `${what}: axe evaluated rules`).toBeGreaterThan(0);
  expect(outcome.violations.map((v) => v.id), what).toEqual([]);
}

const ALL_STAGES = Object.entries(OBJECTIVE_STAGES) as [keyof typeof OBJECTIVE_STAGES, ObjectiveFixture][];

describe("the Dashboard's campaign objective card", () => {
  it.each(ALL_STAGES)("%s: shows the server's stage, words and actions, with no percentage", async (name, objective) => {
    const navigate = vi.fn();
    const { container } = render(
      <ObjectiveCard dashboard={dashboard(objective) as never} navigate={navigate} />,
    );
    const card = screen.getByTestId("objective-card");
    expect(card).toHaveAttribute("data-stage", objective.stage);
    expect(within(card).getByTestId("objective-headline")).toHaveTextContent(objective.headline);
    expect(within(card).getByTestId("objective-conditions-text")).toHaveTextContent(objective.conditions_text);
    expect(within(card).getByTestId("objective-transition-text")).toHaveTextContent(objective.transition_text);
    expect(within(card).getByTestId("objective-summary").textContent).not.toMatch(/%/);
    if (objective.stage === "concluded") {
      expect(within(card).queryByRole("button")).toBeNull();
      expect(within(card).queryByTestId("objective-condition-words")).toBeNull();
    } else {
      const words = within(card).getByTestId("objective-condition-words");
      for (const condition of objective.conditions) {
        expect(words).toHaveTextContent(`${condition.label}: ${condition.met ? "Met" : "Not yet"}`);
      }
      fireEvent.click(within(card).getByRole("button", { name: "Review reforms" }));
      expect(navigate).toHaveBeenCalledWith("constitution");
    }
    if (objective.stage === "qualifying_election") {
      const risks = within(card).getByTestId("objective-risks");
      expect(risks).toHaveTextContent("Survival: Coup risk 10.72%");
      expect(risks).toHaveTextContent("Legitimacy: 60.00%");
    } else {
      expect(within(card).queryByTestId("objective-risks")).toBeNull();
    }
    await axeClean(container, `objective card (${name})`);
  });
});

describe("the Constitution screen", () => {
  it("lists the three conditions in words, with a link per unmet one and the qualifying reform", async () => {
    const navigate = vi.fn();
    const { container } = withCampaign(<ConstitutionScreen navigate={navigate} />);
    const list = await screen.findByTestId("constitution-checklist");
    const rows = within(list).getAllByRole("listitem");
    expect(rows.map((row) => row.getAttribute("data-condition"))).toEqual([
      "elected_executive",
      "no_decree_authority",
      "election_interval",
    ]);
    for (const row of rows) {
      expect(within(row).getByTestId("condition-status")).toHaveTextContent("Not yet");
    }
    expect(screen.getByTestId("ordering-note")).toHaveTextContent(
      "Set the election schedule before, or together with, the last of the other changes.",
    );
    expect(container).toHaveTextContent("Meeting every condition is not victory: you must then win the election.");
    expect(container.textContent).not.toMatch(/the reform that completes them is the one that counts/);

    fireEvent.click(within(rows[1]!).getByRole("button", { name: "Draft this change on its own: No decree authority" }));
    expect(useDraftStore.getState().requestedCardId).toBe("constitution_decree_authority_to_none");
    expect(navigate).toHaveBeenLastCalledWith("decisions");

    fireEvent.click(screen.getByRole("button", { name: "Draft the qualifying reform" }));
    expect(useDraftStore.getState().requestedCardId).toBe(QUALIFYING_REFORM_CARD_ID);
    await axeClean(container, "Constitution (reform)");
  });

  it("withholds a link that would strand the constitution, saying why", async () => {
    currentDashboard = dashboard(OBJECTIVE_STAGES.afterDecreeNone);
    const { container } = withCampaign(<ConstitutionScreen navigate={vi.fn()} />);
    const list = await screen.findByTestId("constitution-checklist");
    const executive = within(list).getAllByRole("listitem").find((row) => row.getAttribute("data-condition") === "elected_executive")!;
    expect(within(executive).queryByRole("button")).toBeNull();
    expect(within(executive).getByTestId("condition-note")).toHaveTextContent(/^Not on its own:/);
    const interval = within(list).getAllByRole("listitem").find((row) => row.getAttribute("data-condition") === "election_interval")!;
    expect(within(interval).getByRole("button")).toHaveAccessibleName("Draft this change on its own: A national election schedule");
    await axeClean(container, "Constitution (after decree none)");
  });

  it.each(["cannotQualifyMissingInterval", "cannotQualifyAlreadyCompetitive", "qualifyingElection", "concludedVictory"] as const)(
    "%s: no reform link is offered",
    async (stage) => {
      currentDashboard = dashboard(OBJECTIVE_STAGES[stage]);
      const { container } = withCampaign(<ConstitutionScreen navigate={vi.fn()} />);
      const list = await screen.findByTestId("constitution-checklist");
      expect(within(list).queryAllByRole("button")).toEqual([]);
      expect(screen.queryByTestId("draft-qualifying-reform")).toBeNull();
      expect(screen.getByTestId("objective-headline")).toHaveTextContent(OBJECTIVE_STAGES[stage].headline);
      await axeClean(container, `Constitution (${stage})`);
    },
  );

  it("says why a linked card is unavailable, using the card's own reason", async () => {
    currentOptions = {
      ...OPTIONS,
      policy_cards: OPTIONS.policy_cards.map((card) =>
        card.card_id === QUALIFYING_REFORM_CARD_ID
          ? { ...card, available: false, unavailable_reason: "game_concluded", unavailable_detail: "Not today.", routes: [] }
          : card,
      ),
    } as DecisionOptionsProjection;
    withCampaign(<ConstitutionScreen navigate={vi.fn()} />);
    expect(await screen.findByTestId("qualifying-unavailable")).toHaveTextContent(
      "The qualifying reform can't be drafted now: Not today.",
    );
    expect(screen.queryByTestId("draft-qualifying-reform")).toBeNull();
  });
});

describe("a link selects its card in Decisions, REPLACING the drafted proposal", () => {
  const qualifying = OPTIONS.policy_cards.find((card) => card.card_id === QUALIFYING_REFORM_CARD_ID)!;
  const legislativeTemplate = qualifying.routes.find((route) => route.route === "legislative")!.template!;

  it("replaces a staged budget, says so, and focuses the selection", async () => {
    const budget = OPTIONS.policy_cards.find((card) => card.category === "taxation" && card.available)!;
    useDraftStore.getState().applyCard({
      policySlot: "budget",
      budget: { spendingUpdates: {}, route: "legislative", personalIncomeRateBps: 1500 },
    });
    expect(budget).toBeDefined();
    useDraftStore.getState().requestCard(QUALIFYING_REFORM_CARD_ID);
    withCampaign(<DecisionsScreen navigate={vi.fn()} />);
    await waitFor(() => expect(useDraftStore.getState().requestedCardId).toBeNull());
    const draft = useDraftStore.getState();
    expect(draft.policySlot).toBe("amendment");
    expect(draft.budget.personalIncomeRateBps).toBeUndefined();
    expect(draft.amendment.targets).toEqual(
      Object.fromEntries(
        (legislativeTemplate as { targets: { axis: string; value: unknown }[] }).targets.map((t) => [t.axis, t.value]),
      ),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Replaced your drafted budget with: Complete the constitutional conditions in one reform.",
    );
    await waitFor(() => expect(document.activeElement?.id).toBe("policy-selection-summary"));
    expect(screen.getByTestId("policy-selection-summary")).toHaveTextContent(qualifying.title);
  });

  it("does not merge into a staged amendment: other axes are dropped, and the player is told", async () => {
    useDraftStore.getState().applyCard({
      policySlot: "amendment",
      amendment: { targets: { executive_term_limit_terms: 2 }, route: "legislative" },
    });
    useDraftStore.getState().setAmendmentInfluence("opposition_party", "main", 100);
    useDraftStore.getState().requestCard("constitution_decree_authority_to_none");
    withCampaign(<DecisionsScreen navigate={vi.fn()} />);
    await waitFor(() => expect(useDraftStore.getState().requestedCardId).toBeNull());
    const draft = useDraftStore.getState();
    expect(draft.amendment.targets).toEqual({ decree_authority: "none" });
    expect(draft.amendment.influence).toEqual({});
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Replaced your drafted amendment with: Set decree authority to no decree authority.",
    );
  });

  it("announces nothing extra when nothing was drafted", async () => {
    useDraftStore.getState().requestCard(QUALIFYING_REFORM_CARD_ID);
    withCampaign(<DecisionsScreen navigate={vi.fn()} />);
    await waitFor(() => expect(useDraftStore.getState().requestedCardId).toBeNull());
    expect(useDraftStore.getState().policySlot).toBe("amendment");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("stages nothing for an unavailable card, and says why", async () => {
    useDraftStore.getState().requestCard("constitution_no_such_card");
    withCampaign(<DecisionsScreen navigate={vi.fn()} />);
    await waitFor(() => expect(useDraftStore.getState().requestedCardId).toBeNull());
    expect(useDraftStore.getState().policySlot).toBeNull();
    expect(await screen.findByRole("alert")).toHaveTextContent("That reform can't be drafted now.");
  });
});

describe("the preview's sentence and the result's line", () => {
  it.each([
    ["previewPasses", null],
    ["previewFails", "This amendment would not pass as it stands, so it would not change the constitution."],
    ["previewUnaffordable", "This draft is not affordable, so resolving it would be refused."],
  ] as const)("%s: says what enactment would do, and when resolving would not enact it", (name, caveat) => {
    render(<ConsequencesPanel preview={results[name] as unknown as PreviewProjection} />);
    expect(screen.getByTestId("objective-effect").textContent).toMatch(/^If enacted, /);
    if (caveat === null) expect(screen.queryByTestId("objective-effect-caveat")).toBeNull();
    else expect(screen.getByTestId("objective-effect-caveat")).toHaveTextContent(caveat);
  });

  it("shows no objective sentence for a draft without an amendment", () => {
    render(<ConsequencesPanel preview={{ ...results.previewPasses, objective_effect_if_enacted: null } as unknown as PreviewProjection} />);
    expect(screen.queryByTestId("objective-effect")).toBeNull();
  });

  it.each(["live", "history"] as const)("%s: the objective line sits under the headline, and named amendment lines replace the generic one", (context) => {
    const result = results.reformResult as unknown as TurnResultProjection;
    render(<TurnResultView result={result} context={context} />);
    expect(screen.getByTestId("objective-line")).toHaveTextContent(
      "The constitution now qualifies, and the transition is recorded. Win the election on turn 5 to complete it.",
    );
    expect(screen.getByText("Decree authority: unlimited → none.")).toBeInTheDocument();
    expect(screen.getByText("Election schedule: none → every 4 turns.")).toBeInTheDocument();
    expect(screen.queryByText("The constitution was amended.")).toBeNull();
  });

  it("renders no objective line when the server sends none", () => {
    render(<TurnResultView result={{ ...(results.reformResult as unknown as TurnResultProjection), objective_line: null }} context="live" />);
    expect(screen.queryByTestId("objective-line")).toBeNull();
  });
});
