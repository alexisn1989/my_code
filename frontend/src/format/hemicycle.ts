/**
 * Gate 4A3 M-2 — the seat diagram's geometry, as pure arithmetic (the format boundary keeps it
 * here). Ported from the approved M-V mockup's `seatLayout`:
 *
 * - rows: `round(sqrt(n / 4))`, clamped to 3..9, at radii from 0.42 to 1 of the outer radius;
 * - seats per row in proportion to each row's radius (the remainder goes to the outer rows first);
 * - seats ordered left to right by angle, inner row first at equal angles, so consecutive seats of a
 *   bloc form a wedge;
 * - the dot's radius is 0.42 of the smaller of the closest spacing along a row and the gap between
 *   rows, so neighbouring dots never touch.
 *
 * Coordinates are in a fixed drawing space (`HEMICYCLE_VIEW`); a screen converts to pixels with the
 * width it actually draws at (`seatDiameterPx`).
 */

/** The drawing space: centre (360, 360), outer radius 330. */
export const HEMICYCLE_VIEW = { width: 720, height: 380, cx: 360, cy: 360, radius: 330 } as const;

/** Below this rendered diameter a seat is too small to read, and the card shows bars instead. */
export const MIN_SEAT_DIAMETER_PX = 6;

export interface SeatPoint {
  x: number;
  y: number;
}

export interface HemicycleLayout {
  seats: SeatPoint[];
  /** The dot radius, in drawing units. */
  dotRadius: number;
}

export function hemicycleLayout(seatCount: number): HemicycleLayout {
  if (seatCount <= 0) return { seats: [], dotRadius: 0 };
  const rows = Math.max(3, Math.min(9, Math.round(Math.sqrt(seatCount / 4))));
  const inner = 0.42;
  const radii = Array.from({ length: rows }, (_, i) => inner + ((1 - inner) * i) / (rows - 1));
  const radiusSum = radii.reduce((a, b) => a + b, 0);
  const counts = radii.map((r) => Math.floor((seatCount * r) / radiusSum));
  let remainder = seatCount - counts.reduce((a, b) => a + b, 0);
  for (let i = rows - 1; remainder > 0; i = (i - 1 + rows) % rows, remainder -= 1) {
    counts[i] = (counts[i] ?? 0) + 1;
  }
  const polar: { angle: number; r: number }[] = [];
  radii.forEach((r, i) => {
    const c = counts[i] ?? 0;
    for (let k = 0; k < c; k += 1) {
      const angle = Math.PI - (c === 1 ? Math.PI / 2 : (Math.PI * k) / (c - 1));
      polar.push({ angle, r });
    }
  });
  polar.sort((p, q) => q.angle - p.angle || p.r - q.r);
  const closestAlongRow = Math.min(
    ...radii.map((r, i) => (Math.PI * r) / Math.max(1, (counts[i] ?? 0) - 1)),
  );
  const ringGap = (1 - inner) / (rows - 1);
  const { cx, cy, radius } = HEMICYCLE_VIEW;
  return {
    seats: polar.map(({ angle, r }) => ({
      x: cx + Math.cos(angle) * r * radius,
      y: cy - Math.sin(angle) * r * radius,
    })),
    dotRadius: Math.min(closestAlongRow, ringGap) * 0.42 * radius,
  };
}

/** A seat's diameter in CSS pixels when the drawing space is shown `drawnWidthPx` wide. */
export function seatDiameterPx(layout: HemicycleLayout, drawnWidthPx: number, viewWidth: number): number {
  return (layout.dotRadius * 2 * drawnWidthPx) / viewWidth;
}

/** True when the seats would be drawn too small to read (the card then shows bars). */
export function seatsTooSmall(layout: HemicycleLayout, drawnWidthPx: number, viewWidth: number): boolean {
  return seatDiameterPx(layout, drawnWidthPx, viewWidth) < MIN_SEAT_DIAMETER_PX;
}

/** The point beyond the outer row where a bloc's arc label goes, and how it is anchored. */
export function arcLabelPoint(seat: SeatPoint): { x: number; y: number; anchor: "start" | "middle" | "end" } {
  const { cx, cy, radius } = HEMICYCLE_VIEW;
  const angle = Math.atan2(cy - seat.y, seat.x - cx);
  const reach = radius + 18;
  const cos = Math.cos(angle);
  return {
    x: cx + cos * reach,
    y: cy - Math.sin(angle) * reach,
    anchor: cos > 0.25 ? "start" : cos < -0.25 ? "end" : "middle",
  };
}

/** Only blocs holding at least a tenth of the chamber are named on the arc (every bloc is named in
 * the table), so names never collide. */
export function namedOnArc(blocSeats: number, chamberSeats: number): boolean {
  return blocSeats * 10 >= chamberSeats;
}

/** Index of the middle seat of a bloc that starts at `start` and holds `seats` seats. */
export function middleSeatIndex(start: number, seats: number): number {
  return start + Math.floor((seats - 1) / 2);
}

/** Start index of each bloc, in order, from their seat counts. */
export function blocStarts(seatCounts: readonly number[]): number[] {
  const starts: number[] = [];
  let next = 0;
  for (const count of seatCounts) {
    starts.push(next);
    next += count;
  }
  return starts;
}

/** The tally bar: how far support reaches, and where the threshold sits, as percentages. */
export function tallyBar(supporting: number, required: number, total: number): { supportPct: number; requiredPct: number } {
  if (total <= 0) return { supportPct: 0, requiredPct: 0 };
  return { supportPct: (supporting * 100) / total, requiredPct: (required * 100) / total };
}

/** The fallback bars: each bloc's share of the chamber, as consecutive percentage segments. */
export function barSegments(seatCounts: readonly number[]): { startPct: number; widthPct: number }[] {
  const total = seatCounts.reduce((a, b) => a + b, 0);
  if (total <= 0) return seatCounts.map(() => ({ startPct: 0, widthPct: 0 }));
  return blocStarts(seatCounts).map((start, i) => ({
    startPct: (start * 100) / total,
    widthPct: ((seatCounts[i] ?? 0) * 100) / total,
  }));
}

/** Whether seat `k` of a bloc is shown filled: the first `supporting` seats are. */
export function seatFilled(k: number, supporting: number): boolean {
  return k < supporting;
}

/** Sum of seat counts (rows of a chamber). */
export function sumSeats(rows: readonly { seats: number }[]): number {
  return rows.reduce((a, b) => a + b.seats, 0);
}

/** Sum of supporting seats (rows of a chamber). */
export function sumSupporting(rows: readonly { supporting_seats: number }[]): number {
  return rows.reduce((a, b) => a + b.supporting_seats, 0);
}

/** The index in the layout of seat `k` of the bloc that starts at `start`. */
export function seatIndex(start: number, k: number): number {
  return start + k;
}

/** A hollow seat is drawn a little smaller, with a ring, so it reads as empty at any size. */
export function hollowSeat(dotRadius: number): { r: number; strokeWidth: number } {
  return { r: dotRadius * 0.86, strokeWidth: dotRadius * 0.28 };
}

/** The speaker's dais, under the centre of the arc. */
export function daisPath(): string {
  const { cx, cy } = HEMICYCLE_VIEW;
  return `M${cx - 46} ${cy + 4} h92 v14 h-92z`;
}
