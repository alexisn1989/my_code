/**
 * Gate 4A3 UX-4g: a bloc whose relationship ends just below zero is shown with its sign, live and in
 * History (the two share one view), and a blocked budget names its votes rather than "seats".
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { historyDetailQueryKey, historyQueryKey, liveTurnResultQueryKey } from "../api/queries";
import { SessionProvider, useSession } from "../state/SessionContext";
import { HistoryScreen } from "./screens/HistoryScreen";
import { ResultScreen } from "./screens/ResultScreen";

const bloc = { party_id: "opposition", bloc_id: "reform", bloc_display_name: "Reform Bloc" };

const RESULT = {
  revision: "1.1",
  turn: 2,
  outcome_headline: "The budget was blocked.",
  outcome_tone: "caution",
  drivers: [
    { category: "politics", reason_id: "legislative_vote_resolved", label: "The legislature voted.", params: { route: "legislative", outcome: "failed_legislative", chambers_passed: 0, chambers_total: 1 } },
    { category: "politics", reason_id: "budget_blocked_by_legislature", label: "The legislature blocked the budget.", params: { chamber: "lower", supporting_seats: 45, required_yes_seats: 51, shortfall_seats: 6, opening: 500, total_committed: 0, legislative_committed: 0 } },
    { category: "politics", reason_id: "bloc_relationship_resolved", label: "A bloc's relationship with the government changed.", params: { ...bloc, opening_relationship_bps: 20, closing_relationship_bps: -50, applied_total_change_bps: -70 } },
  ],
  ledger: [],
  unchanged: [],
  trace: [],
  terminal: null,
};

function SetRevision({ children }: { children: ReactNode }) {
  const { setCampaignView, revision } = useSession();
  useEffect(() => {
    if (revision === null) setCampaignView("1.1", "campaign-1");
  }, [revision, setCampaignView]);
  return revision === null ? null : <>{children}</>;
}

async function renderIn(context: "live" | "history") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  client.setQueryData(liveTurnResultQueryKey(), RESULT);
  client.setQueryData(historyQueryKey(), [{ turn: 2, outcome_line: RESULT.outcome_headline }]);
  client.setQueryData(historyDetailQueryKey(2), { turnResult: RESULT });
  render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <SetRevision>
          {context === "live" ? <ResultScreen navigate={() => {}} /> : <HistoryScreen navigate={() => {}} />}
        </SetRevision>
      </SessionProvider>
    </QueryClientProvider>,
  );
  if (context === "history") fireEvent.click(await screen.findByRole("button", { name: /^Turn 2/ }));
  return screen.findByTestId("turn-result-view");
}

describe.each(["live", "history"] as const)("UX-4g corrections in the turn result (%s)", (context) => {
  it("a relationship ending just below zero keeps its minus sign", async () => {
    const view = await renderIn(context);
    expect(within(view).getByTestId("drivers-consequential")).toHaveTextContent(
      "Reform Bloc: relationship 0.20% → -0.50% (-0.70 points).",
    );
    expect(view.textContent ?? "").not.toContain("→ 0.50%");
  });

  it("the blocking chamber names supporting and required votes", async () => {
    const view = await renderIn(context);
    expect(within(view).getByTestId("drivers-consequential")).toHaveTextContent(
      "Lower chamber blocked the budget: 45 supporting votes; 51 required—6 short.",
    );
    expect(view.textContent ?? "").not.toContain("of 51 seats");
  });
});
