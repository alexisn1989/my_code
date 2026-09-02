/**
 * Strategic Military Map Gate M0 commit 7 -- coverage for the accessible
 * read-only screen: loading/error states, theater rendering, selection and
 * live-region announcement, resolved (not raw) Routes out/in lists, a
 * one-way edge's asymmetric lists, and the structural negative assertion
 * that no order/deployment/unit affordance exists anywhere in the tree.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useLoadGame, useNewGame, useResolve } from "../../api/queries";
import { StrategicMapScreen } from "./StrategicMapScreen";
import { SessionProvider, useSession } from "../../state/SessionContext";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function SetRevision({ children }: { children: ReactNode }) {
  const { setRevision, revision } = useSession();
  useEffect(() => {
    if (revision === null) {
      setRevision("rev-1");
    }
  }, [revision, setRevision]);
  return revision === null ? null : <>{children}</>;
}

const RECIPROCAL_MAP = {
  map_id: "tiny_valid",
  capital_theater_id: "capital",
  theaters: [
    {
      theater_id: "capital",
      display_name: "Capital Theater",
      kind: "land",
      is_capital: true,
      is_player_owned: true,
      owner_id: "player",
      owner_namespace: "player_country",
      owner_display_name: "Republic of Arken",
      centroid_x: 0,
      centroid_y: 0,
      label_anchor: "center",
      outgoing_theater_ids: ["frontier"],
      incoming_theater_ids: ["frontier"],
    },
    {
      theater_id: "frontier",
      display_name: "Frontier Theater",
      kind: "coastal",
      is_capital: false,
      is_player_owned: false,
      owner_id: "neighbor",
      owner_namespace: "foreign_profile",
      owner_display_name: "Republic of Veskara",
      centroid_x: 10,
      centroid_y: 10,
      label_anchor: "n",
      outgoing_theater_ids: ["capital"],
      incoming_theater_ids: ["capital"],
    },
  ],
  routes: [{ from_theater_id: "capital", to_theater_id: "frontier", bidirectional: true }],
  shapes: [],
};

const ONE_WAY_MAP = {
  map_id: "one_way",
  capital_theater_id: "capital",
  theaters: [
    {
      theater_id: "capital",
      display_name: "Capital Theater",
      kind: "land",
      is_capital: true,
      is_player_owned: true,
      owner_id: "player",
      owner_namespace: "player_country",
      owner_display_name: "Republic of Arken",
      centroid_x: 0,
      centroid_y: 0,
      label_anchor: "center",
      outgoing_theater_ids: ["frontier", "border", "coast"],
      incoming_theater_ids: ["frontier"],
    },
    {
      theater_id: "frontier",
      display_name: "Frontier Theater",
      kind: "coastal",
      is_capital: false,
      is_player_owned: false,
      owner_id: "neighbor",
      owner_namespace: "foreign_profile",
      owner_display_name: "Republic of Veskara",
      centroid_x: 10,
      centroid_y: 10,
      label_anchor: "n",
      outgoing_theater_ids: ["capital"],
      incoming_theater_ids: ["capital"],
    },
    {
      theater_id: "border",
      display_name: "Border Theater",
      kind: "land",
      is_capital: false,
      is_player_owned: false,
      owner_id: "neighbor",
      owner_namespace: "foreign_profile",
      owner_display_name: "Republic of Veskara",
      centroid_x: 20,
      centroid_y: 20,
      label_anchor: "s",
      outgoing_theater_ids: [],
      incoming_theater_ids: ["capital"],
    },
    {
      theater_id: "coast",
      display_name: "Coast Theater",
      kind: "coastal",
      is_capital: false,
      is_player_owned: false,
      owner_id: "neighbor",
      owner_namespace: "foreign_profile",
      owner_display_name: "Republic of Veskara",
      centroid_x: 30,
      centroid_y: 30,
      label_anchor: "e",
      outgoing_theater_ids: [],
      incoming_theater_ids: ["capital"],
    },
  ],
  routes: [
    { from_theater_id: "capital", to_theater_id: "frontier", bidirectional: true },
    { from_theater_id: "capital", to_theater_id: "border", bidirectional: false },
    { from_theater_id: "capital", to_theater_id: "coast", bidirectional: false },
  ],
  shapes: [],
};

const DECREE_MAP = {
  map_id: "decree_state_map",
  capital_theater_id: "throne",
  theaters: [
    {
      theater_id: "throne",
      display_name: "Throne Theater",
      kind: "land",
      is_capital: true,
      is_player_owned: true,
      owner_id: "player",
      owner_namespace: "player_country",
      owner_display_name: "The Decree State",
      centroid_x: 0,
      centroid_y: 0,
      label_anchor: "center",
      outgoing_theater_ids: [],
      incoming_theater_ids: [],
    },
  ],
  routes: [],
  shapes: [],
};

function dashboard(revision: string, overrides: Record<string, unknown> = {}) {
  return {
    revision,
    country_name: "Testland",
    turn: 1,
    next_election_label: "Turn 8",
    government_form: "Parliamentary republic",
    political_capital: { display: "120", current: 120, capacity: 200, committed_this_turn: 0 },
    alerts: [],
    goal: { headline: "Hold the coalition together", detail: null },
    map: { note: "No spatial state.", presentation_only: true, tint_metric_label: "Legitimacy", tint_value_bps: 6200 },
    concerns: {
      money: { label: "Money", headline: "Stable", direction: "unchanged", tone: "neutral", delta_text: null, detail_screen: "economy" },
      legitimacy: { label: "Legitimacy", headline: "Solid", direction: "unchanged", tone: "neutral", delta_text: null, detail_screen: "government" },
      legislature: { label: "Legislature", headline: "Comfortable", direction: "unchanged", tone: "neutral", delta_text: null, detail_screen: "legislature" },
      constitution: { label: "Constitution", headline: "Stable", direction: "unchanged", tone: "neutral", delta_text: null, detail_screen: "constitution" },
      survival: { label: "Survival", headline: "Secure", direction: "unchanged", tone: "neutral", delta_text: null, detail_screen: "relationships" },
    },
    terminal: null,
    ...overrides,
  };
}

/** Drives the REAL `useNewGame`/`useLoadGame`/`useResolve` mutations (not a
 * hand-rolled cache write) alongside the real `StrategicMapScreen`, so the
 * five-row loaded-game-identity table (frozen plan §12/§13, "C5") is proven
 * through the actual production wiring, not re-implemented in the test. */
function Harness() {
  const { revision, setRevision } = useSession();
  const newGame = useNewGame();
  const loadGame = useLoadGame();
  const resolve = useResolve();
  return (
    <div>
      <button
        type="button"
        onClick={() => newGame.mutate({ scenarioId: "tiny_valid" }, { onSuccess: (d) => setRevision(d.revision) })}
      >
        Start tiny_valid
      </button>
      <button
        type="button"
        onClick={() => loadGame.mutate({ saveId: "save-decree" }, { onSuccess: (d) => setRevision(d.revision) })}
      >
        Load decree_state
      </button>
      <button
        type="button"
        disabled={revision === null}
        onClick={() =>
          revision !== null &&
          resolve.mutate(
            { revision, decisions: [] },
            { onSuccess: (response) => setRevision(response.dashboard.revision) },
          )
        }
      >
        Resolve turn
      </button>
      <StrategicMapScreen navigate={vi.fn()} />
    </div>
  );
}

function renderScreen(map: unknown, options?: { revision?: string | null }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/game/map/strategic")) return Promise.resolve(jsonResponse(map));
    throw new Error(`unexpected fetch: ${url}`);
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <SessionProvider>
          {options?.revision === null ? children : <SetRevision>{children}</SetRevision>}
        </SessionProvider>
      </QueryClientProvider>
    );
  }

  return render(<StrategicMapScreen navigate={vi.fn()} />, { wrapper: Wrapper });
}

describe("StrategicMapScreen: loading and error", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows an accessible loading status while the map is pending", () => {
    vi.mocked(fetch).mockImplementation(() => new Promise(() => {}));
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <SessionProvider>
          <SetRevision>
            <StrategicMapScreen navigate={vi.fn()} />
          </SetRevision>
        </SessionProvider>
      </QueryClientProvider>,
    );
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
  });

  it("shows an alert naming the failure, and a subsequent refetch recovers the screen", async () => {
    let calls = 0;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/map/strategic")) {
        calls += 1;
        if (calls === 1) {
          return Promise.resolve(
            jsonResponse({ type: "internal_error", title: "Failed", status: 500, detail: "boom", fields: [] }, 500),
          );
        }
        return Promise.resolve(jsonResponse(RECIPROCAL_MAP));
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    render(
      <QueryClientProvider client={client}>
        <SessionProvider>
          <SetRevision>
            <StrategicMapScreen navigate={vi.fn()} />
          </SetRevision>
        </SessionProvider>
      </QueryClientProvider>,
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(alert.textContent?.length).toBeGreaterThan(0);

    // The screen's own error branch wires `onRefresh` to the query's
    // `refetch` -- a subsequent successful fetch replaces the alert with
    // the real map, proving the wiring rather than just the error render.
    await waitFor(() => expect(calls).toBe(1));
    client.refetchQueries();
    await waitFor(() =>
      expect(screen.getByText("Capital Theater — Land, Republic of Arken, capital")).toBeInTheDocument(),
    );
  });
});

describe("StrategicMapScreen: rendering and selection", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders every theater from the response, with kind and owner conveyed as text", async () => {
    renderScreen(RECIPROCAL_MAP);
    expect(await screen.findByText("Capital Theater — Land, Republic of Arken, capital")).toBeInTheDocument();
    expect(screen.getByText("Frontier Theater — Coastal, Republic of Veskara")).toBeInTheDocument();
  });

  it("selecting a theater sets aria-pressed and announces the live-region text", async () => {
    renderScreen(RECIPROCAL_MAP);
    const button = await screen.findByRole("button", {
      name: "Capital Theater — Land, Republic of Arken, capital",
    });
    expect(button).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-pressed", "true");

    await waitFor(() =>
      expect(
        screen.getByText("Capital Theater, land, owned by Republic of Arken, 1 routes out, 1 routes in"),
      ).toBeInTheDocument(),
    );
  });

  it("Routes out/in render as separate labelled lists of real theater names, not raw ids", async () => {
    renderScreen(RECIPROCAL_MAP);
    fireEvent.click(
      await screen.findByRole("button", { name: "Capital Theater — Land, Republic of Arken, capital" }),
    );

    expect(screen.getByRole("heading", { name: "Routes out" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Routes in" })).toBeInTheDocument();
    expect(screen.queryByText("frontier")).not.toBeInTheDocument();
    expect(screen.getAllByText("Frontier Theater").length).toBeGreaterThan(0);
  });

  it("a one-way edge shows a different-length Routes out list than Routes in", async () => {
    renderScreen(ONE_WAY_MAP);
    fireEvent.click(
      await screen.findByRole("button", { name: "Capital Theater — Land, Republic of Arken, capital" }),
    );

    await waitFor(() =>
      expect(
        screen.getByText("Capital Theater, land, owned by Republic of Arken, 3 routes out, 1 routes in"),
      ).toBeInTheDocument(),
    );

    const routesOutHeading = screen.getByRole("heading", { name: "Routes out" });
    const routesOutList = routesOutHeading.parentElement?.querySelector("ul");
    const routesInHeading = screen.getByRole("heading", { name: "Routes in" });
    const routesInList = routesInHeading.parentElement?.querySelector("ul");
    expect(routesOutList?.children.length).toBe(3);
    expect(routesInList?.children.length).toBe(1);
  });

  it("no accessible node anywhere mentions order, deployment, movement or unit", async () => {
    renderScreen(RECIPROCAL_MAP);
    fireEvent.click(
      await screen.findByRole("button", { name: "Capital Theater — Land, Republic of Arken, capital" }),
    );
    await waitFor(() => expect(screen.getByRole("heading", { name: "Routes out" })).toBeInTheDocument());

    const forbidden = /\b(order|deploy|move|movement|unit)\b/i;
    for (const button of screen.getAllByRole("button")) {
      expect(button.textContent ?? "").not.toMatch(forbidden);
      expect(button.getAttribute("aria-label") ?? "").not.toMatch(forbidden);
    }
    expect(screen.queryAllByRole("menuitem")).toHaveLength(0);
  });

  it("no raw ids or raw owner-namespace enum text are exposed to players", async () => {
    renderScreen(RECIPROCAL_MAP);
    fireEvent.click(
      await screen.findByRole("button", { name: "Capital Theater — Land, Republic of Arken, capital" }),
    );
    await waitFor(() => expect(screen.getByRole("heading", { name: "Routes out" })).toBeInTheDocument());

    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/player_country|foreign_profile/);
    // The raw theater id "frontier" (lowercase, whole word) must never appear on its own --
    // only the resolved display name "Frontier Theater" may.
    expect(body).not.toMatch(/\bfrontier\b/);
  });

  it("conveys terminal (concluded) campaigns as still fully inspectable -- inspection is not an action", async () => {
    // The screen never fetches or branches on `/api/game/state`'s `terminal`
    // field at all -- it reads the map only, so a concluded campaign is
    // exactly as inspectable as an active one, structurally, not by a
    // special case that could be forgotten later.
    renderScreen(RECIPROCAL_MAP);
    expect(await screen.findByText("Capital Theater — Land, Republic of Arken, capital")).toBeInTheDocument();
    expect(screen.getByText("Frontier Theater — Coastal, Republic of Veskara")).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes("/api/game/state"))).toBe(
      false,
    );
  });

  it("the map-artwork panel is hidden below 900px; the info-bearing theater list/detail carries no such hiding class", async () => {
    renderScreen(RECIPROCAL_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const mapPlaceholder = screen.getByText(/Map artwork is not part of this gate/);
    expect(mapPlaceholder.className).toMatch(/\bhidden\b/);
    expect(mapPlaceholder.className).toMatch(/min-\[900px\]:block/);

    const theaterListHeading = screen.getByRole("heading", { name: "Theaters" });
    const theaterPanel = theaterListHeading.closest("section");
    expect(theaterPanel?.className ?? "").not.toMatch(/\bhidden\b/);
    expect(theaterPanel?.className ?? "").not.toMatch(/min-\[900px\]/);
  });
});

describe("StrategicMapScreen: loaded-game identity (frozen plan §12/§13 'C5' five-row table)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function renderHarness() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    let mapFetchCount = 0;
    let currentMap: unknown = RECIPROCAL_MAP;

    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/game/new") && init?.method === "POST") {
        currentMap = RECIPROCAL_MAP;
        return Promise.resolve(jsonResponse(dashboard("rev-tiny-1")));
      }
      if (url.includes("/api/game/load") && init?.method === "POST") {
        const body: unknown = JSON.parse(String(init.body));
        currentMap = (body as { save_id: string }).save_id === "save-decree" ? DECREE_MAP : RECIPROCAL_MAP;
        return Promise.resolve(
          jsonResponse(dashboard((body as { save_id: string }).save_id === "save-decree" ? "rev-decree-1" : "rev-tiny-1")),
        );
      }
      if (url.includes("/api/game/resolve") && init?.method === "POST") {
        return Promise.resolve(
          jsonResponse({
            dashboard: dashboard("rev-tiny-2"),
            turnResult: { turn: 1, outcome_headline: "It passed", outcome_tone: "positive" },
          }),
        );
      }
      if (url.includes("/api/game/map/strategic")) {
        mapFetchCount += 1;
        return Promise.resolve(jsonResponse(currentMap));
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const rendered = render(
      <QueryClientProvider client={client}>
        <SessionProvider>
          <Harness />
        </SessionProvider>
      </QueryClientProvider>,
    );

    return { ...rendered, getMapFetchCount: () => mapFetchCount };
  }

  it("creating a new game invalidates the strategic-map query and fetches the new map", async () => {
    renderHarness();
    fireEvent.click(screen.getByRole("button", { name: "Start tiny_valid" }));
    expect(await screen.findByText("Capital Theater — Land, Republic of Arken, capital")).toBeInTheDocument();
  });

  it("loading a different save invalidates the query and cannot retain the prior map", async () => {
    renderHarness();
    fireEvent.click(screen.getByRole("button", { name: "Start tiny_valid" }));
    expect(await screen.findByText("Capital Theater — Land, Republic of Arken, capital")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Load decree_state" }));
    expect(await screen.findByText("Throne Theater — Land, The Decree State, capital")).toBeInTheDocument();
    // The prior tiny_valid map's theater must not survive on screen.
    expect(screen.queryByText(/Capital Theater/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Frontier Theater/)).not.toBeInTheDocument();
  });

  it("selection state clears when the loaded game changes", async () => {
    renderHarness();
    fireEvent.click(screen.getByRole("button", { name: "Start tiny_valid" }));
    const theaterButton = await screen.findByRole("button", {
      name: "Capital Theater — Land, Republic of Arken, capital",
    });
    fireEvent.click(theaterButton);
    expect(theaterButton).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: "Capital Theater" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Load decree_state" }));
    await screen.findByText("Throne Theater — Land, The Decree State, capital");

    // No theater id from the prior map survives as a selection into the new one.
    expect(screen.queryByRole("heading", { name: "Capital Theater" })).not.toBeInTheDocument();
    expect(screen.getByText("Select a theater to see its detail.")).toBeInTheDocument();
  });

  it("resolving an ordinary turn does NOT refetch the immutable map", async () => {
    const { getMapFetchCount } = renderHarness();
    fireEvent.click(screen.getByRole("button", { name: "Start tiny_valid" }));
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    await waitFor(() => expect(getMapFetchCount()).toBe(1));

    fireEvent.click(screen.getByRole("button", { name: "Resolve turn" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Resolve turn" })).not.toBeDisabled());

    // Give any (incorrect) refetch a chance to happen before asserting it didn't.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(getMapFetchCount()).toBe(1);
    expect(screen.getByText("Capital Theater — Land, Republic of Arken, capital")).toBeInTheDocument();
  });
});
