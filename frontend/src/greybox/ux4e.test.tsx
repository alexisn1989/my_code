/**
 * Gate 4A3 UX-4e: a decree turn's result, live and in History -- no claim that the legislature
 * voted, the outcome first, every bloc named, and the neutral "Turn outcome" heading (DR3).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { historyDetailQueryKey, historyQueryKey, liveTurnResultQueryKey } from "../api/queries";
import { SessionProvider, useSession } from "../state/SessionContext";
import { HistoryScreen } from "./screens/HistoryScreen";
import { ResultScreen } from "./screens/ResultScreen";

const bloc = (bloc_id: string, name: string) => ({ party_id: "governing_party", bloc_id, bloc_display_name: name });

// The order a real Valdrun decree turn records them in (economy first, the vote later).
const DRIVERS = [
  { category: "policy", reason_id: "tax_rate_changed", label: "A tax rate changed.", params: { field: "personal_income_rate_bps", old_bps: 2000, new_bps: 2500, category: "", old_amount: 0, new_amount: 0 } },
  { category: "economy", reason_id: "sector_inactive", label: "A sector was inactive this turn.", params: { category: "construction" } },
  { category: "politics", reason_id: "legitimacy_resolved", label: "Legitimacy was resolved.", params: { opening_legitimacy_bps: 6000, closing_legitimacy_bps: 6100, total_legitimacy_change_bps: 100 } },
  { category: "politics", reason_id: "legislative_vote_resolved", label: "The legislature voted.", params: { route: "decree", outcome: "enacted_by_decree", chambers_passed: 0, chambers_total: 0 } },
  { category: "politics", reason_id: "political_capital_ledger_resolved", label: "Political capital spending was recorded.", params: { total_committed: 250, legislative_committed: 250, relationship_committed: 0 } },
  { category: "politics", reason_id: "decree_bypass_relationship_reaction", label: "Blocs resented being bypassed by decree.", params: { ...bloc("core", "Crown Party Core"), decree_bypass_component_bps: -300 } },
  { category: "politics", reason_id: "bloc_relationship_resolved", label: "A bloc's relationship with the government changed.", params: { ...bloc("core", "Crown Party Core"), opening_relationship_bps: 6000, closing_relationship_bps: 5700, applied_total_change_bps: -300 } },
];

const RESULT = {
  revision: "1.1",
  turn: 1,
  outcome_headline: "The budget was enacted by decree. The legislature was bypassed.",
  outcome_tone: "caution",
  drivers: DRIVERS,
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
  client.setQueryData(historyQueryKey(), [{ turn: 1, outcome_line: RESULT.outcome_headline }]);
  client.setQueryData(historyDetailQueryKey(1), { turnResult: RESULT });
  render(
    <QueryClientProvider client={client}>
      <SessionProvider>
        <SetRevision>
          {context === "live" ? <ResultScreen navigate={() => {}} /> : <HistoryScreen navigate={() => {}} />}
        </SetRevision>
      </SessionProvider>
    </QueryClientProvider>,
  );
  if (context === "history") fireEvent.click(await screen.findByRole("button", { name: /^Turn 1/ }));
  return screen.findByTestId("turn-result-view");
}

describe.each(["live", "history"] as const)("a decree turn's result (%s)", (context) => {
  it("never says the legislature voted, beside 'the legislature was bypassed'", async () => {
    const view = await renderIn(context);
    expect(view).toHaveTextContent("The legislature was bypassed.");
    expect((view.textContent ?? "").toLowerCase()).not.toContain("voted");
  });

  it("puts the outcome first, and names the bloc", async () => {
    const view = await renderIn(context);
    const visible = within(view).getByTestId("drivers-consequential").querySelectorAll(":scope > li");
    expect(Array.from(visible).map((li) => li.textContent)).toEqual([
      "Personal income tax: 20.00% → 25.00%.",
      "Enacted by decree — no vote was held.",
      "The Construction sector produced nothing this turn.",
      "Legitimacy: 60.00% → 61.00% (+1.00 points).",
      "Crown Party Core resented being bypassed by decree (-3.00 points).",
      "Crown Party Core: relationship 60.00% → 57.00% (-3.00 points).",
    ]);
    expect(within(view).getByTestId("drivers-routine")).toHaveTextContent(
      "Capital committed this turn: 250 (250 to the vote or decree, 0 to relationships).",
    );
  });

  it("uses the neutral 'Turn outcome' heading (DR3)", async () => {
    const view = await renderIn(context);
    expect(within(view).getByRole("heading", { name: "Turn outcome" })).toBeInTheDocument();
    expect(within(view).queryByRole("heading", { name: /^Turn \d+ — outcome$/ })).toBeNull();
  });
});
