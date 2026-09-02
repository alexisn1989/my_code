/**
 * `src/format/` -- the ONLY place display arithmetic may occur (frozen plan
 * Sec 14.1 / R9, T-format-boundary). Every function here converts an
 * ALREADY-COMPUTED server value into a display string or a purely visual
 * ratio; nothing here decides a game outcome, sums a vote, or derives a cost
 * the server has not already returned as a number.
 *
 * Guarded structurally by `src/format/format-boundary.test.ts`, which walks
 * every other source file's real TypeScript AST and fails on an arithmetic
 * `BinaryExpression` outside this directory and test files.
 */

/** `12345` (bps) -> "123.45%". Mirrors the backend's own
 * `format_bps_percent` (backend/app/api/projections.py) so a raw bps field
 * the backend did not pre-format (e.g. a decision-options bound) displays
 * identically to one it did. */
export function formatBpsPercent(valueBps: number): string {
  const whole = Math.trunc(valueBps / 100);
  const fraction = Math.abs(valueBps % 100)
    .toString()
    .padStart(2, "0");
  return `${whole}.${fraction}%`;
}

/** A ratio already expressed in basis points (0..10_000) -> a CSS width
 * percentage. Used for bar width ONLY, exactly like the greybox's existing
 * `RatioBar` -- the authoritative text next to the bar always comes from its
 * own separate, already-formatted field. */
export function ratioBpsToWidthPercent(ratioBps: number): string {
  return `${ratioBps / 100}%`;
}

/** Thousands-grouped, no invented currency symbol (the engine has none
 * either -- `StrictMoney` is a bare non-negative integer). */
export function formatAmount(amount: number): string {
  return amount.toLocaleString("en-US");
}

/** "500 / 1,000" -- the same shape `CapitalSummary.display` already uses
 * server-side, applied to fields the server returns as bare numbers instead
 * (e.g. a `ChamberPreview`'s `supporting_seats`/`total_seats`, or a
 * decision-options relationship-investment range). */
export function formatFraction(current: number, of: number): string {
  return `${formatAmount(current)} / ${formatAmount(of)}`;
}

/** A committed-vs-opening capital pair -> "120 of 500 committed". Composes
 * two already-server-provided integers into one sentence; performs no
 * simulation logic (affordability itself is still the server's `affordable`
 * boolean, never re-derived here). */
export function formatCommitted(committed: number, opening: number): string {
  return `${formatAmount(committed)} of ${formatAmount(opening)} committed`;
}

/** Wraps a tab index by `delta` positions within a `length`-sized cycle --
 * roving-tabindex keyboard navigation math (Gate 4A3A's card browser), not
 * display formatting, but arithmetic all the same, so it lives in the one
 * place the format-boundary test allows a `BinaryExpression` to appear. */
export function wrapIndex(index: number, delta: number, length: number): number {
  return (index + delta + length) % length;
}

/** Bumps the client-side "loaded game" generation counter
 * (`gameGenerationQueryKey`, `src/api/queries.ts`) by one. Not display
 * formatting, but arithmetic all the same, so it lives here per the format
 * boundary rather than inline at the call site. */
export function nextGeneration(previous: number | undefined): number {
  return (previous ?? 0) + 1;
}

/** One authored strategic-map label anchor (`StrategicTheaterProjection.label_anchor`,
 * Strategic Military Map Gate M0). Declared here rather than imported from `../api/schema` so
 * this module keeps its zero-import purity; TypeScript still checks the two unions are
 * assignable at the call site, so a contract change cannot drift past unnoticed. */
export type LabelAnchorValue = "n" | "s" | "e" | "w" | "center";

/** The SVG `text-anchor` values this module emits. */
export type SvgTextAnchor = "start" | "middle" | "end";

/** How far, in authored grid units, a theater label sits from its own node. The strategic map
 * is authored on a 0..10,000 grid (backend `geography.MAP_GRID_MAX`) and the SVG `viewBox`
 * matches it 1:1, so this is a grid distance, not a pixel one. */
const LABEL_OFFSET_UNITS = 330;

/**
 * Where one theater's label goes, given its node position and its authored `label_anchor`.
 *
 * The anchor names a side of the node ("n" = the label sits above it), and the returned
 * `textAnchor` keeps the text growing AWAY from the node rather than back across it, so an
 * east-anchored label starts at its point and a west-anchored one ends at it.
 *
 * This is the ONLY place the map's coordinate offset arithmetic happens: the screen component
 * may not compute `x ± offset` inline (`format-boundary.test.ts` walks its real AST and fails on
 * any arithmetic `BinaryExpression` outside `src/format/**`).
 */
export function labelOffsetPosition(
  x: number,
  y: number,
  anchor: LabelAnchorValue,
): { x: number; y: number; textAnchor: SvgTextAnchor } {
  switch (anchor) {
    case "n":
      return { x, y: y - LABEL_OFFSET_UNITS, textAnchor: "middle" };
    case "s":
      return { x, y: y + LABEL_OFFSET_UNITS, textAnchor: "middle" };
    case "e":
      return { x: x + LABEL_OFFSET_UNITS, y, textAnchor: "start" };
    case "w":
      return { x: x - LABEL_OFFSET_UNITS, y, textAnchor: "end" };
    case "center":
      return { x, y, textAnchor: "middle" };
  }
}

/**
 * Wraps `position` into a `paletteSize`-long presentation palette.
 *
 * Used to hand each distinct map owner a visual style from a fixed palette: the caller sorts its
 * owners deterministically first, so the same map always produces the same assignment regardless
 * of the order the server happened to emit its collections in. `paletteSize` must be non-zero --
 * every palette in the codebase is a non-empty literal array, so there is no runtime branch here
 * for a case that cannot occur.
 */
export function paletteIndex(position: number, paletteSize: number): number {
  return position % paletteSize;
}
