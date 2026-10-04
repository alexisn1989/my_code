/**
 * Gate 4A3 UX-4b (U8): the nav count, "This turn's draft" and the resolve confirmation state the
 * SAME number, which is the number of player actions that will be submitted.
 *
 * Each case also pins that number against `stagedActions` and against what `buildDecisions` sends,
 * so the three surfaces cannot agree on a phantom.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { buildDecisions } from "../state/buildDecisionSet";
import { useDraftStore } from "../state/draft";
import { SessionProvider, useSession } from "../state/SessionContext";
import { stagedActions } from "../state/stagedActions";
import { GreyboxApp } from "./GreyboxApp";
import { DecisionsScreen } from "./screens/DecisionsScreen";

const candidate = (character_id: string, display_name: string, requires_vacating_post: string | null) => ({
  character_id,
  display_name,
  requires_vacating_post,
  currently_holds_post: requires_vacating_post,
  candidate_accepts_post: true,
  appointment_cost: 20,
  competence_bps: 5000,
  loyalty_bps: 5000,
  independence_bps: 5000,
  ambition_bps: 5000,
  personal_trust_bps: 5000,
  verb: "appoint",
  refusal_code: null,
});

const OPTIONS = {
  revision: "rev-1",
  chambers: [],
  constitutional_axes: [],
  policy_cards: [],
  spending_categories: [],
  decree_available: false,
  decree_amendment_capital_cost: 400,
  decree_legislative_capital_cost: 250,
  opening_capital: 500,
  relationship_investment_maximum: 300,
  relationship_investment_minimum: 0,
  tax_rate_bps_maximum: 5000,
  tax_rate_bps_minimum: 0,
  blocs: [
    { party_id: "governing_party", bloc_id: "core", bloc_name: "Crown Loyalists", party_name: "Crown", chamber: "lower", seats: 40 },
    { party_id: "opposition_party", bloc_id: "main", bloc_name: "Reform Bloc", party_name: "Reform", chamber: "lower", seats: 30 },
  ],
  cabinet_posts: [
    {
      post: "chief_of_staff",
      post_display_name: "Chief of Staff",
      can_dismiss: true,
      holder_character_id: "char_a",
      holder_display_name: "Ada Vale",
      candidates: [candidate("char_b", "Bela Ronsard", "foreign_minister")],
    },
    {
      post: "foreign_minister",
      post_display_name: "Foreign Minister",
      can_dismiss: true,
      holder_character_id: "char_b",
      holder_display_name: "Bela Ronsard",
      candidates: [],
    },
  ],
  legislative_bargain_counterparties: [],
  foreign_assistance_counterparties: [],
  promise_options: [],
  active_promises: [],
};

const DASHBOARD = { revision: "rev-1", campaign_id: "campaign-1", turn: 4, terminal: null };

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  useDraftStore.getState().clearDraft();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/decision-options")) return json(OPTIONS);
      if (url.includes("/api/game/state")) return json(DASHBOARD);
      return json([]);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  useDraftStore.getState().clearDraft();
});

function SetRevision({ children }: { children: ReactNode }) {
  const { setCampaignView, revision } = useSession();
  useEffect(() => {
    if (revision === null) setCampaignView("rev-1", "campaign-1");
  }, [revision, setCampaignView]);
  return revision === null ? null : <>{children}</>;
}

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

/** The nav's count, read from the real shell. `null` when no count is shown. */
function navCount(): string | null {
  const { unmount } = render(
    <QueryClientProvider client={client()}>
      <GreyboxApp />
    </QueryClientProvider>,
  );
  const nav = screen.getByRole("navigation", { name: "Screens" });
  const decisions = within(nav).getByRole("button", { name: "Decisions" });
  const badge = within(nav).queryByTestId("staged-count");
  if (badge !== null) {
    expect(decisions).toHaveAttribute("aria-describedby", badge.id);
    expect(decisions).toHaveAccessibleName("Decisions");
  }
  const text = badge?.textContent ?? null;
  unmount();
  return text;
}

/** The draft list and the confirmation, read from the real Decisions screen. */
async function decisionsSurfaces(): Promise<{ listed: number; empty: boolean; confirm: string }> {
  const { unmount } = render(
    <QueryClientProvider client={client()}>
      <SessionProvider>
        <SetRevision>
          <DecisionsScreen navigate={vi.fn()} />
        </SetRevision>
      </SessionProvider>
    </QueryClientProvider>,
  );
  const panel = (await screen.findByRole("heading", { name: "This turn's draft" })).closest("section") as HTMLElement;
  const list = within(panel).queryByTestId("staged-actions");
  const listed = list === null ? 0 : list.querySelectorAll(":scope > li").length;
  const empty = within(panel).queryByText("Nothing is staged yet.") !== null;
  fireEvent.click(screen.getByRole("button", { name: "Resolve turn" }));
  const confirm = (await screen.findByText(/^Resolve turn 4 with/)).textContent ?? "";
  unmount();
  return { listed, empty, confirm };
}

describe("the three surfaces agree, on what is submitted", () => {
  it("a transfer plus two investments is 3 everywhere, against 2 wire decisions", async () => {
    const draft = useDraftStore.getState();
    draft.confirmAppointment("chief_of_staff", "char_b", "foreign_minister");
    draft.setInvestment("governing_party", "core", 20);
    draft.setInvestment("opposition_party", "main", 30);

    expect(stagedActions(useDraftStore.getState())).toHaveLength(3);
    expect(buildDecisions(useDraftStore.getState())).toHaveLength(2);
    expect(navCount()).toBe("· 3 staged");
    const surfaces = await decisionsSurfaces();
    expect(surfaces.listed).toBe(3);
    expect(surfaces.confirm).toBe("Resolve turn 4 with 3 staged actions?");
  });

  it("lists each action in its staging screen's words, with the transfer's consequence", async () => {
    const draft = useDraftStore.getState();
    draft.confirmAppointment("chief_of_staff", "char_b", "foreign_minister");
    draft.setInvestment("opposition_party", "main", 30);
    render(
      <QueryClientProvider client={client()}>
        <SessionProvider>
          <SetRevision>
            <DecisionsScreen navigate={vi.fn()} />
          </SetRevision>
        </SessionProvider>
      </QueryClientProvider>,
    );
    const list = await screen.findByTestId("staged-actions");
    const items = Array.from(list.querySelectorAll(":scope > li")).map((li) => li.textContent);
    expect(items).toEqual([
      "Bela Ronsard becomes Chief of Staff.As a result: Foreign Minister is left vacant.",
      "30 political capital invested in Reform Bloc.",
    ]);
  });

  it.each([
    ["an empty budget slot", () => useDraftStore.getState().setPolicySlot("budget")],
    ["an empty amendment slot", () => useDraftStore.getState().setPolicySlot("amendment")],
    [
      "influence on a target-less budget",
      () => {
        useDraftStore.getState().setPolicySlot("budget");
        useDraftStore.getState().setBudgetInfluence("governing_party", "core", 40);
      },
    ],
    [
      "influence on a target-less amendment",
      () => {
        useDraftStore.getState().setPolicySlot("amendment");
        useDraftStore.getState().setAmendmentInfluence("governing_party", "core", 40);
      },
    ],
    ["no major action", () => useDraftStore.getState().setPolicySlot(null)],
  ])("%s is 0 everywhere, and nothing is submitted", async (_name, stage) => {
    stage();
    expect(stagedActions(useDraftStore.getState())).toEqual([]);
    expect(buildDecisions(useDraftStore.getState())).toEqual([]);
    expect(navCount()).toBeNull();
    const surfaces = await decisionsSurfaces();
    expect(surfaces.listed).toBe(0);
    expect(surfaces.empty).toBe(true);
    expect(surfaces.confirm).toBe("Resolve turn 4 with nothing staged?");
  });

  it("one action is singular", async () => {
    useDraftStore.getState().setInvestment("governing_party", "core", 20);
    expect(navCount()).toBe("· 1 staged");
    expect((await decisionsSurfaces()).confirm).toBe("Resolve turn 4 with 1 staged action?");
  });
});
