/**
 * Gate 4A2 closeout, final acceptance pass item 9 -- the closeout plan
 * identified missing automated coverage for preview presentation across the
 * four decision-route shapes (passed legislative, failed legislative,
 * decree, constitutional amendment), the always-present estimate label, and
 * bicameral chambers being shown separately rather than pooled. This file
 * closes that gap by driving `DecisionsScreen`'s real `PreviewPanel` through
 * mocked `/api/game/preview` responses shaped exactly like the real
 * `PreviewProjection`/`ChamberPreview` schema (see `schema.d.ts`), never
 * inventing a field the server does not actually return.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DecisionsScreen } from "./DecisionsScreen";
import { SessionProvider, useSession } from "../../state/SessionContext";

/** `revision` starts `null` in a fresh `SessionProvider`, and `handlePreview`
 * no-ops on a null revision -- exactly the pattern already established by
 * `DecisionsScreen.resilience.test.tsx`. */
function SetRevision({ children }: { children: ReactNode }) {
  const { setRevision, revision } = useSession();
  useEffect(() => {
    if (revision === null) {
      setRevision("rev-1");
    }
  }, [revision, setRevision]);
  return revision === null ? null : <>{children}</>;
}

const ACTIVE_DASHBOARD = {
  revision: "rev-1",
  country_name: "Testland",
  turn: 3,
  terminal: null,
};

const DECISION_OPTIONS = {
  revision: "rev-1",
  blocs: [],
  chambers: [],
  constitutional_axes: [],
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

/** The excluded-stochastic-channel names the real server sends -- arbitrary
 * strings from the preview's point of view, but real channel identifiers
 * (election swing, coup risk, unrest) the engine genuinely resolves
 * stochastically and genuinely excludes from a preview. */
const EXCLUDED_CHANNELS = ["election_swing", "coup_risk", "unrest_escalation"];

function baseProjection(overrides: Partial<Record<string, unknown>>) {
  return {
    affordable: true,
    chambers: [],
    committed_capital: 0,
    estimate: true,
    excludes_stochastic_channels: EXCLUDED_CHANNELS,
    has_proposal: true,
    influence_capital: 0,
    investment_capital: 0,
    opening_capital: 500,
    route: "legislative",
    route_capital_cost: 0,
    would_pass: false,
    ...overrides,
  };
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function renderScreenAndPreview(preview: unknown) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/api/game/state")) {
      return Promise.resolve(jsonResponse(ACTIVE_DASHBOARD));
    }
    if (url.includes("/api/game/decision-options")) {
      return Promise.resolve(jsonResponse(DECISION_OPTIONS));
    }
    if (url.includes("/api/game/preview") && init?.method === "POST") {
      return Promise.resolve(jsonResponse(preview));
    }
    throw new Error(`unexpected fetch: ${url}`);
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <SessionProvider>
          <SetRevision>{children}</SetRevision>
        </SessionProvider>
      </QueryClientProvider>
    );
  }

  return render(<DecisionsScreen navigate={vi.fn()} />, { wrapper: Wrapper });
}

async function clickPreview() {
  const button = await screen.findByRole("button", { name: /^preview$/i });
  fireEvent.click(button);
}

describe("DecisionsScreen preview presentation", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("a passed legislative preview shows the chamber tally and 'Would pass'", async () => {
    renderScreenAndPreview(
      baseProjection({
        route: "legislative",
        would_pass: true,
        chambers: [
          { chamber: "lower", supporting_seats: 58, required_seats: 51, total_seats: 100, carries: true },
        ],
      }),
    );
    await clickPreview();

    await waitFor(() => expect(screen.getByText("Would pass")).toBeInTheDocument());
    expect(screen.getByText("Carries", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("lower")).toBeInTheDocument();
  });

  it("a failed legislative preview shows the chamber tally and 'Would not pass'", async () => {
    renderScreenAndPreview(
      baseProjection({
        route: "legislative",
        would_pass: false,
        chambers: [
          { chamber: "lower", supporting_seats: 45, required_seats: 51, total_seats: 100, carries: false },
        ],
      }),
    );
    await clickPreview();

    await waitFor(() => expect(screen.getByText("Would not pass")).toBeInTheDocument());
    expect(screen.getByText("Fails")).toBeInTheDocument();
  });

  it("a decree preview carries no chamber vote and says so explicitly", async () => {
    renderScreenAndPreview(
      baseProjection({
        route: "decree",
        would_pass: true,
        chambers: [],
        route_capital_cost: 250,
        committed_capital: 250,
      }),
    );
    await clickPreview();

    await waitFor(() =>
      expect(screen.getByText("No legislative vote applies to this route.")).toBeInTheDocument(),
    );
    // A decree still resolves to a pass/fail estimate -- it just never routes
    // through a chamber table, since there is no vote to tabulate.
    expect(screen.getByText("Would pass")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("a bicameral constitutional-amendment preview shows both chambers as separate rows, never pooled", async () => {
    renderScreenAndPreview(
      baseProjection({
        route: "legislative",
        would_pass: true,
        chambers: [
          { chamber: "lower", supporting_seats: 67, required_seats: 67, total_seats: 100, carries: true },
          { chamber: "upper", supporting_seats: 40, required_seats: 40, total_seats: 60, carries: true },
        ],
      }),
    );
    await clickPreview();

    await waitFor(() => expect(screen.getByText("lower")).toBeInTheDocument());
    expect(screen.getByText("upper")).toBeInTheDocument();
    // Two distinct chamber rows, each carrying its OWN totals -- 100 and 60
    // seats respectively must both be visible; a pooled implementation would
    // show a single combined total (160) instead of these two.
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText("60")).toBeInTheDocument();
    // Both rows independently carry -- exactly two "Carries" cells, not one.
    expect(screen.getAllByText("Carries", { selector: "span" })).toHaveLength(2);
  });

  it("the estimate label and the real excluded-channel list are present on every route shape, and no channel is ever presented as guaranteed", async () => {
    for (const projection of [
      baseProjection({ route: "legislative", would_pass: true, chambers: [{ chamber: "lower", supporting_seats: 58, required_seats: 51, total_seats: 100, carries: true }] }),
      baseProjection({ route: "decree", would_pass: true, chambers: [] }),
      baseProjection({ has_proposal: false, chambers: [] }),
    ]) {
      const { unmount } = renderScreenAndPreview(projection);
      await clickPreview();

      await waitFor(() => expect(screen.getByText("Preview (estimate)")).toBeInTheDocument());
      for (const channel of EXCLUDED_CHANNELS) {
        expect(screen.getByText(new RegExp(channel))).toBeInTheDocument();
      }
      // The panel states plainly that this is an estimate, not a guarantee --
      // the one place stochastic channels are named is the exclusion notice
      // itself, never as an affirmed outcome.
      expect(screen.getByText(/an estimate, not a guarantee/i)).toBeInTheDocument();
      unmount();
      vi.mocked(fetch).mockReset();
    }
  });

  it("a no-proposal preview states plainly that only investment (if any) would apply, never a fabricated chamber result", async () => {
    renderScreenAndPreview(baseProjection({ has_proposal: false, chambers: [] }));
    await clickPreview();

    await waitFor(() =>
      expect(
        screen.getByText("No policy proposal is drafted. Only investment (if any) would apply."),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText("Would pass")).not.toBeInTheDocument();
    expect(screen.queryByText("Would not pass")).not.toBeInTheDocument();
  });
});

const SCHEMA_MODULES: Record<string, string> = import.meta.glob("../../api/schema.d.ts", {
  query: "?raw",
  import: "default",
  eager: true,
});
const SCHEMA_SOURCE = SCHEMA_MODULES["../../api/schema.d.ts"];

describe("PreviewProjection's real schema carries no stochastic-outcome field (structural, not prose)", () => {
  it("declares no field naming a guaranteed election/coup/unrest result", () => {
    // Reads the ACTUAL generated schema text (never hand-duplicated) and
    // confirms, structurally, that PreviewProjection has no field that could
    // be rendered as an affirmed stochastic outcome -- the same guarantee
    // DecisionsScreen.tsx's own docstring claims ("those fields simply do
    // not exist on PreviewProjection, so there is nothing to accidentally
    // display as if they did"), pinned here so a future field addition to
    // the generated contract cannot silently defeat it.
    if (SCHEMA_SOURCE === undefined) {
      throw new Error("schema.d.ts not found -- run `npm run generate:api` first");
    }
    const previewBlockMatch = /PreviewProjection: \{[\s\S]*?\n {8}\};/.exec(SCHEMA_SOURCE);
    expect(previewBlockMatch, "PreviewProjection block not found in schema.d.ts").not.toBeNull();
    const block = previewBlockMatch?.[0] ?? "";

    const forbiddenFieldNames = [
      "election_result",
      "election_outcome",
      "coup_outcome",
      "coup_result",
      "unrest_outcome",
      "unrest_result",
      "stochastic_outcome",
      "guaranteed_outcome",
      "swing_result",
    ];
    for (const forbidden of forbiddenFieldNames) {
      expect(block, `PreviewProjection must not declare ${forbidden}`).not.toContain(forbidden);
    }
  });
});
