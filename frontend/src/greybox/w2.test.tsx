/**
 * Gate 4A3 W-2: what investments and cabinet posts do, as the player reads it.
 *
 * Every preview and option set is the SERVER'S output (`src/test/*.json`, pinned by
 * `backend/tests/test_objective_fixtures.py`); the backend tests (`test_effect_explanations.py`)
 * prove those numbers equal what resolution applies.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DecisionOptionsProjection, PreviewProjection } from "../api/client";
import { investmentEffectSentence } from "../format/format";
import { useDraftStore } from "../state/draft";
import { SessionProvider, useSession } from "../state/SessionContext";
import optionsJson from "../test/decision-options-valdrun.json";
import { OBJECTIVE_FIXTURE } from "../test/objectiveFixture";
import resultsJson from "../test/objective-results.json";
import { ConsequencesPanel } from "./policy/ConsequencesPanel";
import { CabinetScreen } from "./screens/CabinetScreen";
import { DecisionsScreen } from "./screens/DecisionsScreen";

const OPTIONS = optionsJson as unknown as DecisionOptionsProjection;
const RESULTS = resultsJson as unknown as Record<string, PreviewProjection>;

function concern(label: string) {
  return { label, headline: "x", delta_text: null, direction: "unchanged", tone: "neutral", detail_screen: "government" };
}

const DASHBOARD = {
  revision: "0.0",
  campaign_id: "campaign-1",
  turn: 0,
  country_name: "Kingdom of Valdrun",
  government_form: "Hereditary monarchy, unlimited decree authority",
  next_election_label: "None scheduled",
  concerns: {
    money: concern("Money"),
    legitimacy: concern("Legitimacy"),
    legislature: concern("Legislature"),
    constitution: concern("Constitution"),
    survival: concern("Survival"),
  },
  political_capital: { current: 500, capacity: 1000, committed_this_turn: 0, display: "500 / 1,000" },
  alerts: [],
  goal: { headline: "Nothing is pressing.", detail: null },
  objective: OBJECTIVE_FIXTURE,
  map: { presentation_only: true, tint_metric_label: "Legitimacy", tint_value_bps: 6000, note: "" },
  terminal: null,
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  useDraftStore.getState().clearDraft();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return json(DASHBOARD);
      if (url.includes("/api/game/decision-options")) return json(OPTIONS);
      return new Response(JSON.stringify({ detail: "not in this test" }), { status: 404 });
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

describe("what an investment would add", () => {
  it("words each real preview row, with the chief of staff's share", () => {
    const rows = RESULTS.previewInvestments!.investment_effects!;
    expect(rows).toHaveLength(5);
    const conservatives = rows.find((row) => row.bloc_display_name === "National Front Conservatives")!;
    expect(investmentEffectSentence(conservatives)).toBe(
      "National Front Conservatives: +16.68 points from 50 capital, including +1.23 points from your chief of staff (relationship -70.00% before this turn).",
    );
    render(<ConsequencesPanel preview={RESULTS.previewInvestments!} />);
    const list = screen.getByTestId("investment-effects");
    expect(within(list).getAllByRole("listitem")).toHaveLength(5);
    expect(list).toHaveTextContent("Relationship investments (their own effect only):");
  });

  it("says before resolving that an investment would change nothing and would be refused", () => {
    const preview = RESULTS.previewInvestmentNoEffect!;
    const row = preview.investment_effects![0]!;
    expect(row.no_effect).toBe(true);
    expect(investmentEffectSentence(row)).toBe(
      "Crown Party Core: 50 capital would change nothing here (relationship 100.00%), so resolving would refuse this investment.",
    );
    render(<ConsequencesPanel preview={preview} />);
    const items = within(screen.getByTestId("investment-effects")).getAllByRole("listitem");
    expect(items.every((item) => item.getAttribute("data-no-effect") === "true")).toBe(true);
  });

  it("shows nothing when no investment is drafted", () => {
    render(<ConsequencesPanel preview={RESULTS.previewPasses!} />);
    expect(screen.queryByTestId("investment-effects")).toBeNull();
  });

  it("explains what investments are for, on the Decisions screen", async () => {
    withCampaign(<DecisionsScreen navigate={vi.fn()} />);
    const guidance = await screen.findByTestId("investment-guidance");
    expect(guidance).toHaveTextContent("Relationships shape how blocs vote on your budgets and amendments");
    expect(guidance).toHaveTextContent("make up half of your support at a national election");
    expect(guidance).toHaveTextContent("drift back toward each bloc's usual stance");
  });
});

describe("what a cabinet post does", () => {
  it("states each post's effect and each candidate's, from the server", async () => {
    withCampaign(<CabinetScreen navigate={vi.fn()} />);
    for (const post of OPTIONS.cabinet_posts) {
      fireEvent.click(await screen.findByRole("button", { name: new RegExp(`^${post.post_display_name}`) }));
      expect(await screen.findByTestId("post-effect")).toHaveTextContent(post.post_effect_text);
      for (const candidate of post.candidates) {
        const effect = document.querySelector(`[data-candidate-effect="${candidate.character_id}"]`);
        if (candidate.candidate_accepts_post || candidate.currently_holds_post === post.post) {
          expect(effect?.textContent).toBe(candidate.effect_text);
        }
      }
    }
    expect(OPTIONS.cabinet_posts.map((post) => post.post_effect_text.split(":")[0])).toEqual([
      "Makes relationship investments more effective",
      "Improves the terms of foreign assistance",
    ]);
  });
});
