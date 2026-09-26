/**
 * Gate 4A2 — shared, unstyled-by-design presentation primitives.
 *
 * "Greybox" means structure without art: flat panels from the existing token
 * palette, no icons, no portraits, no animation, no final imagery. Layout and
 * semantics are the deliverable; visual polish is Gate 4A5.
 *
 * No component here performs simulation arithmetic. Where a bar has a width, it
 * scales an ALREADY-PROJECTED ratio field for visual purposes only (via
 * `../format/format.ts`, the one arithmetic boundary), and never changes the
 * semantic value shown in text beside it.
 */

import type { ReactNode } from "react";

import { RATIO_BPS_MAX, RATIO_BPS_MIN, ratioBpsToWidthPercent } from "../format/format";
import type { Direction, Tone } from "./types";

const TONE_CLASS: Record<Tone, string> = {
  positive: "text-success-400",
  negative: "text-danger-400",
  caution: "text-warning-400",
  neutral: "text-parchment-200",
};

const TONE_GLYPH: Record<Tone, string> = {
  positive: "✓",
  negative: "✗",
  caution: "▲",
  neutral: "■",
};

const TONE_LABEL: Record<Tone, string> = {
  positive: "positive",
  negative: "negative",
  caution: "caution",
  neutral: "neutral",
};

/** Exported so other renderers of a `Direction` (e.g. a policy card's effect
 * chips) can match `DeltaText`'s own glyph/word convention exactly, instead
 * of maintaining a second copy of the same three-entry map. */
export const DIRECTION_GLYPH: Record<Direction, string> = {
  up: "▲",
  down: "▼",
  unchanged: "■",
};

export const DIRECTION_LABEL: Record<Direction, string> = {
  up: "up",
  down: "down",
  unchanged: "unchanged",
};

export function Panel({
  title,
  children,
  headingLevel = 3,
}: {
  title: string;
  children: ReactNode;
  headingLevel?: 2 | 3;
}) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <section className="rounded border border-navy-800 bg-navy-900 p-4">
      <Heading className="mb-3 font-[family-name:var(--font-display)] text-lg text-parchment-100">
        {title}
      </Heading>
      {children}
    </section>
  );
}

/**
 * Colour is never the only carrier of meaning: every toned value also gets a
 * glyph and a visually-hidden word.
 */
export function ToneValue({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={TONE_CLASS[tone]}>
      <span aria-hidden="true">{TONE_GLYPH[tone]}</span>{" "}
      <span className="sr-only">{TONE_LABEL[tone]}</span>
      {children}
    </span>
  );
}

export function DeltaText({
  deltaText,
  direction,
}: {
  deltaText: string | null;
  direction: Direction;
}) {
  if (deltaText === null) {
    return null;
  }
  return (
    <span className="text-xs text-parchment-200/70">
      <span aria-hidden="true">{DIRECTION_GLYPH[direction]}</span>{" "}
      <span className="sr-only">{DIRECTION_LABEL[direction]}</span>
      {deltaText}
    </span>
  );
}

export function DataTable({
  caption,
  columns,
  rows,
}: {
  caption: string;
  columns: string[];
  rows: { key: string; cells: ReactNode[] }[];
}) {
  /*
   * Gate 4A3 Commit 3, findings V2 and V3: the 320px CONFORMANCE width.
   *
   * At 320 CSS px -- the width WCAG 2.2 SC 1.4.10 actually names -- a multi-column data table cannot
   * reflow below its minimum content width, so it pushed the Decisions column and its panel wider than
   * the viewport and THE PAGE scrolled horizontally. That is the reflow failure.
   *
   * The fix is to contain the scrolling to the table rather than to shrink the data: SC 1.4.10 exempts
   * "content which requires two-dimensional layout for usage or meaning", and a data table is the
   * canonical example. So the page no longer scrolls, every cell stays reachable, and nothing is
   * hidden or truncated -- which is the distinction between fixing a reflow failure and merely
   * clipping the evidence of one.
   *
   * `tabIndex={0}` and the group role make the scroll container keyboard-operable: a scrollable region
   * that only a pointer can reach would trade a reflow failure for a keyboard one. It is labelled by
   * the same caption the table carries, so the two do not disagree.
   */
  return (
    <div
      role="group"
      aria-label={caption}
      tabIndex={0}
      className="overflow-x-auto focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
    >
    <table className="w-full text-left text-sm tabular-nums">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column} scope="col" className="pb-2 pr-4 font-normal text-parchment-200/70">
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className="border-t border-navy-800">
            {row.cells.map((cell, index) => (
              // eslint-disable-next-line react/no-array-index-key -- static fixture columns
              <td key={index} className="py-2 pr-4">
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

/**
 * Renders a server-projected ratio as a bar. `ratioBps` is an already-computed
 * projection field; it is used for bar WIDTH only. The authoritative text beside
 * the bar comes from its own separate field, so the visual scaling can never
 * change the semantic value the player reads.
 */
export function RatioBar({
  label,
  valueText,
  ratioBps,
}: {
  label: string;
  valueText: string;
  ratioBps: number;
}) {
  const widthPercent = ratioBpsToWidthPercent(ratioBps);
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span>{label}</span>
        <span className="tabular-nums">{valueText}</span>
      </div>
      {/* Finding S1 (Gate 4A3 Commit 3): `role="meter"` REQUIRES `aria-valuenow`, and this element
          carried only `aria-label` and `aria-valuetext` -- so assistive technology was handed a meter
          with no current value. axe rates it critical.

          It was found by the jsdom COMPONENT supplement and not by the browser screen sweep, and the
          reason is worth keeping: nothing renders `RatioBar` yet, so no screen could exhibit it. A
          screen-level audit structurally cannot find a defect in a component no screen mounts.

          `aria-valuenow` takes the raw basis-point value and the range is declared from the scale's
          own constants; `aria-valuetext` keeps carrying the human-readable form, which is exactly the
          division of labour ARIA intends. No arithmetic happens here -- that would belong in
          `src/format/**` and `format-boundary.test.ts` would refuse it. */}
      <div
        role="meter"
        aria-label={label}
        aria-valuenow={ratioBps}
        aria-valuemin={RATIO_BPS_MIN}
        aria-valuemax={RATIO_BPS_MAX}
        aria-valuetext={valueText}
        className="h-2 w-full rounded bg-navy-800"
      >
        <div className="h-2 rounded bg-gold-500" style={{ width: widthPercent }} />
      </div>
    </div>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="text-sm text-parchment-200/60">{children}</p>;
}
