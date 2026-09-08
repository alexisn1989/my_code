/**
 * The cabinet screen: staging, the transfer's two orders, and the boundaries it must not cross.
 *
 * Drives the real screen against a mocked `/api/game/decision-options`, so what is proven is the
 * component's behaviour against the real projection shape -- not a mock of the component.
 *
 * The fixture is `tiny_valid`'s actual cabinet, because it is the only shipped scenario that
 * reaches every case at once: both posts held, a transfer candidate (Ilse, who holds the ministry),
 * an incumbent, and a candidate who refuses one post and not the other.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CabinetScreen } from "./CabinetScreen";
import { SessionProvider, useSession } from "../../state/SessionContext";
import { buildDecisions } from "../../state/buildDecisionSet";
import { useDraftStore } from "../../state/draft";

function candidate(
  characterId: string,
  displayName: string,
  cost: number,
  overrides: Record<string, unknown> = {},
) {
  return {
    character_id: characterId,
    display_name: displayName,
    competence_bps: 5000,
    loyalty_bps: 5000,
    independence_bps: 5000,
    ambition_bps: 5000,
    personal_trust_bps: 5000,
    appointment_cost: cost,
    verb: "replace",
    candidate_accepts_post: true,
    refusal_code: null,
    currently_holds_post: null,
    requires_vacating_post: null,
    ...overrides,
  };
}

const HAL = () => candidate("hal_verrin", "Hal Verrin", 147);
const ILSE = () => candidate("ilse_marovec", "Ilse Marovec", 276);
const TOMAS = () => candidate("tomas_bekker", "Tomas Bekker", 231);
const WREN = () => candidate("wren_hollis", "Wren Hollis", 197);

const CABINET_POSTS = [
  {
    post: "chief_of_staff",
    post_display_name: "chief of staff",
    holder_character_id: "hal_verrin",
    holder_display_name: "Hal Verrin",
    holder_competence_bps: 3200,
    can_dismiss: true,
    candidates: [
      { ...HAL(), currently_holds_post: "chief_of_staff" },
      { ...ILSE(), currently_holds_post: "foreign_minister", requires_vacating_post: "foreign_minister" },
      TOMAS(),
      WREN(),
    ],
  },
  {
    post: "foreign_minister",
    post_display_name: "foreign minister",
    holder_character_id: "ilse_marovec",
    holder_display_name: "Ilse Marovec",
    holder_competence_bps: 8600,
    can_dismiss: true,
    candidates: [
      { ...HAL(), currently_holds_post: "chief_of_staff", requires_vacating_post: "chief_of_staff" },
      { ...ILSE(), currently_holds_post: "foreign_minister" },
      {
        ...TOMAS(),
        candidate_accepts_post: false,
        refusal_code: "cabinet_candidate_refuses_this_post",
      },
      WREN(),
    ],
  },
];

const DECISION_OPTIONS = {
  revision: "rev-1",
  campaign_id: "campaign-1",
  blocs: [],
  chambers: [],
  constitutional_axes: [],
  cabinet_posts: CABINET_POSTS,
  decree_amendment_capital_cost: 400,
  decree_available: false,
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
          <CabinetScreen navigate={() => {}} />
        </SetRevision>
      </SessionProvider>
    </QueryClientProvider>,
  );
}

/** A stable serialization of the shared store, for "byte-identical" claims. */
function storeSnapshot(): string {
  const orders = useDraftStore.getState().cabinetOrders;
  return JSON.stringify(
    Object.keys(orders)
      .sort((a, b) => a.localeCompare(b))
      .map((post) => [post, orders[post]]),
  );
}

function selectPostButton(post: string): HTMLElement {
  const node = document.querySelector(`[data-post-option="${post}"]`);
  if (node === null) {
    throw new Error(`no post control for ${post}`);
  }
  return node as HTMLElement;
}

function candidateButton(characterId: string): HTMLElement {
  const node = document.querySelector(`[data-candidate-option="${characterId}"]`);
  if (node === null) {
    throw new Error(`no candidate control for ${characterId}`);
  }
  return node as HTMLElement;
}

function panelState(): string | null {
  return screen.getByTestId("cabinet-panel").getAttribute("data-cabinet-state");
}

beforeEach(() => {
  useDraftStore.getState().clearDraft();
  vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
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

describe("CabinetScreen: rendering", () => {
  it("names both posts and their holders, with no raw identifier anywhere", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    expect(screen.getByText("foreign minister")).toBeInTheDocument();
    expect(screen.getByText("Held by Hal Verrin")).toBeInTheDocument();

    const body = document.body.textContent ?? "";
    for (const rawId of ["chief_of_staff", "foreign_minister", "hal_verrin", "ilse_marovec"]) {
      expect(body).not.toContain(rawId);
    }
  });

  it("says plainly that the rest of the government is still unavailable", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    expect(screen.getByText(/not available in this gate/i)).toBeInTheDocument();
  });
});

describe("CabinetScreen: the state machine", () => {
  it("walks idle -> postSelected -> candidateSelected and back out with Escape", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    expect(panelState()).toBe("idle");

    fireEvent.click(selectPostButton("chief_of_staff"));
    expect(panelState()).toBe("postSelected");

    fireEvent.click(candidateButton("wren_hollis"));
    expect(panelState()).toBe("candidateSelected");

    fireEvent.keyDown(screen.getByTestId("cabinet-panel"), { key: "Escape" });
    expect(panelState()).toBe("postSelected");

    fireEvent.keyDown(screen.getByTestId("cabinet-panel"), { key: "Escape" });
    expect(panelState()).toBe("idle");
  });

  it("Cancel does exactly what Escape does", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    fireEvent.click(selectPostButton("chief_of_staff"));
    fireEvent.click(candidateButton("wren_hollis"));
    fireEvent.click(screen.getByTestId("cancel-cabinet-proposal"));
    expect(panelState()).toBe("postSelected");
  });

  it("browsing, selecting, cancelling and Escape leave the shared store byte-identical", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    const before = storeSnapshot();

    fireEvent.click(selectPostButton("chief_of_staff"));
    fireEvent.click(candidateButton("ilse_marovec"));
    fireEvent.click(screen.getByTestId("cancel-cabinet-proposal"));
    fireEvent.click(candidateButton("wren_hollis"));
    fireEvent.keyDown(screen.getByTestId("cabinet-panel"), { key: "Escape" });
    fireEvent.click(selectPostButton("foreign_minister"));
    fireEvent.keyDown(screen.getByTestId("cabinet-panel"), { key: "Escape" });

    expect(storeSnapshot()).toBe(before);
    expect(before).toBe("[]");
  });
});

describe("CabinetScreen: appoint, replace, dismiss", () => {
  it("confirming a replacement stages exactly one explicit order", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    fireEvent.click(selectPostButton("chief_of_staff"));
    fireEvent.click(candidateButton("wren_hollis"));
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));

    expect(useDraftStore.getState().cabinetOrders).toEqual({
      chief_of_staff: { characterId: "wren_hollis", origin: "explicit" },
    });
    expect(panelState()).toBe("idle");
    expect(screen.getByTestId("staged-cabinet-summary")).toHaveTextContent("Wren Hollis");
  });

  it("confirming a dismissal stages a null order and costs nothing", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    fireEvent.click(selectPostButton("chief_of_staff"));
    fireEvent.click(screen.getByTestId("propose-dismissal"));
    expect(screen.getByTestId("cabinet-review-lines")).toHaveTextContent(
      "Hal Verrin is dismissed as chief of staff.",
    );
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));

    expect(useDraftStore.getState().cabinetOrders).toEqual({
      chief_of_staff: { characterId: null, origin: "explicit" },
    });
  });

  it("removing a staged order clears it", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    fireEvent.click(selectPostButton("chief_of_staff"));
    fireEvent.click(candidateButton("wren_hollis"));
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));
    fireEvent.click(screen.getByTestId("staged-cabinet-summary").querySelector("[data-remove-order]") as HTMLElement);
    expect(useDraftStore.getState().cabinetOrders).toEqual({});
  });
});

describe("CabinetScreen: the transfer", () => {
  async function stageTransfer() {
    renderScreen();
    await screen.findByText("chief of staff");
    fireEvent.click(selectPostButton("chief_of_staff"));
    fireEvent.click(candidateButton("ilse_marovec"));
  }

  it("states every resulting post change before confirmation", async () => {
    await stageTransfer();
    const review = screen.getByTestId("cabinet-review-lines");
    expect(review).toHaveTextContent("Ilse Marovec becomes chief of staff.");
    expect(review).toHaveTextContent("foreign minister is left vacant.");
    expect(review).toHaveTextContent("Costs 276 political capital.");
  });

  it("confirming writes TWO orders: the appointment and its generated companion", async () => {
    await stageTransfer();
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));
    expect(useDraftStore.getState().cabinetOrders).toEqual({
      chief_of_staff: {
        characterId: "ilse_marovec",
        origin: "explicit",
        requiresVacatingPost: "foreign_minister",
      },
      foreign_minister: { characterId: null, origin: "generated", generatedBy: "chief_of_staff" },
    });
  });

  it("the companion has no independent Remove control", async () => {
    await stageTransfer();
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));
    const summary = screen.getByTestId("staged-cabinet-summary");
    expect(summary.querySelector('[data-remove-order="chief_of_staff"]')).not.toBeNull();
    expect(summary.querySelector('[data-remove-order="foreign_minister"]')).toBeNull();
    expect(summary.querySelector('[data-generated-note="foreign_minister"]')).not.toBeNull();
  });

  it("cancelling the transfer takes its companion with it", async () => {
    await stageTransfer();
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));
    fireEvent.click(
      screen.getByTestId("staged-cabinet-summary").querySelector('[data-remove-order="chief_of_staff"]') as HTMLElement,
    );
    expect(useDraftStore.getState().cabinetOrders).toEqual({});
  });

  it("an explicit order on the origin is preserved, and the review says so", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    // Stage the ORIGIN first.
    fireEvent.click(selectPostButton("foreign_minister"));
    fireEvent.click(candidateButton("wren_hollis"));
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));
    // Now the transfer.
    fireEvent.click(selectPostButton("chief_of_staff"));
    fireEvent.click(candidateButton("ilse_marovec"));
    expect(screen.getByTestId("cabinet-review-lines")).toHaveTextContent(
      "foreign minister keeps its staged order: Wren Hollis.",
    );
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));
    expect(useDraftStore.getState().cabinetOrders["foreign_minister"]).toEqual({
      characterId: "wren_hollis",
      origin: "explicit",
    });
  });

  it("editing the companion promotes it, and the transfer's cancellation then leaves it standing", async () => {
    await stageTransfer();
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));
    // Edit the generated companion into a real appointment.
    fireEvent.click(selectPostButton("foreign_minister"));
    fireEvent.click(candidateButton("wren_hollis"));
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));
    expect(useDraftStore.getState().cabinetOrders["foreign_minister"]?.origin).toBe("explicit");

    fireEvent.click(
      screen.getByTestId("staged-cabinet-summary").querySelector('[data-remove-order="chief_of_staff"]') as HTMLElement,
    );
    expect(useDraftStore.getState().cabinetOrders).toEqual({
      foreign_minister: { characterId: "wren_hollis", origin: "explicit" },
    });
  });

  it("removing a promoted companion RESTORES the generated one, so the transfer stays coherent", async () => {
    await stageTransfer();
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));
    fireEvent.click(selectPostButton("foreign_minister"));
    fireEvent.click(candidateButton("wren_hollis"));
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));
    fireEvent.click(
      screen.getByTestId("staged-cabinet-summary").querySelector('[data-remove-order="foreign_minister"]') as HTMLElement,
    );
    expect(useDraftStore.getState().cabinetOrders["foreign_minister"]).toEqual({
      characterId: null,
      origin: "generated",
      generatedBy: "chief_of_staff",
    });
    expect(screen.getByTestId("staged-cabinet-summary")).toHaveTextContent(
      "foreign minister is left vacant",
    );
  });
});

describe("CabinetScreen: refusals and occupancy", () => {
  it("an unwilling candidate is text, not a control, with prose and no raw code", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    fireEvent.click(selectPostButton("foreign_minister"));

    expect(document.querySelector('[data-candidate-option="tomas_bekker"]')).toBeNull();
    const refused = document.querySelector('[data-candidate-refused="tomas_bekker"]');
    expect(refused).not.toBeNull();
    expect(refused?.textContent).toContain("beneath them");
    expect(document.body.textContent ?? "").not.toContain("cabinet_candidate_refuses_this_post");
  });

  it("the incumbent of the selected post is marked, not refused, and offers no order", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    fireEvent.click(selectPostButton("chief_of_staff"));
    expect(document.querySelector('[data-candidate-option="hal_verrin"]')).toBeNull();
    expect(document.querySelector('[data-candidate-incumbent="hal_verrin"]')?.textContent).toContain(
      "already in post",
    );
  });

  it("a transfer candidate says which post appointing them would vacate", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    fireEvent.click(selectPostButton("chief_of_staff"));
    expect(document.querySelector('[data-candidate-transfer="ilse_marovec"]')?.textContent).toContain(
      "Currently foreign minister",
    );
  });
});

describe("CabinetScreen: accessibility and layout", () => {
  it("every interactive control is a native button", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    fireEvent.click(selectPostButton("chief_of_staff"));
    fireEvent.click(candidateButton("wren_hollis"));
    for (const node of Array.from(document.querySelectorAll("[data-post-option],[data-candidate-option],[data-testid='confirm-cabinet-order'],[data-testid='cancel-cabinet-proposal']"))) {
      expect(node.tagName).toBe("BUTTON");
    }
  });

  it("announces each transition through one polite live region", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    const region = document.querySelector('[role="status"][aria-live="polite"]');
    expect(document.querySelectorAll('[role="status"][aria-live="polite"]')).toHaveLength(1);

    fireEvent.click(selectPostButton("chief_of_staff"));
    expect(region?.textContent).toContain("chief of staff selected");

    fireEvent.click(candidateButton("wren_hollis"));
    expect(region?.textContent).toContain("Nothing is staged until you confirm");

    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));
    expect(region?.textContent).toContain("Nobody has been appointed yet");
  });

  it("hides no information-bearing node at narrow widths", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    const panel = screen.getByTestId("cabinet-panel");
    expect(panel.querySelectorAll(".hidden")).toHaveLength(0);
    expect(panel.className).not.toContain("hidden");
  });
});

describe("CabinetScreen: what it submits", () => {
  it("a staged transfer becomes one canonical cabinet decision", async () => {
    renderScreen();
    await screen.findByText("chief of staff");
    fireEvent.click(selectPostButton("chief_of_staff"));
    fireEvent.click(candidateButton("ilse_marovec"));
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));

    const decisions = buildDecisions(useDraftStore.getState());
    expect(decisions).toHaveLength(1);
    expect(JSON.stringify(decisions)).toBe(
      JSON.stringify([
        {
          kind: "cabinet",
          orders: [
            { post: "chief_of_staff", character_id: "ilse_marovec" },
            { post: "foreign_minister" },
          ],
        },
      ]),
    );
  });

  it("navigation preserves the staged orders and their provenance", async () => {
    const first = renderScreen();
    await screen.findByText("chief of staff");
    fireEvent.click(selectPostButton("chief_of_staff"));
    fireEvent.click(candidateButton("ilse_marovec"));
    fireEvent.click(screen.getByTestId("confirm-cabinet-order"));
    const staged = storeSnapshot();

    first.unmount();
    renderScreen();
    await screen.findByText("chief of staff");
    expect(storeSnapshot()).toBe(staged);
    expect(screen.getByTestId("staged-cabinet-summary")).toHaveTextContent("Ilse Marovec");
  });
});

describe("CabinetScreen: no campaign", () => {
  it("asks for a campaign rather than rendering an empty cabinet", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SessionProvider>
          <CabinetScreen navigate={() => {}} />
        </SessionProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Start or load a campaign/i)).toBeInTheDocument();
  });
});
