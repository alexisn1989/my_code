/**
 * Gate 4A3 M-1: the map's geometry and its place table, checked as rules, not pictures.
 */

import { describe, expect, it } from "vitest";

import type { StrategicMapProjection } from "../api/client";
import { PLACES } from "../greybox/map/places";
import { SCREENS } from "../greybox/registry";
import { countryMapGeometry, landWash, mapIllustrationNote, revealScrollLeft, scrollRoom, scrollStep } from "./countryMap";
import { tintMixPercent } from "./format";

/** A small synthetic map: a square country with its capital, a neighbour, a river. */
const MAP = {
  map_id: "test",
  capital_theater_id: "home_capital",
  shapes: [
    { shape_id: "home", owner_id: "home", owner_namespace: "country", owner_display_name: "Home", polygon: [[1000, 1000], [4000, 1000], [4000, 5000], [1000, 5000]] },
    { shape_id: "next", owner_id: "next", owner_namespace: "country", owner_display_name: "Next Door", polygon: [[4000, 1000], [7000, 1000], [7000, 5000], [4000, 5000]] },
  ],
  theaters: [
    { theater_id: "home_capital", display_name: "Home Capital", owner_id: "home", owner_namespace: "country", owner_display_name: "Home", is_capital: true, is_player_owned: true, kind: "core", centroid_x: 2500, centroid_y: 3000, label_anchor: "middle", incoming_theater_ids: [], outgoing_theater_ids: [] },
    { theater_id: "next_plain", display_name: "Next Plain", owner_id: "next", owner_namespace: "country", owner_display_name: "Next Door", is_capital: false, is_player_owned: false, kind: "core", centroid_x: 5500, centroid_y: 3000, label_anchor: "middle", incoming_theater_ids: [], outgoing_theater_ids: [] },
  ],
  rivers: [{ river_id: "r", display_name: "River", polyline: [[1500, 1200], [2000, 4800]] }],
  routes: [],
} as unknown as StrategicMapProjection;

function minimumGapPx(tall: boolean, widthPx: number): number {
  const plots = PLACES.map((place) => (tall ? place.plot.phone : place.plot.wide));
  const g = countryMapGeometry(MAP, tall, plots);
  const heightPx = (widthPx * g.height) / g.width;
  let minimum = Infinity;
  for (let i = 0; i < g.pins.length; i += 1) {
    for (let j = i + 1; j < g.pins.length; j += 1) {
      const a = g.pins[i]!;
      const b = g.pins[j]!;
      const dx = ((a.left - b.left) / 100) * widthPx;
      const dy = ((a.top - b.top) / 100) * heightPx;
      minimum = Math.min(minimum, Math.hypot(dx, dy));
    }
  }
  return minimum;
}

describe("the places", () => {
  it("are seven, uniquely named, each leading to an existing screen under that screen's nav name", () => {
    expect(PLACES).toHaveLength(7);
    expect(new Set(PLACES.map((p) => p.name)).size).toBe(7);
    expect(new Set(PLACES.map((p) => p.number))).toEqual(new Set([1, 2, 3, 4, 5, 6, 7]));
    for (const place of PLACES) {
      const screen = SCREENS.find((entry) => entry.id === place.screen);
      expect(screen, place.name).toBeDefined();
      expect(place.opens, place.name).toBe(screen!.label);
    }
  });
});

describe("the map geometry", () => {
  it("is deterministic", () => {
    const plots = PLACES.map((p) => p.plot.wide);
    expect(countryMapGeometry(MAP, false, plots)).toEqual(countryMapGeometry(MAP, false, plots));
  });

  it("puts every building on the capital plan, inside the picture", () => {
    for (const tall of [false, true]) {
      const g = countryMapGeometry(MAP, tall, PLACES.map((p) => (tall ? p.plot.phone : p.plot.wide)));
      expect(g.pins).toHaveLength(7);
      const { box } = g.city;
      for (const plot of g.city.plots) {
        expect(plot.x).toBeGreaterThan(box.x);
        expect(plot.x).toBeLessThan(box.x + box.w);
        expect(plot.y).toBeGreaterThan(box.y);
        expect(plot.y).toBeLessThan(box.y + box.h);
      }
      for (const pin of g.pins) {
        expect(pin.left).toBeGreaterThan(0);
        expect(pin.left).toBeLessThan(100);
        expect(pin.top).toBeGreaterThan(0);
        expect(pin.top).toBeLessThan(100);
      }
    }
  });

  it("keeps 44 px buildings apart at the smallest map each layout is drawn at", () => {
    // Phone layout: a 320 px screen leaves about 254 px for the map. Wide: drawn from 760 px up.
    expect(minimumGapPx(true, 254)).toBeGreaterThanOrEqual(52);
    expect(minimumGapPx(false, 760)).toBeGreaterThanOrEqual(80);
  });

  it("never draws a house on an institution's plot", () => {
    for (const tall of [false, true]) {
      const g = countryMapGeometry(MAP, tall, PLACES.map((p) => (tall ? p.plot.phone : p.plot.wide)));
      expect(g.city.houses.length).toBeGreaterThan(10);
      for (const house of g.city.houses) {
        for (const plot of g.city.plots) {
          expect(Math.hypot(house.x - plot.x, house.y - plot.y)).toBeGreaterThan(30);
        }
      }
    }
  });

  it("labels only the neighbours, and never under the capital plan", () => {
    const near = {
      ...MAP,
      theaters: MAP.theaters.map((t) => (t.theater_id === "next_plain" ? { ...t, centroid_x: 4200 } : t)),
    } as StrategicMapProjection;
    const shown = countryMapGeometry(near, false, PLACES.map((p) => p.plot.wide));
    expect(shown.neighbourLabels.map((l) => l.text)).toEqual(["NEXT DOOR"]);
    expect(shown.countryPaths).toHaveLength(1);
    expect(shown.neighbourPaths).toHaveLength(1);
    // A neighbour whose label point would fall under the capital plan is not labelled there.
    const hidden = countryMapGeometry(MAP, false, PLACES.map((p) => p.plot.wide));
    expect(hidden.neighbourLabels).toEqual([]);
  });
});

describe("the one national wash", () => {
  it("follows the national tint's own mix, at half strength on the land", () => {
    for (const bps of [0, 6000, 10_000]) {
      expect(landWash(bps)).toBe(
        `color-mix(in oklab, var(--color-gold-600) ${Math.round(tintMixPercent(bps) * 50) / 100}%, var(--color-parchment-200))`,
      );
    }
    expect(landWash(6000)).not.toBe(landWash(6100));
  });

  it("says the picture is an illustration and simulates no regions", () => {
    expect(mapIllustrationNote()).toMatch(/^Illustration:/);
    expect(mapIllustrationNote()).toContain("no regional figures are simulated");
  });
});

describe("the phone navigation row's scroll affordances", () => {
  it("say which sides have more to show, with a pixel of slack", () => {
    expect(scrollRoom(0, 300, 300)).toEqual({ left: false, right: false });
    expect(scrollRoom(0, 300, 900)).toEqual({ left: false, right: true });
    expect(scrollRoom(300, 300, 900)).toEqual({ left: true, right: true });
    expect(scrollRoom(600, 300, 900)).toEqual({ left: true, right: false });
    expect(scrollRoom(599.5, 300, 900)).toEqual({ left: true, right: false });
  });

  it("move most of a row's visible width per press", () => {
    expect(scrollStep(300)).toBe(240);
  });

  it("reveal the current button by moving the row as little as possible", () => {
    // Row at x=16, 300 wide, scrolled 0. A button wholly in view: nothing moves.
    expect(revealScrollLeft(0, 300, 16, 40, 120)).toBe(0);
    // Off the right edge (content 400..480): scroll so its right edge meets the row's.
    expect(revealScrollLeft(0, 300, 16, 416, 496)).toBe(180);
    // Off the left edge while scrolled 200 (content 50..130): scroll to its left edge.
    expect(revealScrollLeft(200, 300, 16, -134, -54)).toBe(50);
  });
});
