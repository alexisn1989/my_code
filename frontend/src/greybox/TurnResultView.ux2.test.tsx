/**
 * Gate 4A3 UX-2 (U4): the turn result puts the cause first, folds bookkeeping away without losing
 * it, and moves reason ids out of the painted text into the Trace (T2).
 *
 * Every case runs against BOTH call sites: the live Turn Result screen and the History detail view.
 * They share `TurnResultView`, so each assertion is made through the real screen in each place.
 *
 * Keyboard: jsdom neither moves focus on Tab nor turns Enter on a link into activation, so these
 * tests assert the link is a real, tabbable `href` link, focus it, and dispatch the click its Enter
 * key produces. The genuine key press is exercised in the browser by `e2e/verify-ux.spec.ts @ux2`.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { historyDetailQueryKey, historyQueryKey, liveTurnResultQueryKey } from "../api/queries";
import { SessionProvider, useSession } from "../state/SessionContext";
import { HistoryScreen } from "./screens/HistoryScreen";
import { ResultScreen } from "./screens/ResultScreen";

const LABOR = {
  category: "economy",
  reason_id: "labor_market_resolved",
  label: "The labour market cleared.",
  params: {
    effective_labor_force: 1_000_000,
    total_employment: 948_000,
    unemployed_workers: 52_000,
    unfilled_jobs: 1_200,
    unemployment_rate_bps: 520,
  },
};
const BLOCKED = {
  category: "politics",
  reason_id: "budget_blocked",
  label: "The legislature blocked the budget.",
  params: {},
};
const INACTIVE = {
  category: "economy",
  reason_id: "sector_inactive",
  label: "A sector was inactive this turn.",
  params: { category: "defense_industry" },
};
const QUIET_EXTRACTION = {
  category: "economy",
  reason_id: "resource_extraction_resolved",
  label: "Resource extraction resolved.",
  params: {
    deposits_active: 4,
    deposits_depleted: 0,
    total_extraction_workers: 9_000,
    unassigned_resource_workers: 0,
    extraction_sector_real_output: 10,
    extraction_sector_potential_output: 10,
  },
};
const TURN = {
  category: "system",
  reason_id: "turn_resolved",
  label: "The turn resolved.",
  params: { turn: 3 },
};

const RESULT = {
  revision: "3.3",
  turn: 3,
  outcome_headline: "The budget was blocked.",
  outcome_tone: "negative",
  drivers: [LABOR, BLOCKED, INACTIVE, QUIET_EXTRACTION, TURN],
  ledger: [],
  unchanged: [],
  trace: [],
  terminal: null,
};

function SetRevision({ children }: { children: ReactNode }) {
  const { setCampaignView, revision } = useSession();
  useEffect(() => {
    if (revision === null) setCampaignView("3.3", "campaign-1");
  }, [revision, setCampaignView]);
  return revision === null ? null : <>{children}</>;
}

async function renderIn(context: "live" | "history") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  client.setQueryData(liveTurnResultQueryKey(), RESULT);
  client.setQueryData(historyQueryKey(), [{ turn: 3, outcome_line: "The budget was blocked." }]);
  client.setQueryData(historyDetailQueryKey(3), { turnResult: RESULT });
  render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <SetRevision>
          {context === "live" ? <ResultScreen navigate={() => {}} /> : <HistoryScreen navigate={() => {}} />}
        </SetRevision>
      </SessionProvider>
    </QueryClientProvider>,
  );
  if (context === "history") {
    fireEvent.click(await screen.findByRole("button", { name: /^Turn 3/ }));
  }
  const view = await screen.findByTestId("turn-result-view");
  expect(view).toHaveAttribute("data-context", context);
  return view;
}

function openTrace(view: HTMLElement) {
  fireEvent.click(within(view).getByRole("button", { name: "Show exact values" }));
  return within(view).getByTestId("trace-reasons");
}

function followByKeyboard(link: HTMLElement) {
  expect(link.tagName).toBe("A");
  expect(link.getAttribute("href")).toMatch(/^#/);
  expect(link.tabIndex, "a real link is in the tab order").toBe(0);
  act(() => link.focus());
  expect(document.activeElement).toBe(link);
  fireEvent.click(link);
}

describe.each(["live", "history"] as const)("U4 turn result (%s)", (context) => {
  it("paints no reason id outside the Trace", async () => {
    const view = await renderIn(context);
    const painted = view.textContent ?? "";
    for (const driver of RESULT.drivers) {
      expect(painted, driver.reason_id).not.toContain(driver.reason_id);
    }
  });

  it("keeps consequences visible and folds only bookkeeping, closed by default", async () => {
    const view = await renderIn(context);
    const visible = within(view).getByTestId("drivers-consequential");
    expect(visible).toHaveTextContent("The legislature blocked the budget.");
    expect(visible).toHaveTextContent("The Defence industry sector produced nothing this turn.");
    const routine = within(view).getByTestId("drivers-routine") as HTMLDetailsElement;
    expect(routine.open).toBe(false);
    expect(within(routine).getByText("Routine steps this turn (3)")).toBeInTheDocument();
    expect(routine).toHaveTextContent(
      "Labour market: 948,000 employed, 5.20% unemployment, 1,200 unfilled jobs.",
    );
    expect(routine).toHaveTextContent("Turn 3 resolved.");
    expect(visible).not.toHaveTextContent("Labour market");
  });

  it("lists one reason per driver in the Trace, in order, each linking to an existing anchor", async () => {
    const view = await renderIn(context);
    const links = within(openTrace(view)).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(RESULT.drivers.map((d) => d.reason_id));
    for (const [index, link] of links.entries()) {
      const target = document.getElementById(link.getAttribute("href")!.slice(1));
      expect(target, `anchor for ${link.textContent}`).not.toBeNull();
      expect(target).toHaveAttribute("data-reason-id", RESULT.drivers[index]!.reason_id);
    }
  });

  it("Enter on a routine reason opens Routine steps and focuses that driver", async () => {
    const view = await renderIn(context);
    const routine = within(view).getByTestId("drivers-routine") as HTMLDetailsElement;
    const link = within(openTrace(view)).getByRole("link", { name: "labor_market_resolved" });
    followByKeyboard(link);
    expect(routine.open).toBe(true);
    const focused = document.activeElement as HTMLElement;
    expect(focused.tagName).toBe("LI");
    expect(focused).toHaveAttribute("data-reason-id", "labor_market_resolved");
    expect(routine.contains(focused)).toBe(true);
    expect(focused).toHaveTextContent("Labour market: 948,000 employed");
  });

  it("Enter on a visible reason focuses it and leaves Routine steps closed", async () => {
    const view = await renderIn(context);
    const routine = within(view).getByTestId("drivers-routine") as HTMLDetailsElement;
    followByKeyboard(within(openTrace(view)).getByRole("link", { name: "budget_blocked" }));
    const focused = document.activeElement as HTMLElement;
    expect(focused).toHaveAttribute("data-reason-id", "budget_blocked");
    expect(focused).toHaveTextContent("The legislature blocked the budget.");
    expect(routine.open).toBe(false);
  });
});
