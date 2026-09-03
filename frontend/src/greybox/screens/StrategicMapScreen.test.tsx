/**
 * Strategic Military Map Gate M0 -- coverage for the accessible read-only
 * screen: loading/error states, theater rendering, selection and
 * live-region announcement, resolved (not raw) Routes out/in lists, a
 * one-way edge's asymmetric lists, and the structural negative assertion
 * that no order/deployment/unit affordance exists anywhere in the tree.
 *
 * Commit 7a adds the real SVG map's own battery: authored polygons and their
 * per-OWNER (never per-position) styling, hatch overlays, route lines with
 * direction arrows, theater nodes at authored centroids, the capital marker,
 * node/list selection synchronisation in both directions, the label-anchor
 * helper's five pinned cases, and the accessibility split that keeps the SVG
 * out of keyboard traversal entirely.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useLoadGame, useNewGame, useResolve } from "../../api/queries";
import { labelOffsetPosition } from "../../format/format";
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

  it("the visual map panel is hidden below 900px; the info-bearing theater list/detail carries no such hiding class", async () => {
    renderScreen(RECIPROCAL_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const visualPanel = screen.getByTestId("strategic-map-visual");
    expect(visualPanel.className).toMatch(/\bhidden\b/);
    expect(visualPanel.className).toMatch(/min-\[900px\]:block/);

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

// --- Commit 7a: the real SVG map ------------------------------------------
//
// `SVG_MAP` is deliberately richer than the fixtures above: two islands owned by ONE foreign
// sovereign (so per-owner styling is distinguishable from per-shape styling), a second, distinct
// foreign sovereign, land AND coastal theaters, all five label anchors, a capital, and both a
// reciprocal and a one-way route.

const SVG_MAP = {
  map_id: "svg_fixture",
  capital_theater_id: "capital",
  theaters: [
    {
      theater_id: "capital",
      display_name: "Capital Theater",
      kind: "land",
      is_capital: true,
      is_player_owned: true,
      owner_id: "arken",
      owner_namespace: "player_country",
      owner_display_name: "Republic of Arken",
      centroid_x: 1900,
      centroid_y: 3200,
      label_anchor: "center",
      outgoing_theater_ids: ["coast", "north_march"],
      incoming_theater_ids: ["coast", "north_march"],
    },
    {
      theater_id: "coast",
      display_name: "Arken Coast",
      kind: "coastal",
      is_capital: false,
      is_player_owned: true,
      owner_id: "arken",
      owner_namespace: "player_country",
      owner_display_name: "Republic of Arken",
      centroid_x: 1200,
      centroid_y: 5200,
      label_anchor: "w",
      outgoing_theater_ids: ["capital"],
      incoming_theater_ids: ["capital"],
    },
    {
      theater_id: "kessia_south",
      display_name: "Southern Kessia",
      kind: "land",
      is_capital: false,
      is_player_owned: false,
      owner_id: "kessia",
      owner_namespace: "foreign_profile",
      owner_display_name: "Kessia",
      centroid_x: 5400,
      centroid_y: 3800,
      label_anchor: "s",
      outgoing_theater_ids: ["vetruska_frontier"],
      incoming_theater_ids: ["north_march", "vetruska_frontier"],
    },
    {
      theater_id: "north_march",
      display_name: "Northern March",
      kind: "land",
      is_capital: false,
      is_player_owned: true,
      owner_id: "arken",
      owner_namespace: "player_country",
      owner_display_name: "Republic of Arken",
      centroid_x: 2200,
      centroid_y: 1900,
      label_anchor: "n",
      outgoing_theater_ids: ["capital", "kessia_south"],
      incoming_theater_ids: ["capital"],
    },
    {
      theater_id: "vetruska_frontier",
      display_name: "Vetruskan Frontier",
      kind: "land",
      is_capital: false,
      is_player_owned: false,
      owner_id: "vetruska",
      owner_namespace: "foreign_profile",
      owner_display_name: "Vetruska",
      centroid_x: 8200,
      centroid_y: 3500,
      label_anchor: "e",
      outgoing_theater_ids: ["kessia_south"],
      incoming_theater_ids: ["kessia_south"],
    },
  ],
  routes: [
    { from_theater_id: "capital", to_theater_id: "coast", bidirectional: true },
    { from_theater_id: "capital", to_theater_id: "north_march", bidirectional: true },
    { from_theater_id: "kessia_south", to_theater_id: "vetruska_frontier", bidirectional: true },
    // One-way, authored north_march -> kessia_south. Never flipped, never inferred.
    { from_theater_id: "north_march", to_theater_id: "kessia_south", bidirectional: false },
  ],
  shapes: [
    {
      shape_id: "shape_a_kessia_east",
      owner_id: "kessia",
      owner_namespace: "foreign_profile",
      owner_display_name: "Kessia",
      polygon: [
        [4200, 1800],
        [6200, 1500],
        [6800, 3600],
        [5600, 5400],
        [4100, 4400],
      ],
    },
    {
      shape_id: "shape_b_arken",
      owner_id: "arken",
      owner_namespace: "player_country",
      owner_display_name: "Republic of Arken",
      polygon: [
        [500, 2000],
        [2200, 1200],
        [3800, 2000],
        [3600, 5200],
        [1800, 6200],
        [500, 4800],
      ],
    },
    {
      // A SECOND island for the SAME sovereign as `shape_a_kessia_east`.
      shape_id: "shape_c_kessia_west",
      owner_id: "kessia",
      owner_namespace: "foreign_profile",
      owner_display_name: "Kessia",
      polygon: [
        [4300, 6000],
        [5200, 5900],
        [5400, 7000],
        [4500, 7400],
      ],
    },
    {
      shape_id: "shape_d_vetruska",
      owner_id: "vetruska",
      owner_namespace: "foreign_profile",
      owner_display_name: "Vetruska",
      polygon: [
        [7200, 1800],
        [9200, 2200],
        [9400, 4600],
        [7800, 5200],
        [7000, 3600],
      ],
    },
  ],
};

/** A map whose route names a theater the same response does not contain. */
const BROKEN_ROUTE_MAP = {
  ...SVG_MAP,
  routes: [
    ...SVG_MAP.routes,
    { from_theater_id: "capital", to_theater_id: "theater_that_does_not_exist", bidirectional: false },
  ],
};

function svgOf(container: HTMLElement): SVGSVGElement {
  const svg = container.querySelector("svg");
  if (svg === null) {
    throw new Error("no strategic-map SVG rendered");
  }
  return svg as unknown as SVGSVGElement;
}

function pointsOf(polygon: readonly (readonly number[])[]): string {
  return polygon.map(([x, y]) => `${x},${y}`).join(" ");
}

describe("StrategicMapScreen: SVG shapes and owner styling", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders one SVG on the authored 0..10,000 grid", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");
    expect(svgOf(container).getAttribute("viewBox")).toBe("0 0 10000 10000");
  });

  it("renders exactly one base polygon per projected shape, in authored vertex order", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const bases = container.querySelectorAll("[data-shape-base]");
    expect(bases).toHaveLength(SVG_MAP.shapes.length);

    for (const shape of SVG_MAP.shapes) {
      const element = container.querySelector(`[data-shape-base="${shape.shape_id}"]`);
      expect(element).not.toBeNull();
      // Joined, never sorted/rotated/normalized: the authored ring exactly as stored.
      expect(element?.getAttribute("points")).toBe(pointsOf(shape.polygon));
    }
  });

  it("renders a hatch overlay for every foreign shape and none for the player's", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const foreignShapes = SVG_MAP.shapes.filter((s) => s.owner_namespace === "foreign_profile");
    expect(container.querySelectorAll("[data-shape-hatch]")).toHaveLength(foreignShapes.length);
    expect(container.querySelector('[data-shape-hatch="shape_b_arken"]')).toBeNull();

    for (const shape of foreignShapes) {
      const overlay = container.querySelector(`[data-shape-hatch="${shape.shape_id}"]`);
      expect(overlay?.getAttribute("fill")).toMatch(/^url\(#mandate-map-hatch-\d+\)$/);
      // The overlay carries the SAME authored ring as its base polygon.
      expect(overlay?.getAttribute("points")).toBe(pointsOf(shape.polygon));
    }
  });

  it("distinguishes player from foreign territory on two channels: fill AND hatch", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const playerFill = container
      .querySelector('[data-shape-base="shape_b_arken"]')
      ?.getAttribute("fill");
    const foreignFill = container
      .querySelector('[data-shape-base="shape_a_kessia_east"]')
      ?.getAttribute("fill");

    expect(playerFill).toBeTruthy();
    expect(foreignFill).toBeTruthy();
    expect(playerFill).not.toBe(foreignFill);
    expect(container.querySelector('[data-shape-hatch="shape_b_arken"]')).toBeNull();
    expect(container.querySelector('[data-shape-hatch="shape_a_kessia_east"]')).not.toBeNull();
  });

  it("gives every shape of one sovereign exactly one style, and different sovereigns different ones", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const fillOf = (shapeId: string) =>
      container.querySelector(`[data-shape-base="${shapeId}"]`)?.getAttribute("fill");
    const hatchOf = (shapeId: string) =>
      container.querySelector(`[data-shape-hatch="${shapeId}"]`)?.getAttribute("fill");

    // Two islands, one sovereign -- identical fill AND identical hatch.
    expect(fillOf("shape_a_kessia_east")).toBe(fillOf("shape_c_kessia_west"));
    expect(hatchOf("shape_a_kessia_east")).toBe(hatchOf("shape_c_kessia_west"));

    // Two different foreign sovereigns -- distinguishable on both channels.
    expect(fillOf("shape_a_kessia_east")).not.toBe(fillOf("shape_d_vetruska"));
    expect(hatchOf("shape_a_kessia_east")).not.toBe(hatchOf("shape_d_vetruska"));
  });

  it("assigns identical owner styles when the response's collections arrive in a different order", async () => {
    const first = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");
    const before = SVG_MAP.shapes.map((shape) => ({
      shape_id: shape.shape_id,
      fill: first.container
        .querySelector(`[data-shape-base="${shape.shape_id}"]`)
        ?.getAttribute("fill"),
      hatch: first.container
        .querySelector(`[data-shape-hatch="${shape.shape_id}"]`)
        ?.getAttribute("fill"),
    }));
    first.unmount();

    const reordered = {
      ...SVG_MAP,
      theaters: [...SVG_MAP.theaters].reverse(),
      shapes: [...SVG_MAP.shapes].reverse(),
    };
    const second = renderScreen(reordered);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");
    const after = SVG_MAP.shapes.map((shape) => ({
      shape_id: shape.shape_id,
      fill: second.container
        .querySelector(`[data-shape-base="${shape.shape_id}"]`)
        ?.getAttribute("fill"),
      hatch: second.container
        .querySelector(`[data-shape-hatch="${shape.shape_id}"]`)
        ?.getAttribute("fill"),
    }));

    expect(after).toEqual(before);
  });
});

describe("StrategicMapScreen: SVG routes", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders exactly one line per projected route row, with endpoints at the authored centroids", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const lines = container.querySelectorAll("[data-route]");
    expect(lines).toHaveLength(SVG_MAP.routes.length);

    const centroids = new Map(
      SVG_MAP.theaters.map((t) => [t.theater_id, { x: t.centroid_x, y: t.centroid_y }]),
    );
    for (const route of SVG_MAP.routes) {
      const line = container.querySelector(
        `[data-route="${route.from_theater_id}->${route.to_theater_id}"]`,
      );
      expect(line).not.toBeNull();
      const from = centroids.get(route.from_theater_id);
      const to = centroids.get(route.to_theater_id);
      expect(line?.getAttribute("x1")).toBe(String(from?.x));
      expect(line?.getAttribute("y1")).toBe(String(from?.y));
      expect(line?.getAttribute("x2")).toBe(String(to?.x));
      expect(line?.getAttribute("y2")).toBe(String(to?.y));
    }
  });

  it("draws a reciprocal route once, with an arrow at each end", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    // The contract collapses the reciprocal pair to one row; the map draws one line, not two.
    expect(container.querySelectorAll('[data-route="capital->coast"]')).toHaveLength(1);
    expect(container.querySelectorAll('[data-route="coast->capital"]')).toHaveLength(0);

    const line = container.querySelector('[data-route="capital->coast"]');
    expect(line?.getAttribute("data-route-bidirectional")).toBe("true");
    expect(line?.getAttribute("marker-end")).toBe("url(#mandate-map-route-arrow-end)");
    expect(line?.getAttribute("marker-start")).toBe("url(#mandate-map-route-arrow-start)");
  });

  it("keeps a one-way route's authored direction and gives it a single end arrow", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    // Authored north_march -> kessia_south. The reverse is never emitted or inferred.
    const line = container.querySelector('[data-route="north_march->kessia_south"]');
    expect(line).not.toBeNull();
    expect(container.querySelector('[data-route="kessia_south->north_march"]')).toBeNull();

    const north = SVG_MAP.theaters.find((t) => t.theater_id === "north_march");
    const kessia = SVG_MAP.theaters.find((t) => t.theater_id === "kessia_south");
    expect(line?.getAttribute("x1")).toBe(String(north?.centroid_x));
    expect(line?.getAttribute("x2")).toBe(String(kessia?.centroid_x));

    expect(line?.getAttribute("data-route-bidirectional")).toBe("false");
    expect(line?.getAttribute("marker-end")).toBe("url(#mandate-map-route-arrow-end)");
    expect(line?.getAttribute("marker-start")).toBeNull();
  });

  it("refuses to draw a partial map when a route names a theater the response does not contain", async () => {
    const { container } = renderScreen(BROKEN_ROUTE_MAP);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/inconsistent/i);
    expect(alert.textContent).toMatch(/theater_that_does_not_exist/);

    // No partial map: no SVG, no theater list, nothing silently omitted.
    expect(container.querySelector("svg")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Theaters" })).not.toBeInTheDocument();
  });
});

describe("StrategicMapScreen: SVG nodes, capital marker and selection sync", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders one node per theater, at its own authored centroid, with land and coastal drawn differently", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const nodes = container.querySelectorAll("[data-theater-node]");
    expect(nodes).toHaveLength(SVG_MAP.theaters.length);

    for (const theater of SVG_MAP.theaters) {
      const node = container.querySelector(`[data-theater-node="${theater.theater_id}"]`);
      expect(node?.getAttribute("data-centroid-x")).toBe(String(theater.centroid_x));
      expect(node?.getAttribute("data-centroid-y")).toBe(String(theater.centroid_y));
    }

    // Kind is legible without colour: a coastal theater's marker carries a square glyph, a land
    // theater's a round one.
    expect(
      container.querySelector('[data-theater-node="coast"] [data-node-glyph]')?.getAttribute("data-node-glyph"),
    ).toBe("coastal");
    expect(
      container.querySelector('[data-theater-node="capital"] [data-node-glyph]')?.getAttribute("data-node-glyph"),
    ).toBe("land");
  });

  it("draws a map ground, a decorative grid, a frame and a compass -- and claims no geography", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    expect(container.querySelector("[data-map-sea]")).not.toBeNull();
    expect(container.querySelectorAll("[data-grid-line]").length).toBeGreaterThan(0);
    expect(container.querySelector('[data-map-frame="outer"]')).not.toBeNull();
    expect(container.querySelector('[data-map-frame="inset"]')).not.toBeNull();

    const compass = container.querySelector("[data-map-compass]");
    expect(compass).not.toBeNull();
    expect(compass?.textContent).toBe("N");
    // Decorative only: it takes no pointer input and sits inside the aria-hidden picture.
    expect(compass?.getAttribute("pointer-events")).toBe("none");
    expect(compass?.closest("svg")?.getAttribute("aria-hidden")).toBe("true");

    // The map states its own honesty, in real text outside the SVG.
    const caveat = screen.getByTestId("strategic-map-caveat");
    expect(caveat.closest("svg")).toBeNull();
    expect(caveat.textContent).toBe("Schematic — not to geographic scale");

    // No claim of geographic accuracy anywhere: no scale bar, no distances, no coordinates.
    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/\bkm\b|\bmiles\b|latitude|longitude|°/i);
  });

  it("draws the authored boundary as its own stroke over a separating halo", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    for (const shape of SVG_MAP.shapes) {
      const halo = container.querySelector(`[data-shape-halo="${shape.shape_id}"]`);
      const base = container.querySelector(`[data-shape-base="${shape.shape_id}"]`);
      // Same authored ring, three times over (halo, fill, hatch) -- never a smoothed or
      // regenerated one.
      expect(halo?.getAttribute("points")).toBe(pointsOf(shape.polygon));
      expect(halo?.getAttribute("fill")).toBe("none");
      expect(Number(halo?.getAttribute("stroke-width"))).toBeGreaterThan(
        Number(base?.getAttribute("stroke-width")),
      );
    }

    // Player and foreign boundaries are drawn in different inks, on top of the fill difference.
    const playerStroke = container
      .querySelector('[data-shape-base="shape_b_arken"]')
      ?.getAttribute("stroke");
    const foreignStroke = container
      .querySelector('[data-shape-base="shape_a_kessia_east"]')
      ?.getAttribute("stroke");
    expect(playerStroke).not.toBe(foreignStroke);
  });

  it("renders exactly one capital star, translated onto the capital theater's own centroid", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const markers = container.querySelectorAll("[data-capital-marker]");
    expect(markers).toHaveLength(1);
    const star = markers[0];
    expect(star?.getAttribute("data-capital-marker")).toBe(SVG_MAP.capital_theater_id);

    // A static five-point star (ten vertices), placed by translating to the authoritative
    // capital's centroid -- so the marker introduces no coordinate of its own.
    expect(star?.tagName.toLowerCase()).toBe("polygon");
    expect((star?.getAttribute("points") ?? "").trim().split(/\s+/)).toHaveLength(10);
    const capital = SVG_MAP.theaters.find((t) => t.is_capital);
    expect(star?.getAttribute("transform")).toBe(
      `translate(${capital?.centroid_x} ${capital?.centroid_y})`,
    );

    // Never the star alone: capital status is also stated in words, in the detail panel.
    fireEvent.click(screen.getByRole("button", { name: "Capital Theater — Land, Republic of Arken, capital" }));
    const detail = screen.getByRole("heading", { name: "Capital Theater" }).closest("section");
    expect(within(detail as HTMLElement).getByText("Capital")).toBeInTheDocument();
    expect(within(detail as HTMLElement).getByText("Yes")).toBeInTheDocument();
  });

  it("selects the matching list row when an SVG node is clicked", async () => {
    const { container } = renderScreen(SVG_MAP);
    const listButton = await screen.findByRole("button", {
      name: "Southern Kessia — Land, Kessia",
    });
    expect(listButton).toHaveAttribute("aria-pressed", "false");

    const node = container.querySelector('[data-theater-node="kessia_south"]');
    expect(node).not.toBeNull();
    fireEvent.click(node as Element);

    expect(listButton).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: "Southern Kessia" })).toBeInTheDocument();
  });

  it("selects the matching SVG node when a list row is clicked, and again when one is focused", async () => {
    const { container } = renderScreen(SVG_MAP);
    const clicked = await screen.findByRole("button", { name: "Southern Kessia — Land, Kessia" });

    fireEvent.click(clicked);
    expect(
      container.querySelector('[data-theater-node="kessia_south"]')?.getAttribute("data-selected"),
    ).toBe("true");
    expect(container.querySelector('[data-selection-marker="kessia_south"]')).not.toBeNull();

    // Keyboard traversal moves focus, and focus alone moves the map's selection -- so tabbing
    // through the list drives the picture without any pointer.
    const focused = screen.getByRole("button", { name: "Vetruskan Frontier — Land, Vetruska" });
    fireEvent.focus(focused);
    expect(
      container
        .querySelector('[data-theater-node="vetruska_frontier"]')
        ?.getAttribute("data-selected"),
    ).toBe("true");
    expect(
      container.querySelector('[data-theater-node="kessia_south"]')?.getAttribute("data-selected"),
    ).toBe("false");
    expect(container.querySelectorAll("[data-selection-marker]")).toHaveLength(1);
  });

  it("changes the selected node's own styling deterministically", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const node = () => container.querySelector('[data-theater-node="capital"]');
    const marker = () => container.querySelector('[data-node-marker="capital"]');
    const unselectedStroke = marker()?.getAttribute("stroke");
    const unselectedRadius = marker()?.getAttribute("r");

    fireEvent.click(node() as Element);

    expect(marker()?.getAttribute("stroke")).not.toBe(unselectedStroke);
    expect(marker()?.getAttribute("r")).not.toBe(unselectedRadius);
    expect(node()?.getAttribute("data-selected")).toBe("true");
  });

  it("gives every node a generous pointer target centred on the very same authored centroid", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    for (const theater of SVG_MAP.theaters) {
      const group = container.querySelector(`[data-theater-node="${theater.theater_id}"]`);
      // The whole marker group is translated to the authored centroid, so the invisible hit
      // circle at its local origin is centred on exactly that coordinate -- an easier click, not
      // a different position.
      expect(group?.getAttribute("transform")).toBe(
        `translate(${theater.centroid_x} ${theater.centroid_y})`,
      );
      const hit = group?.querySelector('circle[fill="transparent"]');
      expect(hit).not.toBeNull();
      const marker = container.querySelector(`[data-node-marker="${theater.theater_id}"]`);
      expect(Number(hit?.getAttribute("r"))).toBeGreaterThan(Number(marker?.getAttribute("r")));
    }
  });
});

describe("StrategicMapScreen: labels, legend and the accessibility split", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("labels every theater by its display name, positioned by its authored anchor", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    for (const theater of SVG_MAP.theaters) {
      const label = container.querySelector(`[data-theater-label="${theater.theater_id}"]`);
      expect(label?.textContent).toBe(theater.display_name);

      const expected = labelOffsetPosition(
        theater.centroid_x,
        theater.centroid_y,
        theater.label_anchor as Parameters<typeof labelOffsetPosition>[2],
      );
      expect(label?.getAttribute("x")).toBe(String(expected.x));
      expect(label?.getAttribute("y")).toBe(String(expected.y));
      expect(label?.getAttribute("text-anchor")).toBe(expected.textAnchor);
    }
  });

  it("pins every label-anchor case of the offset helper", () => {
    // North sits above the node, south below, east to its right, west to its left, and centre on
    // it -- with the text growing AWAY from the node in each case, never back across it.
    expect(labelOffsetPosition(1000, 2000, "n")).toEqual({
      x: 1000,
      y: 1670,
      textAnchor: "middle",
    });
    expect(labelOffsetPosition(1000, 2000, "s")).toEqual({
      x: 1000,
      y: 2330,
      textAnchor: "middle",
    });
    expect(labelOffsetPosition(1000, 2000, "e")).toEqual({
      x: 1330,
      y: 2000,
      textAnchor: "start",
    });
    expect(labelOffsetPosition(1000, 2000, "w")).toEqual({ x: 670, y: 2000, textAnchor: "end" });
    // "center" means no side preferred, NOT printed over the symbol: a label sitting exactly on
    // its node hid the marker, and on the capital hid the star (found in the Gate 9 preview pass),
    // so a centre label drops clear of the tallest symbol drawn at a node.
    expect(labelOffsetPosition(1000, 2000, "center")).toEqual({
      x: 1000,
      y: 2380,
      textAnchor: "middle",
    });
  });

  it("does not clip labels that their authored anchor pushes past the edge of the grid", async () => {
    // Found in the Gate 9 browser walkthrough, not here: an SVG viewport clips by default, so
    // "Arken Coast" (anchor w near x=1,200) and "Vetruskan Frontier" (anchor e near x=8,200)
    // rendered as "n Coast" and "Vetruskan F". jsdom computes no layout, so this pins the two
    // structural facts that let the browser paint them in full -- the grid-exact viewBox is kept,
    // and the viewport no longer clips -- with the screenshots as the visual evidence.
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const svg = svgOf(container);
    expect(svg.getAttribute("viewBox")).toBe("0 0 10000 10000");
    expect(svg.getAttribute("class") ?? "").toMatch(/\boverflow-visible\b/);

    // A west-anchored label near the left edge genuinely lands outside the grid: that is exactly
    // the case the clipping used to eat, so the fixture must really contain one.
    const westLabel = container.querySelector('[data-theater-label="coast"]');
    expect(westLabel?.getAttribute("text-anchor")).toBe("end");
    expect(Number(westLabel?.getAttribute("x"))).toBeLessThan(1000);
  });

  it("keeps the SVG out of the accessibility tree and out of keyboard traversal entirely", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const svg = svgOf(container);
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    expect(svg.getAttribute("focusable")).toBe("false");
    // Not one tab stop inside the picture: the list is the whole keyboard surface.
    expect(svg.querySelectorAll("[tabindex]")).toHaveLength(0);
    expect(svg.querySelectorAll("button, a, input, select, textarea")).toHaveLength(0);
  });

  it("states the map's vocabulary in a real, visible, non-SVG legend", async () => {
    renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    const legend = screen.getByTestId("strategic-map-legend");
    expect(legend.tagName.toLowerCase()).not.toBe("svg");
    expect(legend.closest("svg")).toBeNull();
    expect(legend.getAttribute("aria-hidden")).toBeNull();

    // Every symbol the map draws is explained in WORDS, not merely shown as a colour swatch.
    const text = legend.textContent ?? "";
    expect(text).toMatch(/Your territory/);
    expect(text).toMatch(/Foreign territory/);
    expect(text).toMatch(/Hatching/);
    expect(text).toMatch(/One-way route/);
    expect(text).toMatch(/Two-way route/);
    expect(text).toMatch(/arrowhead/i);
    expect(text).toMatch(/Theater marker/);
    expect(text).toMatch(/Capital/);
    expect(text).toMatch(/star/i);
    expect(text).toMatch(/Selected theater/);
    expect(text).toMatch(/Grid and compass/);
    // ...and the glyphs it uses are marked decorative, so a screen reader hears the words only.
    for (const glyph of legend.querySelectorAll("span")) {
      expect(glyph.getAttribute("aria-hidden")).toBe("true");
    }
  });

  it("renders map labels as display names in atlas typography, never as raw ids", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");

    for (const theater of SVG_MAP.theaters) {
      const label = container.querySelector(`[data-theater-label="${theater.theater_id}"]`);
      // The DISPLAY name is the text; uppercasing is styling, so the underlying string -- and
      // therefore what any reader copies out -- stays exactly what the server sent.
      expect(label?.textContent).toBe(theater.display_name);
      expect(label?.textContent).not.toBe(theater.theater_id);
      const style = label?.getAttribute("style") ?? "";
      expect(style).toMatch(/text-transform:\s*uppercase/);
      expect(label?.getAttribute("paint-order")).toBe("stroke");
      // A halo behind the glyphs is what keeps a name readable over hatching or a route line.
      expect(Number(label?.getAttribute("stroke-width"))).toBeGreaterThan(0);
    }

    const svgText = [...container.querySelectorAll("svg text")].map((t) => t.textContent).join(" ");
    expect(svgText).not.toMatch(/player_country|foreign_profile/);
  });

  it("adds no military order, movement, unit, deployment or combat affordance", async () => {
    const { container } = renderScreen(SVG_MAP);
    await screen.findByText("Capital Theater — Land, Republic of Arken, capital");
    fireEvent.click(container.querySelector('[data-theater-node="capital"]') as Element);

    const forbidden = /\b(order|deploy|deployment|move|movement|unit|troop|combat|attack)\b/i;
    for (const control of screen.getAllByRole("button")) {
      expect(control.textContent ?? "").not.toMatch(forbidden);
      expect(control.getAttribute("aria-label") ?? "").not.toMatch(forbidden);
    }
    expect(screen.queryAllByRole("menuitem")).toHaveLength(0);
    expect(container.querySelectorAll("form, input, select, textarea")).toHaveLength(0);
  });

  it("keeps the complete textual route information available in the narrow, SVG-free layout", async () => {
    const { container } = renderScreen(SVG_MAP);
    const listButton = await screen.findByRole("button", {
      name: "Northern March — Land, Republic of Arken",
    });
    fireEvent.click(listButton);

    // The panel that the <900px breakpoint hides is the one holding the SVG and its legend...
    const visualPanel = screen.getByTestId("strategic-map-visual");
    expect(visualPanel.className).toMatch(/\bhidden\b/);
    expect(svgOf(container).closest('[data-testid="strategic-map-visual"]')).toBe(visualPanel);
    expect(screen.getByTestId("strategic-map-legend").closest('[data-testid="strategic-map-visual"]')).toBe(
      visualPanel,
    );

    // ...and everything directional survives it, in words, in the always-visible column.
    const detail = screen.getByRole("heading", { name: "Northern March" }).closest("section");
    expect(detail?.className ?? "").not.toMatch(/\bhidden\b/);
    expect(within(detail as HTMLElement).getByRole("heading", { name: "Routes out" })).toBeInTheDocument();
    expect(within(detail as HTMLElement).getByRole("heading", { name: "Routes in" })).toBeInTheDocument();
    expect(within(detail as HTMLElement).getByText("Southern Kessia")).toBeInTheDocument();
    // "Capital Theater" is legitimately in BOTH lists here (Northern March routes out to it and
    // in from it), so it is expected more than once.
    expect(within(detail as HTMLElement).getAllByText("Capital Theater").length).toBe(2);
    expect(within(detail as HTMLElement).getByText("Land")).toBeInTheDocument();
    expect(within(detail as HTMLElement).getByText("Republic of Arken")).toBeInTheDocument();
  });
});
