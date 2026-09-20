/**
 * The meeting panel: staging three negotiations, and the boundaries it must not cross.
 *
 * Drives the real screen against a mocked `/api/game/decision-options`, so what is proven is the
 * component's behaviour against the real projection shape — never a mock of the component.
 *
 * The fixture is shipped content: `deficit_demo`'s Sofia Renn (who deals, at 113) and Petra Almas
 * (who will not), `tiny_valid`'s Kessia and Vetruska, and one promise option per term. Real rows
 * matter here because three of the claims below — that a refusal carries no price, that a decree
 * blocks confirmation, and that no question contains a figure — are about what a player sees when
 * the server says no, and inventing a friendlier row would prove nothing.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MeetingScreen } from "./MeetingScreen";
import { SessionProvider, useSession } from "../../state/SessionContext";
import { buildDecisions } from "../../state/buildDecisionSet";
import { useDraftStore } from "../../state/draft";

const SOFIA = {
  character_id: "leader_independents",
  display_name: "Sofia Renn",
  portrait_ref: "renn_sofia",
  party_id: "independents",
  party_display_name: "Independents",
  loyalty_bps: 4600,
  independence_bps: 7400,
  ambition_bps: 3900,
  personal_trust_bps: 5400,
  will_deal: true,
  asking_price: 113,
  refusal_reason: null,
};

const PETRA = {
  character_id: "leader_citizens_bloc",
  display_name: "Petra Almas",
  portrait_ref: "almas_petra",
  party_id: "citizens_bloc",
  party_display_name: "Citizens Bloc",
  loyalty_bps: 1500,
  independence_bps: 7900,
  ambition_bps: 8000,
  personal_trust_bps: 2600,
  will_deal: false,
  asking_price: null,
  refusal_reason: "refused_will_not_deal",
};

const KESSIA = {
  profile_id: "kessia",
  display_name: "Kessia",
  counterpart_character_id: "leader_kessia",
  counterpart_display_name: "Dietrich Halm",
  counterpart_portrait_ref: "halm_dietrich",
  standing_bps: 2000,
  remaining_capacity: 250_000_000,
  will_assist: true,
  estimated_grant: 38_150_000,
  refusal_reason: null,
};

const VETRUSKA = {
  profile_id: "vetruska",
  display_name: "Vetruska",
  counterpart_character_id: "leader_vetruska",
  counterpart_display_name: "Sanna Ilves",
  counterpart_portrait_ref: "ilves_sanna",
  standing_bps: -5000,
  remaining_capacity: 120_000_000,
  will_assist: false,
  estimated_grant: null,
  refusal_reason: "foreign_assistance_counterpart_is_hostile",
};

const TENURE_OPTION = {
  character_id: "hal_verrin",
  character_display_name: "Hal Verrin",
  character_portrait_ref: "verrin_hal",
  term_kind: "cabinet_tenure" as const,
  subject_id: "chief_of_staff",
  subject_display_name: "chief of staff",
  earliest_legal_deadline: 7,
};

const SUPPORT_OPTION = {
  character_id: "leader_independents",
  character_display_name: "Sofia Renn",
  character_portrait_ref: "renn_sofia",
  term_kind: "legislative_support" as const,
  subject_id: "budget",
  subject_display_name: "the budget",
  earliest_legal_deadline: 7,
};

const ACTIVE_RELEASABLE = {
  promise_id: "pr_aaa",
  character_id: "leader_citizens_bloc",
  character_display_name: "Petra Almas",
  character_portrait_ref: "almas_petra",
  term_kind: "legislative_support" as const,
  subject_id: "budget",
  subject_display_name: "the budget",
  status: "pending" as const,
  made_turn: 1,
  deadline_turn: 9,
  released_turn: null,
  releasable: true,
  release_blocked_reason: null,
};

const ACTIVE_BLOCKED = {
  ...ACTIVE_RELEASABLE,
  promise_id: "pr_bbb",
  character_id: "leader_kessia",
  character_display_name: "Dietrich Halm",
  character_portrait_ref: "halm_dietrich",
  term_kind: "assistance_restraint" as const,
  subject_id: "kessia",
  subject_display_name: "Kessia",
  status: "cancelled" as const,
  released_turn: 2,
  releasable: false,
  release_blocked_reason: "promise_already_released" as const,
};

const DECISION_OPTIONS = {
  revision: "rev-1",
  campaign_id: "campaign-1",
  blocs: [],
  chambers: [],
  constitutional_axes: [],
  cabinet_posts: [],
  legislative_bargain_counterparties: [PETRA, SOFIA],
  foreign_assistance_counterparties: [KESSIA, VETRUSKA],
  promise_options: [TENURE_OPTION, SUPPORT_OPTION],
  active_promises: [ACTIVE_RELEASABLE, ACTIVE_BLOCKED],
  decree_amendment_capital_cost: 400,
  decree_available: true,
  policy_cards: [],
  decree_legislative_capital_cost: 250,
  opening_capital: 500,
  relationship_investment_maximum: 200,
  relationship_investment_minimum: 1,
  spending_categories: [],
  tax_rate_bps_maximum: 5000,
  tax_rate_bps_minimum: 0,
};

function SetRevision({ children }: { children: ReactNode }) {
  const { setCampaignView, revision } = useSession();
  useEffect(() => {
    if (revision === null) {
      setCampaignView("rev-1", "campaign-1");
    }
  }, [revision, setCampaignView]);
  return revision === null ? null : <>{children}</>;
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <SetRevision>
          <MeetingScreen navigate={() => {}} />
        </SetRevision>
      </SessionProvider>
    </QueryClientProvider>,
  );
}

function bySelector(selector: string): HTMLElement {
  const node = document.querySelector(selector);
  if (node === null) {
    throw new Error(`no node for ${selector}`);
  }
  return node as HTMLElement;
}

/** Waits for the projection to land. Deliberately NOT a text query: several people appear in more
 * than one section — Sofia Renn is both a leader and a promise counterparty, which is exactly the
 * point of the screen — so a name is not a unique anchor here. */
async function ready(): Promise<HTMLElement> {
  return screen.findByTestId("meeting-panel");
}

function panelState(): string | null {
  return screen.getByTestId("meeting-panel").getAttribute("data-meeting-state");
}

/** A legislative-route budget in the draft, which is what makes a bargain stageable at all. */
function stageLegislativeBudget(): void {
  useDraftStore.getState().setPolicySlot("budget");
  useDraftStore.getState().setBudgetRoute("legislative");
}

beforeEach(() => {
  useDraftStore.getState().clearDraft();
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async () =>
      new Response(JSON.stringify(DECISION_OPTIONS), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
  useDraftStore.getState().clearDraft();
});

describe("MeetingScreen: rendering", () => {
  it("shows every counterparty with a portrait, and no raw identifier anywhere", async () => {
    renderScreen();
    await ready();
    // Sofia appears TWICE on purpose — as a leader to bargain with and as somebody to promise —
    // which is why these are `getAllByText`. Dietrich likewise, as a counterpart and as an
    // outstanding promise.
    expect(screen.getAllByText(/Sofia Renn/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Dietrich Halm/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Hal Verrin/)).toBeInTheDocument();

    // One portrait per person on screen, each named by its DISPLAY name, never by its reference.
    const portraits = document.querySelectorAll("svg[role='img']");
    expect(portraits.length).toBeGreaterThan(0);
    for (const portrait of portraits) {
      const label = portrait.getAttribute("aria-label") ?? "";
      expect(label).not.toContain("_");
      expect(label).not.toBe("portrait");
    }

    const text = document.body.textContent ?? "";
    for (const raw of [
      "leader_independents",
      "leader_citizens_bloc",
      "hal_verrin",
      "chief_of_staff",
      "renn_sofia",
      "almas_petra",
      "pr_aaa",
      "legislative_support",
      "refused_will_not_deal",
      "promise_already_released",
    ]) {
      expect(text).not.toContain(raw);
    }
  });

  it("prices a willing leader and prices a refusing one at nothing at all", async () => {
    renderScreen();
    await ready();
    expect(bySelector("[data-leader-price='leader_independents']").textContent).toContain("113");
    expect(document.querySelector("[data-leader-price='leader_citizens_bloc']")).toBeNull();
    expect(bySelector("[data-leader-refusal='leader_citizens_bloc']").textContent).toContain(
      "Will not deal",
    );
  });

  it("asks every counterparty a question, and no question carries a figure", async () => {
    renderScreen();
    await ready();
    const questions = document.querySelectorAll(
      "[data-leader-question], [data-counterpart-question], [data-promise-question], [data-active-promise-question]",
    );
    // Two leaders, two counterparts, two promise options, two outstanding promises.
    expect(questions.length).toBe(8);
    for (const question of questions) {
      // NO DIGITS. R8 removed counteroffers and price bands; a question naming a number would put
      // the deleted mechanic back through prose. The price is still on screen, in its own element
      // (asserted above), so this cannot be satisfied by hiding the figure instead.
      expect(question.textContent ?? "").not.toMatch(/[0-9]/);
    }
  });

  it("states why a release is blocked, in words rather than a code", async () => {
    renderScreen();
    await ready();
    expect(bySelector("[data-release-blocked='pr_bbb']").textContent).toContain("Already released");
    expect(document.querySelector("[data-release-blocked='pr_aaa']")).toBeNull();
  });
});

describe("MeetingScreen: the state machine", () => {
  it("walks idle -> counterpartySelected -> idle, and Escape unwinds", async () => {
    stageLegislativeBudget();
    renderScreen();
    await ready();
    expect(panelState()).toBe("idle");

    fireEvent.click(bySelector("[data-leader-option='leader_independents']"));
    expect(panelState()).toBe("counterpartySelected");

    fireEvent.keyDown(screen.getByTestId("meeting-panel"), { key: "Escape" });
    expect(panelState()).toBe("idle");
  });

  it("writes nothing to the shared draft until Confirm", async () => {
    stageLegislativeBudget();
    renderScreen();
    await ready();

    fireEvent.click(bySelector("[data-leader-option='leader_independents']"));
    expect(useDraftStore.getState().bargain).toBeNull();

    fireEvent.click(screen.getByTestId("cancel-meeting"));
    expect(useDraftStore.getState().bargain).toBeNull();

    fireEvent.click(bySelector("[data-leader-option='leader_independents']"));
    fireEvent.click(screen.getByTestId("confirm-meeting"));
    expect(useDraftStore.getState().bargain).toEqual({
      characterId: "leader_independents",
      proposalKind: "budget",
    });
  });
});

describe("MeetingScreen: the bargain's coupling to the policy slot", () => {
  it("refuses to stage a bargain when the draft carries no proposal, and says why", async () => {
    renderScreen();
    await ready();
    expect(screen.getByTestId("bargain-blocked").textContent).toContain(
      "Put a budget or an amendment",
    );

    fireEvent.click(bySelector("[data-leader-option='leader_independents']"));
    expect(screen.getByTestId("confirm-meeting")).toBeDisabled();
    expect(useDraftStore.getState().bargain).toBeNull();
  });

  it("refuses to stage a bargain over a DECREE, with accessible copy, and stays server-authoritative", async () => {
    useDraftStore.getState().setPolicySlot("budget");
    useDraftStore.getState().setBudgetRoute("decree");
    renderScreen();
    await ready();

    // The visible explanation is a real sentence naming the route, not a dead control.
    const blocked = screen.getByTestId("bargain-blocked").textContent ?? "";
    expect(blocked).toContain("decreed");
    expect(blocked).not.toContain("legislative_bargain_requires_legislative_route");

    fireEvent.click(bySelector("[data-leader-option='leader_independents']"));
    expect(screen.getByTestId("review-bargain-blocked")).toBeInTheDocument();
    expect(screen.getByTestId("confirm-meeting")).toBeDisabled();

    // And the screen stages NOTHING: the server refuses this set outright, so there is no
    // frontend-only legality here — the client simply declines to compose a draft it was told
    // cannot resolve.
    fireEvent.click(screen.getByTestId("confirm-meeting"));
    expect(useDraftStore.getState().bargain).toBeNull();
  });

  it("derives proposal_kind from the slot rather than offering a choice", async () => {
    useDraftStore.getState().setPolicySlot("amendment");
    useDraftStore.getState().setAmendmentRoute("legislative");
    renderScreen();
    await ready();

    fireEvent.click(bySelector("[data-leader-option='leader_independents']"));
    fireEvent.click(screen.getByTestId("confirm-meeting"));
    expect(useDraftStore.getState().bargain).toEqual({
      characterId: "leader_independents",
      proposalKind: "amendment",
    });
    expect(buildDecisions(useDraftStore.getState())).toContainEqual(
      expect.objectContaining({
        kind: "legislative_bargain",
        proposal_kind: "constitutional_amendment",
      }),
    );
  });

  it("clears a staged bargain when the slot moves out from under it", async () => {
    stageLegislativeBudget();
    renderScreen();
    await ready();
    fireEvent.click(bySelector("[data-leader-option='leader_independents']"));
    fireEvent.click(screen.getByTestId("confirm-meeting"));
    expect(useDraftStore.getState().bargain).not.toBeNull();

    useDraftStore.getState().setPolicySlot(null);
    expect(useDraftStore.getState().bargain).toBeNull();
  });
});

describe("MeetingScreen: assistance and promises", () => {
  it("stages an assistance request, and emits it in canonical order", async () => {
    renderScreen();
    await ready();
    fireEvent.click(bySelector("[data-counterpart-option='kessia']"));
    fireEvent.click(screen.getByTestId("confirm-meeting"));
    expect(useDraftStore.getState().assistance).toEqual({ profileId: "kessia" });
    expect(buildDecisions(useDraftStore.getState())).toEqual([
      { kind: "foreign_assistance", profile_id: "kessia" },
    ]);
  });

  it("stages a promise at the server's earliest legal deadline, never a computed one", async () => {
    renderScreen();
    await ready();
    fireEvent.click(bySelector("[data-promise-option='hal_verrin/cabinet_tenure/chief_of_staff']"));
    fireEvent.click(screen.getByTestId("confirm-meeting"));
    expect(useDraftStore.getState().promise).toEqual({
      action: "make",
      characterId: "hal_verrin",
      termKind: "cabinet_tenure",
      subjectId: "chief_of_staff",
      // 7 is `earliest_legal_deadline` as projected. The client never computes `turn + 4`.
      deadlineTurn: 7,
    });
  });

  it("stages a release of a releasable promise and refuses a blocked one", async () => {
    renderScreen();
    await ready();

    fireEvent.click(bySelector("[data-active-promise='pr_aaa']"));
    expect(screen.getByTestId("confirm-meeting")).not.toBeDisabled();
    fireEvent.click(screen.getByTestId("confirm-meeting"));
    expect(useDraftStore.getState().promise).toEqual({
      action: "release",
      characterId: "leader_citizens_bloc",
      promiseId: "pr_aaa",
    });

    useDraftStore.getState().clearPromise();
    fireEvent.click(bySelector("[data-active-promise='pr_bbb']"));
    expect(screen.getByTestId("confirm-meeting")).toBeDisabled();
    fireEvent.click(screen.getByTestId("confirm-meeting"));
    expect(useDraftStore.getState().promise).toBeNull();
  });

  it("the review of a release quotes no capital figure", async () => {
    renderScreen();
    await ready();
    fireEvent.click(bySelector("[data-active-promise='pr_aaa']"));
    const lines = screen.getByTestId("meeting-review-lines").textContent ?? "";
    expect(lines).toContain("costs political capital");
    // The price is a server constant; a second copy of it here would be the duplication the
    // no-duplication contract forbids. `/preview` names the charge on the Decisions screen.
    expect(lines).not.toContain("250");
  });
});

describe("MeetingScreen: the staged summary and the draft lifecycle", () => {
  it("names each staged approach and removes it on request", async () => {
    stageLegislativeBudget();
    renderScreen();
    await ready();

    fireEvent.click(bySelector("[data-leader-option='leader_independents']"));
    fireEvent.click(screen.getByTestId("confirm-meeting"));
    const summary = screen.getByTestId("staged-meeting-summary");
    expect(summary.textContent).toContain("Sofia Renn");
    expect(summary.textContent).toContain("the budget");

    fireEvent.click(screen.getByTestId("remove-bargain"));
    expect(useDraftStore.getState().bargain).toBeNull();
    expect(screen.queryByTestId("staged-meeting-summary")).toBeNull();
  });

  it("clearDraft removes all three, as a resolve or a new campaign does", async () => {
    stageLegislativeBudget();
    renderScreen();
    await ready();
    fireEvent.click(bySelector("[data-leader-option='leader_independents']"));
    fireEvent.click(screen.getByTestId("confirm-meeting"));
    fireEvent.click(bySelector("[data-counterpart-option='kessia']"));
    fireEvent.click(screen.getByTestId("confirm-meeting"));

    useDraftStore.getState().clearDraft();
    const state = useDraftStore.getState();
    expect(state.bargain).toBeNull();
    expect(state.assistance).toBeNull();
    expect(state.promise).toBeNull();
  });
});

describe("MeetingScreen: accessibility and resilience", () => {
  it("every control is a native button and there is exactly one live region", async () => {
    renderScreen();
    await ready();
    const interactive = document.querySelectorAll("[data-leader-option], [data-promise-option]");
    for (const node of interactive) {
      expect(node.tagName).toBe("BUTTON");
    }
    expect(document.querySelectorAll("[aria-live='polite']").length).toBe(1);
  });

  it("announces a staged approach without claiming anything has happened", async () => {
    stageLegislativeBudget();
    renderScreen();
    await ready();
    fireEvent.click(bySelector("[data-leader-option='leader_independents']"));
    fireEvent.click(screen.getByTestId("confirm-meeting"));
    const live = bySelector("[aria-live='polite']").textContent ?? "";
    expect(live).toContain("Sofia Renn");
    expect(live).toContain("Nothing has been agreed yet");
  });

  it("says so plainly when there is no campaign", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SessionProvider>
          <MeetingScreen navigate={() => {}} />
        </SessionProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Start or load a campaign/)).toBeInTheDocument();
  });

  it("surfaces a failed projection rather than rendering an empty room", async () => {
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("", { status: 500 }));
    renderScreen();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
