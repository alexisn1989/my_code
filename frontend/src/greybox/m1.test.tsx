/**
 * Gate 4A3 M-1: the map dashboard, as the player meets it.
 *
 * - every pin on the map has a twin in the Places list, with the same name and destination;
 * - both ask the shell to move focus to the destination's heading;
 * - the title plate keeps the national tint's contract, and one wash covers the whole country;
 * - with no map yet, the plate, caption and Places list still stand;
 * - the Dashboard is compact: the stakes stated once, the summaries folded, alerts only when present.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DashboardProjection, StrategicMapProjection } from "../api/client";
import { SessionProvider, useSession } from "../state/SessionContext";
import { OBJECTIVE_FIXTURE } from "../test/objectiveFixture";
import { CountryMap, PlacesList } from "./map/CountryMap";
import { PLACES, placeAccessibleName } from "./map/places";
import { DashboardScreen } from "./screens/DashboardScreen";

function card(label: string, headline: string, detail_screen: string) {
  return { label, headline, delta_text: null, direction: "unchanged", tone: "neutral", detail_screen };
}

const DASHBOARD = {
  revision: "1.1",
  campaign_id: "campaign-1",
  turn: 1,
  country_name: "Kingdom of Testland",
  government_form: "Hereditary monarchy, unlimited decree authority",
  next_election_label: "None scheduled",
  concerns: {
    money: card("Money", "100,000,000.00", "economy"),
    legitimacy: card("Legitimacy", "61.25%", "government"),
    legislature: card("Legislature", "2 parties, 100 seats", "legislature"),
    constitution: card("Constitution", "Supermajority", "constitution"),
    survival: card("Survival", "Coup risk 4.00%", "government"),
  },
  political_capital: { current: 500, capacity: 1000, committed_this_turn: 0, display: "500 / 1,000" },
  alerts: [] as unknown[],
  goal: { headline: "Nothing is pressing.", detail: null },
  objective: OBJECTIVE_FIXTURE,
  map: { presentation_only: true, tint_metric_label: "Legitimacy", tint_value_bps: 6125, note: "" },
  terminal: null,
} as unknown as DashboardProjection;

const MAP = {
  map_id: "test",
  capital_theater_id: "home_capital",
  shapes: [
    { shape_id: "home", owner_id: "home", owner_namespace: "country", owner_display_name: "Kingdom of Testland", polygon: [[1000, 1000], [4000, 1000], [4000, 5000], [1000, 5000]] },
    { shape_id: "home_isle", owner_id: "home", owner_namespace: "country", owner_display_name: "Kingdom of Testland", polygon: [[300, 300], [800, 300], [800, 800], [300, 800]] },
    { shape_id: "next", owner_id: "next", owner_namespace: "country", owner_display_name: "Next Door", polygon: [[4000, 1000], [7000, 1000], [7000, 5000], [4000, 5000]] },
  ],
  theaters: [
    { theater_id: "home_capital", display_name: "Capital", owner_id: "home", owner_namespace: "country", owner_display_name: "Kingdom of Testland", is_capital: true, is_player_owned: true, kind: "core", centroid_x: 2500, centroid_y: 3000, label_anchor: "middle", incoming_theater_ids: [], outgoing_theater_ids: [] },
  ],
  rivers: [],
  routes: [],
} as unknown as StrategicMapProjection;

const NAMES = PLACES.map(placeAccessibleName).sort();

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

let dashboardBody: unknown = DASHBOARD;

beforeEach(() => {
  dashboardBody = DASHBOARD;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/game/state")) return json(dashboardBody);
      if (url.includes("/api/game/map/strategic")) return json(MAP);
      return json({ detail: "not in this test" }, 404);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function SetRevision({ children }: { children: ReactNode }) {
  const { setCampaignView, revision } = useSession();
  useEffect(() => {
    if (revision === null) setCampaignView("1.1", "campaign-1");
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

describe("the country map and its Places twin", () => {
  it("gives every pin a Places twin with the same name, and both open the same screen with focus", () => {
    const navigate = vi.fn();
    render(
      <>
        <CountryMap dashboard={DASHBOARD} map={MAP} navigate={navigate} />
        <PlacesList navigate={navigate} />
      </>,
    );
    const pins = [...document.querySelectorAll<HTMLButtonElement>("[data-map-pin]")];
    const list = within(screen.getByTestId("places-list")).getAllByRole("button");
    expect(pins.map((b) => b.getAttribute("aria-label")).sort()).toEqual(NAMES);
    expect(list.map((b) => b.getAttribute("aria-label")).sort()).toEqual(NAMES);
    for (const place of PLACES) {
      const name = placeAccessibleName(place);
      fireEvent.click(pins.find((b) => b.getAttribute("aria-label") === name)!);
      expect(navigate).toHaveBeenLastCalledWith(place.screen, { focusHeading: true });
      fireEvent.click(list.find((b) => b.getAttribute("aria-label") === name)!);
      expect(navigate).toHaveBeenLastCalledWith(place.screen, { focusHeading: true });
    }
    expect(navigate).toHaveBeenCalledTimes(14);
  });

  it("keeps the national tint's contract on the title plate, and washes the whole country alike", () => {
    render(<CountryMap dashboard={DASHBOARD} map={MAP} navigate={vi.fn()} />);
    const plate = screen.getByTestId("national-tint");
    expect(plate).toHaveAttribute("role", "img");
    expect(plate).toHaveAttribute("data-tint-bps", "6125");
    expect(plate).toHaveAttribute("aria-label", "Kingdom of Testland: national tint by legitimacy, 61.25%.");
    expect(plate.getAttribute("style")).toMatch(/var\(--color-gold-600\) [\d.]+%/);
    expect(plate.textContent).toBe("Kingdom of Testland");
    const washes = [...document.querySelectorAll<SVGPathElement>("[data-national-wash]")];
    expect(washes).toHaveLength(2);
    expect(new Set(washes.map((w) => w.style.fill)).size).toBe(1);
    expect(screen.getByText(/Illustration: the capital's streets and buildings/)).toBeInTheDocument();
  });

  it("still shows the plate and caption while the map is not available", () => {
    render(<CountryMap dashboard={DASHBOARD} map={null} navigate={vi.fn()} />);
    expect(screen.getByTestId("national-tint")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-map-pin]")).toHaveLength(0);
    expect(screen.getByText(/The colour shows national legitimacy/)).toBeInTheDocument();
  });
});

describe("the compact Dashboard", () => {
  it("states the stakes once, folds the summaries, and omits an empty alerts panel", async () => {
    withCampaign(<DashboardScreen navigate={vi.fn()} />);
    await screen.findByTestId("country-map");
    expect(screen.getAllByTestId("win-and-loss")).toHaveLength(1);
    expect(within(screen.getByTestId("objective-card")).getByTestId("win-and-loss")).toBeInTheDocument();
    const summaries = screen.getByTestId("national-summaries");
    expect(summaries.tagName).toBe("DETAILS");
    expect(summaries).not.toHaveAttribute("open");
    expect(within(summaries).getByTestId("concern-cards")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Alerts" })).toBeNull();
    // The objective's conditions are folded too, and still there.
    const details = screen.getByTestId("objective-details");
    expect(details).not.toHaveAttribute("open");
    expect(within(details).getByTestId("objective-condition-words")).toBeInTheDocument();
  });

  it("shows the alerts panel when there is an alert", async () => {
    dashboardBody = {
      ...DASHBOARD,
      alerts: [{ id: "a1", severity: "warning", headline: "The treasury is running down.", detail: null }],
    };
    withCampaign(<DashboardScreen navigate={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Alerts" })).toBeInTheDocument();
    expect(screen.getByText("The treasury is running down.")).toBeInTheDocument();
  });
});
