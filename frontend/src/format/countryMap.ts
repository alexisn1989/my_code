/**
 * Gate 4A3 M-1: the geometry of the illustrated country map. Pure functions, here because display
 * arithmetic lives in `src/format/` only (`format-boundary.test.ts`).
 *
 * WHAT IS DATA AND WHAT IS ILLUSTRATION:
 * - The country's outline, its neighbours, its rivers and the capital's position are the game's own
 *   strategic-map geography (`GET /api/game/map/strategic`), only scaled and styled.
 * - One NATIONAL value colours the whole country uniformly (`landWash`): the same rule as the
 *   national tint (`tintMixPercent`), never a per-region value. No region is coloured on its own.
 * - Hills, trees, the compass and the whole capital plan (its wall, streets, river, bridges, square
 *   and houses) are decoration, placed by fixed rules so the picture is stable. None of it is a claim
 *   about the simulated country.
 * - The seven institutions stand on plots in that plan: navigation, not locations of anything
 *   simulated.
 */

import type { StrategicMapProjection } from "../api/client";
import { tintMixPercent } from "./format";

export interface Point {
  x: number;
  y: number;
}

export interface TerrainMark extends Point {
  kind: "hill" | "tree";
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface CityPlan {
  box: Box;
  wall: string;
  towers: Point[];
  avenues: { x1: number; y1: number; x2: number; y2: number }[];
  lanes: { x1: number; y1: number; x2: number; y2: number }[];
  river: string;
  riverWidth: number;
  bridges: { x: number; y: number; w: number; h: number }[];
  square: Point & { r: number };
  houses: { x: number; y: number; w: number; h: number }[];
  /** Each institution's plot: where its building stands. */
  plots: Point[];
}

export interface CountryMapGeometry {
  /** The SVG viewBox: 1000 wide; 620 tall on wide maps, 1380 tall on narrow ones. */
  width: number;
  height: number;
  tall: boolean;
  countryPaths: string[];
  neighbourPaths: string[];
  riverPaths: string[];
  neighbourLabels: { text: string; x: number; y: number }[];
  terrain: TerrainMark[];
  capital: Point;
  leaderEnd: Point;
  compass: Point;
  city: CityPlan;
  /** Where each institution's building sits, as a percentage of the map's width and height. */
  pins: { left: number; top: number }[];
}

/** The decorative seeds. Changing them changes only where hills, trees and houses are drawn. */
const TERRAIN_SEED = 7;
const HOUSE_SEED = 11;
const TERRAIN_MARKS = 46;
const TERRAIN_ATTEMPTS = 900;

function lcg(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function inside(point: [number, number], polygon: readonly (readonly number[])[]): boolean {
  let within = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const [xi, yi] = polygon[i] as [number, number];
    const [xj, yj] = polygon[j] as [number, number];
    if (yi > point[1] !== yj > point[1] && point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi) {
      within = !within;
    }
  }
  return within;
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

/** The illustrated capital: a walled town plan inside `box`, with institutions on `plotFractions`. */
function cityPlan(box: Box, plotFractions: readonly (readonly [number, number])[], tall: boolean): CityPlan {
  const at = (u: number, v: number): Point => ({ x: round1(box.x + u * box.w), y: round1(box.y + v * box.h) });
  // An irregular eight-sided wall, a little inside the box.
  const corners: [number, number][] = [
    [0.18, 0.03], [0.82, 0.03], [0.97, 0.18], [0.97, 0.8], [0.84, 0.97], [0.16, 0.97], [0.03, 0.82], [0.03, 0.2],
  ];
  const wallPoints = corners.map(([u, v]) => at(u, v));
  const wall = `M${wallPoints.map((p) => `${p.x} ${p.y}`).join("L")}Z`;
  const riverV = 0.73;
  const river = (() => {
    const a = at(-0.02, riverV + 0.04);
    const c1 = at(0.3, riverV - 0.07);
    const c2 = at(0.62, riverV + 0.1);
    const b = at(1.02, riverV - 0.02);
    return `M${a.x} ${a.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${b.x} ${b.y}`;
  })();
  const riverWidth = round1(box.h * (tall ? 0.05 : 0.045));
  const bridgeW = round1(box.w * 0.07);
  const bridgeH = round1(riverWidth * 2.2);
  const bridges = [at(0.38, riverV + 0.005), at(0.62, riverV + 0.02)].map((p) => ({
    x: round1(p.x - bridgeW / 2),
    y: round1(p.y - bridgeH / 2),
    w: bridgeW,
    h: bridgeH,
  }));
  const square = { ...at(0.5, 0.43), r: round1(Math.min(box.w, box.h) * 0.07) };
  const line = (u1: number, v1: number, u2: number, v2: number) => {
    const p = at(u1, v1);
    const q = at(u2, v2);
    return { x1: p.x, y1: p.y, x2: q.x, y2: q.y };
  };
  const avenues = [line(0.05, 0.43, 0.95, 0.43), line(0.5, 0.06, 0.5, 0.95), line(0.12, 0.2, 0.88, 0.66)];
  const lanes = [
    line(0.08, 0.22, 0.92, 0.22), line(0.08, 0.6, 0.92, 0.6), line(0.08, 0.9, 0.92, 0.9),
    line(0.25, 0.06, 0.25, 0.95), line(0.75, 0.06, 0.75, 0.95), line(0.12, 0.66, 0.88, 0.2),
  ];
  const plots = plotFractions.map(([u, v]) => at(u, v));
  // Houses: small blocks along the plan, never on a plot, the square or the river.
  const random = lcg(HOUSE_SEED);
  const houses: CityPlan["houses"] = [];
  const keepClear = Math.min(box.w, box.h) * (tall ? 0.13 : 0.11);
  for (let row = 0.1; row < 0.95; row += 0.075) {
    for (let col = 0.1; col < 0.93; col += 0.06) {
      const u = col + (random() - 0.5) * 0.02;
      const v = row + (random() - 0.5) * 0.02;
      if (Math.abs(v - riverV) < 0.07 || Math.abs(u - 0.5) < 0.03 || Math.abs(v - 0.43) < 0.03) continue;
      const p = at(u, v);
      if (plots.some((plot) => Math.hypot(plot.x - p.x, plot.y - p.y) < keepClear)) continue;
      if (Math.hypot(square.x - p.x, square.y - p.y) < square.r + 6) continue;
      if (!inside([u, v], corners)) continue;
      if (random() < 0.22) continue;
      houses.push({
        x: p.x,
        y: p.y,
        w: round1(box.w * (0.025 + random() * 0.02)),
        h: round1(box.h * (0.018 + random() * 0.014)),
      });
    }
  }
  return {
    box,
    wall,
    towers: wallPoints,
    avenues,
    lanes,
    river,
    riverWidth,
    bridges,
    square,
    houses,
    plots,
  };
}

/**
 * Lay out the player's country, its neighbours and the illustrated capital.
 *
 * `tall` picks the phone layout: the country above and a large capital plan below. `plots` are the
 * institutions' positions on the plan (`places.ts`), for the chosen layout.
 */
export function countryMapGeometry(
  map: StrategicMapProjection,
  tall: boolean,
  plots: readonly (readonly [number, number])[],
): CountryMapGeometry {
  const capitalTheater = map.theaters.find((theater) => theater.theater_id === map.capital_theater_id);
  if (capitalTheater === undefined) throw new Error("the strategic map has no capital theater");
  const ownerId = capitalTheater.owner_id;
  const own = map.shapes.filter((shape) => shape.owner_id === ownerId);
  const width = 1000;
  const height = tall ? 1380 : 620;
  // On tall maps the title plate sits above the picture, so the country is centred and the
  // capital plan follows close beneath it.
  const region = tall ? { x: 40, y: 24, w: 920, h: 516 } : { x: 30, y: 30, w: 540, h: 560 };
  const points = own.flatMap((shape) => shape.polygon as unknown as [number, number][]);
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const pad = 900;
  const spanX = maxX - minX + 2 * pad;
  const spanY = maxY - minY + 2 * pad;
  const scale = Math.min(region.w / spanX, region.h / spanY);
  const offsetX = region.x + (region.w - spanX * scale) / 2;
  const offsetY = region.y + (region.h - spanY * scale) / 2;
  const to = (x: number, y: number): Point => ({
    x: round1(offsetX + (x - minX + pad) * scale),
    y: round1(offsetY + (y - minY + pad) * scale),
  });
  const path = (polygon: readonly (readonly number[])[]): string =>
    `M${polygon.map((p) => { const q = to(p[0] as number, p[1] as number); return `${q.x} ${q.y}`; }).join("L")}Z`;

  const capital = to(capitalTheater.centroid_x, capitalTheater.centroid_y);
  const box: Box = tall ? { x: 40, y: 568, w: 920, h: 790 } : { x: 590, y: 24, w: 390, h: 572 };
  const city = cityPlan(box, plots, tall);
  // The dashed line from the capital's mark to the nearest side of the plan.
  const leaderEnd = tall
    ? { x: round1(Math.min(Math.max(capital.x, box.x + 40), box.x + box.w - 40)), y: box.y }
    : { x: box.x, y: round1(Math.min(Math.max(capital.y, box.y + 40), box.y + box.h - 40)) };

  const random = lcg(TERRAIN_SEED);
  const terrain: TerrainMark[] = [];
  for (let attempt = 0; attempt < TERRAIN_ATTEMPTS && terrain.length < TERRAIN_MARKS; attempt += 1) {
    const x = minX + random() * (maxX - minX);
    const y = minY + random() * (maxY - minY);
    const kind = random() < 0.5 ? "hill" : "tree";
    if (!own.some((shape) => inside([x, y], shape.polygon))) continue;
    const at = to(x, y);
    if (Math.hypot(at.x - capital.x, at.y - capital.y) < 40) continue;
    terrain.push({ kind, ...at });
  }

  const labelled = new Map<string, { text: string; x: number; y: number }>();
  for (const theater of map.theaters) {
    if (theater.owner_id === ownerId || labelled.has(theater.owner_id)) continue;
    const at = to(theater.centroid_x, theater.centroid_y);
    const clear = tall ? at.x < width && at.y < region.y + region.h : at.x < box.x - 30;
    if (at.x > 0 && at.y > 0 && clear) {
      labelled.set(theater.owner_id, { text: theater.owner_display_name.toUpperCase(), x: at.x, y: at.y });
    }
  }

  const pins = city.plots.map((plot) => ({
    left: Math.round((plot.x / width) * 10000) / 100,
    top: Math.round((plot.y / height) * 10000) / 100,
  }));

  return {
    width,
    height,
    tall,
    countryPaths: own.map((shape) => path(shape.polygon)),
    neighbourPaths: map.shapes.filter((shape) => shape.owner_id !== ownerId).map((shape) => path(shape.polygon)),
    riverPaths: map.rivers.map(
      (river) => `M${river.polyline.map((p) => { const q = to(p[0] as number, p[1] as number); return `${q.x} ${q.y}`; }).join("L")}`,
    ),
    neighbourLabels: [...labelled.values()],
    terrain,
    capital,
    leaderEnd,
    compass: tall ? { x: 90, y: 500 } : { x: 70, y: 545 },
    city,
    pins,
  };
}

/** The ONE national wash for the whole country: the national tint's own mix percentage, applied
 * uniformly, lighter on the parchment land (half the mix) so the map stays readable. */
export function landWash(valueBps: number): string {
  return `color-mix(in oklab, var(--color-gold-600) ${Math.round(tintMixPercent(valueBps) * 50) / 100}%, var(--color-parchment-200))`;
}

/** The map's illustration notice, beside the national tint caption. */
export function mapIllustrationNote(): string {
  return "Illustration: the capital's streets and buildings are ways in to the institutions, and no regional figures are simulated.";
}

/** Gate 4A3 M-1: whether a horizontally scrolling row has more to show on each side (1 px slack for
 * sub-pixel layouts), and how far one arrow press moves it: most of a row's visible width. */
export function scrollRoom(scrollLeft: number, clientWidth: number, scrollWidth: number): { left: boolean; right: boolean } {
  return { left: scrollLeft > 1, right: scrollLeft + clientWidth < scrollWidth - 1 };
}

export function scrollStep(clientWidth: number): number {
  return Math.round(clientWidth * 0.8);
}

/** The row's `scrollLeft` that brings one of its items wholly into view, moving as little as possible
 * (none when it already shows). Rects are viewport coordinates, as `getBoundingClientRect` gives them.
 * Used instead of `scrollIntoView`, which in Chromium also moves the Tab starting point to the item. */
export function revealScrollLeft(
  scrollLeft: number,
  clientWidth: number,
  rowLeft: number,
  itemLeft: number,
  itemRight: number,
): number {
  const start = itemLeft - rowLeft + scrollLeft;
  const end = itemRight - rowLeft + scrollLeft;
  if (start < scrollLeft) return start;
  if (end > scrollLeft + clientWidth) return end - clientWidth;
  return scrollLeft;
}
