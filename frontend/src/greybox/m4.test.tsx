/**
 * Gate 4A3 M-4: the restructured turn result, live and in History, over BACKEND-generated results
 * (`src/test/turn-results.json`, pinned by `backend/tests/test_result_fixtures.py`).
 *
 * Every case renders through the real screens -- the live Result screen and History's detail view --
 * which share `TurnResultView`.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import type { TurnResultProjection } from "../api/client";
import { decisionOptionsQueryKey, historyDetailQueryKey, historyQueryKey, liveTurnResultQueryKey } from "../api/queries";
import { recordedChamberLine } from "../format/parliament";
import { voteColours } from "../format/result";
import fixtures from "../test/turn-results.json";
import { SessionProvider, useSession } from "../state/SessionContext";
import { HistoryScreen } from "./screens/HistoryScreen";
import { ResultScreen } from "./screens/ResultScreen";
import { TurnResultView } from "./TurnResultView";

const ALL = fixtures as unknown as Record<string, TurnResultProjection>;
const CONTEXTS = ["live", "history"] as const;

function SetRevision({ children }: { children: ReactNode }) {
  const { setCampaignView, revision } = useSession();
  useEffect(() => {
    if (revision === null) setCampaignView("rev-1", "campaign-1");
  }, [revision, setCampaignView]);
  return revision === null ? null : <>{children}</>;
}

async function renderIn(context: "live" | "history", result: TurnResultProjection, seed?: (c: QueryClient) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  client.setQueryData(liveTurnResultQueryKey(), result);
  client.setQueryData(historyQueryKey(), [{ turn: result.turn, outcome_line: result.outcome_headline }]);
  client.setQueryData(historyDetailQueryKey(result.turn), { turnResult: result });
  seed?.(client);
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
    fireEvent.click(await screen.findByRole("button", { name: new RegExp(`^Turn ${result.turn}`) }));
  }
  return screen.findByTestId("turn-result-view");
}

const card = (view: HTMLElement) => within(view).getByTestId("proposal-card");

describe.each(CONTEXTS)("the proposal card (%s)", (context) => {
  it("a passed bicameral budget: the verdict, what was proposed, and both chambers' RECORDED tallies", async () => {
    const result = ALL["arkenBargainBudget"]!;
    const vote = result.recorded_vote!;
    const view = await renderIn(context, result);
    expect(within(card(view)).getByTestId("result-verdict")).toHaveTextContent("Enacted");
    expect(within(card(view)).getByTestId("result-proposal")).toHaveTextContent("A budget, passed: taxes lowered");
    const chambers = within(card(view)).getAllByTestId("result-chamber");
    expect(chambers.map((c) => c.dataset.chamber)).toEqual(vote.chambers.map((c) => c.chamber));
    for (const [i, chamber] of vote.chambers.entries()) {
      const node = chambers[i]!;
      expect(within(node).getByTestId("result-chamber-line")).toHaveTextContent(recordedChamberLine(chamber));
      // The rows sum to the chamber's recorded total, and exactly that many seats are filled.
      const rows = chamber.blocs ?? [];
      expect(rows.reduce((sum, row) => sum + row.supporting_seats, 0)).toBe(chamber.supporting_seats);
      const svg = within(node).getByTestId("hemicycle");
      expect(svg.dataset.mode).toBe("recorded");
      expect(svg.querySelectorAll('[data-seat][data-filled="true"]')).toHaveLength(chamber.supporting_seats);
      expect(svg.querySelectorAll("[data-seat]")).toHaveLength(chamber.total_seats);
    }
    // The bloc table, collapsed, lists the stored rows only.
    const table = within(card(view)).getByTestId("result-bloc-votes");
    expect(table).not.toHaveAttribute("open");
    expect(table.querySelectorAll("tbody tr")).toHaveLength(vote.chambers.reduce((n, c) => n + (c.blocs ?? []).length, 0));
  });

  it("a failed budget: 'Did not carry' and the blocking sentence", async () => {
    const view = await renderIn(context, ALL["valdrunFailedBudget"]!);
    expect(within(card(view)).getByTestId("result-verdict")).toHaveTextContent("Did not carry");
    expect(within(card(view)).getByTestId("result-card-drivers")).toHaveTextContent(
      "Lower chamber blocked the budget: 45 supporting votes; 51 required—6 short.",
    );
  });

  it("an amendment vote: chamber totals and the note -- no seat diagram and no bloc rows invented", async () => {
    const result = ALL["valdrunAmendmentFailed"]!;
    const view = await renderIn(context, result);
    expect(within(card(view)).getByTestId("result-verdict")).toHaveTextContent("Did not carry");
    expect(within(card(view)).getByTestId("result-chamber-line")).toHaveTextContent(
      recordedChamberLine(result.recorded_vote!.chambers[0]!),
    );
    expect(within(card(view)).getByTestId("amendment-blocs-note")).toHaveTextContent(
      "Per-bloc votes are not recorded for amendments.",
    );
    expect(within(card(view)).queryByTestId("hemicycle")).toBeNull();
    expect(within(card(view)).queryByTestId("result-bloc-votes")).toBeNull();
  });

  it("a decree: 'Enacted by decree', no tallies and no diagram", async () => {
    const view = await renderIn(context, ALL["valdrunDecreeBudget"]!);
    expect(within(card(view)).getByTestId("result-verdict")).toHaveTextContent("Enacted by decree");
    expect(card(view)).toHaveTextContent("Enacted by decree — no vote was held.");
    expect(within(card(view)).queryByTestId("result-chamber")).toBeNull();
    expect(within(card(view)).queryByTestId("hemicycle")).toBeNull();
  });

  it("no proposal: 'No proposal', and why no vote was held", async () => {
    const view = await renderIn(context, ALL["valdrunNoProposal"]!);
    expect(within(card(view)).getByTestId("result-verdict")).toHaveTextContent("No proposal");
    expect(within(card(view)).getByTestId("result-proposal")).toHaveTextContent("No proposal was put to a vote this turn.");
    expect(card(view).dataset.verdict).toBe("no_proposal");
  });

  it("shows the stored numbers, never today's chamber", async () => {
    const result = ALL["arkenBargainBudget"]!;
    const view = await renderIn(context, result, (client) => {
      // Today's options say something quite different; the card must not read them.
      client.setQueryData(decisionOptionsQueryKey("rev-1"), {
        chamber_details: [{ chamber: "lower", total_seats: 999, budget_required_seats: 777, amendment_required_seats: 888 }],
        blocs: [],
        last_recorded_vote: null,
      });
    });
    expect(card(view).textContent).not.toMatch(/999|777|888/);
    expect(card(view)).toHaveTextContent(recordedChamberLine(result.recorded_vote!.chambers[0]!));
  });
});

describe.each(CONTEXTS)("people and reactions (%s)", (context) => {
  it("names the leader who backed the budget, with the portrait from that turn", async () => {
    const result = ALL["arkenBargainBudget"]!;
    const bargain = result.drivers.find((d) => d.reason_id === "legislative_bargain_accepted")!;
    const view = await renderIn(context, result);
    const people = within(view).getAllByTestId("result-person");
    const leader = people.find((p) => p.dataset.reasonId === "legislative_bargain_accepted")!;
    expect(leader).toHaveTextContent(`${bargain.params!["character_display_name"]}`);
    expect(leader).toHaveTextContent(`backed the budget, for ${bargain.params!["asking_price"]} political capital.`);
    expect(leader.querySelector("[data-portrait-ref]")?.getAttribute("data-portrait-ref")).toBe(bargain.params!["character_portrait_ref"]);
    expect(people.map((p) => p.dataset.reasonId)).toEqual(["cabinet_replaced", "legislative_bargain_accepted"]);
  });

  it("a refusal states no price; a person with no portrait from that turn is named alone", async () => {
    const result: TurnResultProjection = {
      ...ALL["valdrunNoProposal"]!,
      drivers: [
        {
          category: "politics",
          reason_id: "legislative_bargain_refused_will_not_deal",
          label: "A party leader refused to deal.",
          params: { character_id: "x", character_display_name: "Nadia Brekke", party_display_name: "Reform Opposition", proposal_display_name: "the amendment" },
        },
      ],
    };
    const view = await renderIn(context, result);
    const person = within(view).getByTestId("result-person");
    expect(person).toHaveTextContent("Nadia Brekke of the Reform Opposition would not deal over the amendment.");
    expect(person.textContent).not.toMatch(/political capital|\d/);
    expect(person.querySelector("[data-portrait-ref]")).toBeNull();
  });

  it("shows each bloc's move in words, with its reaction under it", async () => {
    const result = ALL["arkenBargainBudget"]!;
    const view = await renderIn(context, result);
    const rows = within(view).getAllByTestId("result-bloc");
    expect(rows).toHaveLength(5);
    for (const row of rows) {
      const move = within(row).getByTestId("result-bloc-move").textContent ?? "";
      expect(move).toMatch(/^(▲ closer \+|▼ cooler -|• no change)/);
      expect(row.querySelectorAll('li[data-reason-id="enacted_policy_relationship_reaction"]')).toHaveLength(1);
    }
    expect(view.dataset.unmatchedComponents).toBe("0");
  });

  it("with no one acting and no bloc moving, says so", async () => {
    const view = await renderIn(context, ALL["valdrunNoProposal"]!);
    expect(view).toHaveTextContent("No one acted on your proposals this turn.");
    expect(view).toHaveTextContent("No bloc's relationship changed.");
  });
});

describe.each(CONTEXTS)("the collapsed bookkeeping and the Trace (%s)", (context) => {
  it("collapses routine steps, the ledger and what did not change, with counts", async () => {
    const result = ALL["arkenBargainBudget"]!;
    const view = await renderIn(context, result);
    for (const id of ["drivers-routine", "result-ledger", "result-unchanged"]) {
      expect(within(view).getByTestId(id)).not.toHaveAttribute("open");
    }
    expect(within(view).getByTestId("result-ledger")).toHaveTextContent(`What your decision committed (${result.ledger.length})`);
    expect(within(view).getByTestId("drivers-routine").querySelector("summary")).toHaveTextContent(/^Routine steps this turn \(\d+\)$/);
  });

  it("every Trace link lands on its line: one in the card, and a reaction under a bloc", async () => {
    const result = ALL["arkenBargainBudget"]!;
    const view = await renderIn(context, result);
    fireEvent.click(within(view).getByRole("button", { name: "Show exact values" }));
    const links = within(within(view).getByTestId("trace-reasons")).getAllByRole("link");
    expect(links).toHaveLength(result.drivers.length);
    for (const reason of ["legislative_vote_resolved", "enacted_policy_relationship_reaction", "turn_resolved"]) {
      const index = result.drivers.findIndex((d) => d.reason_id === reason);
      act(() => {
        fireEvent.click(links[index]!);
      });
      const focused = document.activeElement as HTMLElement;
      expect(focused.dataset.reasonId).toBe(reason);
      expect(focused.getAttribute("href") ?? links[index]!.getAttribute("href")).toBe(`#${focused.id}`);
    }
    // The routine target opened its section first.
    expect(within(view).getByTestId("drivers-routine")).toHaveAttribute("open");
  });
});

describe("History renders the same view as live", () => {
  it.each(Object.keys(ALL))("%s: identical DOM apart from the History note", (name) => {
    const result = ALL[name]!;
    const html = (context: "live" | "history") => {
      const { container, unmount } = render(<TurnResultView result={result} context={context} />);
      const copy = container.cloneNode(true) as HTMLElement;
      unmount();
      copy.querySelectorAll("p").forEach((p) => {
        if (p.textContent?.startsWith("Reviewing a past turn.")) p.remove();
      });
      return copy.innerHTML.replace(/data-context="[a-z]+"/, "").replace(/_r_[0-9a-z]+_|«r[0-9a-z]+»|:r[0-9a-z]+:/g, "ID");
    };
    expect(html("history")).toBe(html("live"));
  });

  it("uses one palette per vote for both chambers", () => {
    const vote = ALL["arkenBargainBudget"]!.recorded_vote!;
    const { container } = render(<TurnResultView result={ALL["arkenBargainBudget"]!} context="live" />);
    const colours = voteColours(vote);
    for (const seat of Array.from(container.querySelectorAll<SVGCircleElement>('[data-seat][data-filled="true"]'))) {
      expect(seat.getAttribute("fill")).toBe(colours[seat.dataset.party!]);
    }
  });
});

describe("one palette per vote, in the view", () => {
  it("colours a party the same in both chambers when they differ in membership and order", () => {
    const base = ALL["arkenBargainBudget"]!;
    const vote = base.recorded_vote!;
    const [lower, upper] = vote.chambers;
    // The upper chamber: a party missing, and the rest in reverse order.
    const upperRows = [...(upper!.blocs ?? [])].reverse().filter((row) => row.party_id !== "civic_union");
    const reshaped: TurnResultProjection = {
      ...base,
      recorded_vote: {
        ...vote,
        chambers: [
          lower!,
          {
            ...upper!,
            blocs: upperRows,
            total_seats: upperRows.reduce((n, row) => n + row.seats, 0),
            supporting_seats: upperRows.reduce((n, row) => n + row.supporting_seats, 0),
          },
        ],
      },
    };
    expect(upperRows[0]!.party_id).not.toBe((lower!.blocs ?? [])[0]!.party_id); // anti-vacuity
    const { container } = render(<TurnResultView result={reshaped} context="live" />);
    const byParty = new Map<string, Set<string>>();
    for (const seat of Array.from(container.querySelectorAll<SVGCircleElement>('[data-seat][data-filled="true"]'))) {
      const party = seat.dataset.party!;
      if (!byParty.has(party)) byParty.set(party, new Set());
      byParty.get(party)!.add(seat.getAttribute("fill") ?? "");
    }
    const colours = voteColours(reshaped.recorded_vote!);
    for (const [party, fills] of byParty) {
      expect([...fills], `${party}: one colour across both chambers`).toEqual([colours[party]]);
    }
    const upperParties = new Set(
      Array.from(container.querySelectorAll<HTMLElement>('[data-testid="result-chamber"][data-chamber="upper"] [data-seat]')).map(
        (seat) => seat.dataset.party,
      ),
    );
    expect(upperParties.has("civic_union")).toBe(false);
  });
});

describe("copy", () => {
  it.each(Object.keys(ALL))("%s never says 'projected'", (name) => {
    const { container } = render(<TurnResultView result={ALL[name]!} context="live" />);
    expect((container.textContent ?? "").toLowerCase()).not.toContain("projected");
  });
});
