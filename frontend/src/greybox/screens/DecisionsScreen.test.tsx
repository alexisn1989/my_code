/**
 * Gate 4A2 -- proves the mandate's "terminal state disables Resolve and
 * directs to the terminal screen" guarantee holds on the actual composer
 * screen, not just by inspection: when the dashboard's `terminal` field is
 * set, DecisionsScreen must never render a Resolve control, and must offer a
 * way to reach the terminal screen instead. When the campaign is still
 * active, the ordinary composer (with its Resolve button) must render.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DecisionsScreen } from "./DecisionsScreen";
import { SessionProvider } from "../../state/SessionContext";

const ACTIVE_DASHBOARD = {
  revision: "rev-1",
  country_name: "Testland",
  turn: 3,
  terminal: null,
};

const CONCLUDED_DASHBOARD = {
  revision: "rev-1",
  country_name: "Testland",
  turn: 9,
  terminal: { bucket: "defeat", headline: "The government collapsed.", reason_label: "Collapse", turn: 9 },
};

const DECISION_OPTIONS = {
  revision: "rev-1",
  blocs: [],
  chambers: [],
  constitutional_axes: [],
  cabinet_posts: [],
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

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

function renderScreen(dashboard: unknown) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/game/state")) {
      return Promise.resolve(jsonResponse(dashboard));
    }
    if (url.includes("/api/game/decision-options")) {
      return Promise.resolve(jsonResponse(DECISION_OPTIONS));
    }
    throw new Error(`unexpected fetch: ${url}`);
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <SessionProvider>{children}</SessionProvider>
      </QueryClientProvider>
    );
  }

  return render(<DecisionsScreen navigate={vi.fn()} />, { wrapper: Wrapper });
}

describe("DecisionsScreen and terminal state", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("disables Resolve entirely and directs to the terminal screen once the campaign has concluded", async () => {
    renderScreen(CONCLUDED_DASHBOARD);

    await waitFor(() => expect(screen.getByText("The campaign has ended")).toBeInTheDocument());

    expect(screen.queryByRole("button", { name: /resolve turn/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /go to victory \/ defeat/i })).toBeInTheDocument();
  });

  /* Gate 4A3 Commit 5: THE HEADING ORDER OF THIS BRANCH, which was wrong and nothing caught.
   *
   * The concluded branch used to return the `Panel` alone, and a `Panel` is an `<h3>`. With no `<h2>`
   * above it the document jumped from the site banner's `<h1>` straight to an `<h3>`, which axe reports
   * as `heading-order` (moderate). It went unseen for two gates because this branch renders only in a
   * CONCLUDED campaign and every audit before Commit 5 ran mid-campaign -- the real-browser sweep found
   * it the first time a campaign was driven to its end (`e2e/terminal-coverage.spec.ts`).
   *
   * That browser assertion is the primary guard, since heading order is a whole-document property. This
   * one is here because it is three orders of magnitude faster and fails for the same reason: it pins
   * the screen heading's LEVEL and its position before the panel, so the structure cannot regress
   * without a red test long before anyone runs Playwright. */
  it("keeps the screen heading, so a concluded campaign does not jump from h1 to h3", async () => {
    renderScreen(CONCLUDED_DASHBOARD);

    await waitFor(() => expect(screen.getByText("The campaign has ended")).toBeInTheDocument());

    const screenHeading = screen.getByRole("heading", { name: "Decision workspace" });
    expect(screenHeading.tagName).toBe("H2");

    const panelHeading = screen.getByRole("heading", { name: "The campaign has ended" });
    expect(panelHeading.tagName).toBe("H3");

    // And in that order: an h3 appearing before its h2 would be the same defect wearing both tags.
    expect(screenHeading.compareDocumentPosition(panelHeading)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("renders the ordinary composer, with a Resolve control, while the campaign is still active", async () => {
    renderScreen(ACTIVE_DASHBOARD);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /resolve turn/i })).toBeInTheDocument(),
    );
    expect(screen.queryByText("The campaign has ended")).not.toBeInTheDocument();
  });

  /* ----------------------------------------------------------------------------------------------
   * Gate 4A3 Commit 4 -- the copy pass, as EXACT rendered strings.
   *
   * "Slot" is `policySlot`, a field name in `src/state/draft.ts`. It told a player nothing, and this
   * is also the screen that keeps the one-budget-or-amendment limit: the introduction deliberately
   * does NOT state it, because stating it there would imply the limit governs the whole turn rather
   * than the policy proposal alone.
   * -------------------------------------------------------------------------------------------- */

  it("states the one-proposal-per-turn limit in the player's terms, not as a 'slot'", async () => {
    renderScreen(ACTIVE_DASHBOARD);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /resolve turn/i })).toBeInTheDocument(),
    );
    expect(
      screen.getByText(
        "You can put forward one budget or one constitutional amendment each turn, never both. " +
          "Selecting a card replaces the other. Choosing \u201cTake no major action\u201d is a valid " +
          "turn with no proposal.",
      ),
    ).toBeInTheDocument();
  });

  it("uses typographic quotation marks, matching the rest of the interface", async () => {
    renderScreen(ACTIVE_DASHBOARD);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /resolve turn/i })).toBeInTheDocument(),
    );
    const body = document.body.textContent ?? "";
    expect(body).toContain("\u201cTake no major action\u201d");
    expect(body).not.toContain('"Take no major action"');
  });

  // Found by `check:copy` and not by this commit's own survey of five sites, which had grepped for
  // three specific PHRASES rather than for the words. Recorded here as its own assertion so the
  // relationship-investment panel cannot drift back to describing itself as a slot.
  it("describes relationship investment by what it does, not by which slot it occupies", async () => {
    renderScreen(ACTIVE_DASHBOARD);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /resolve turn/i })).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("heading", { name: "Relationship investment (separate from your proposal)" }),
    ).toBeInTheDocument();
    expect(document.body.textContent ?? "").toContain(
      "Separate from the budget or amendment above, so staging one does not use up the other.",
    );
  });

  it("no player-visible text on this screen says 'slot'", async () => {
    renderScreen(ACTIVE_DASHBOARD);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /resolve turn/i })).toBeInTheDocument(),
    );
    // Text nodes AND the attributes a player reads or hears -- the panel title that said
    // "(separate slot)" was a `title` prop, invisible to a `textContent` scan.
    const rendered: string[] = [document.body.textContent ?? ""];
    for (const node of Array.from(
      document.body.querySelectorAll("[title], [aria-label], [placeholder], [alt]"),
    )) {
      for (const attribute of ["title", "aria-label", "placeholder", "alt"]) {
        const value = node.getAttribute(attribute);
        if (value !== null) rendered.push(value);
      }
    }
    for (const text of rendered) {
      expect(text).not.toMatch(/\bslots?\b/i);
    }
  });
});
