/**
 * Gate 4A0 greybox — shared, unstyled-by-design presentation primitives.
 *
 * "Greybox" means structure without art: flat panels from the existing token
 * palette, no icons, no portraits, no animation, no final imagery. Layout and
 * semantics are the deliverable; visual polish is Gate 4A5.
 *
 * No component here performs simulation arithmetic. Where a bar has a width, it
 * scales an ALREADY-PROJECTED ratio field for visual purposes only, and never
 * changes the semantic value shown in text beside it.
 */

import type { ReactNode } from "react";

import type { Direction, Tone } from "./contract";

const TONE_CLASS: Record<Tone, string> = {
  positive: "text-emerald-300",
  negative: "text-red-300",
  caution: "text-amber-300",
  neutral: "text-parchment-200",
};

const DIRECTION_GLYPH: Record<Direction, string> = {
  up: "▲",
  down: "▼",
  unchanged: "■",
};

const DIRECTION_LABEL: Record<Direction, string> = {
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
  return <span className={TONE_CLASS[tone]}>{children}</span>;
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
  return (
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
  const widthPercent = `${ratioBps / 100}%`;
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span>{label}</span>
        <span className="tabular-nums">{valueText}</span>
      </div>
      <div
        role="meter"
        aria-label={label}
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
