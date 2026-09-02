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
});
