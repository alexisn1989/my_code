/**
 * Gate 4A3 M-2 — one chamber's seats, drawn as a hemicycle (the approved M-V design).
 *
 * Seats are grouped by bloc, in the order given, and coloured by party. Support is shown as FILLED
 * against HOLLOW seats and in numbers beside the diagram and in the table, never by colour alone.
 * In `seats` mode every seat is drawn filled in its party colour and no support is shown.
 *
 * The geometry is `format/hemicycle.ts`. The diagram measures the width it is drawn at; if a seat
 * would be smaller than 6 px there, bars with the same counts are drawn instead (no shipped chamber
 * needs them: 100 seats measure 8.7 px at 320 px).
 */

import { type RefObject, useEffect, useRef, useState } from "react";

import {
  arcLabelPoint,
  barSegments,
  blocStarts,
  daisPath,
  hemicycleLayout,
  hollowSeat,
  middleSeatIndex,
  namedOnArc,
  seatFilled,
  seatIndex,
  seatsTooSmall,
  sumSeats,
} from "../../format/hemicycle";
import { BARS_NOTE } from "../../format/parliament";

export interface HemicycleBloc {
  key: string;
  partyId: string;
  /** The short name shown on the arc (the bloc name without its party). */
  shortName: string;
  seats: number;
  /** Supporting seats in `current` and `recorded` mode; ignored in `seats` mode. */
  supporting: number;
}

/** Arc labels need room; below this drawn width they are left to the table. */
const LABELS_FROM_PX = 560;
const VIEW_WITH_LABELS = { x: -150, y: -12, width: 1020, height: 400 };
const VIEW_PLAIN = { x: 10, y: 10, width: 700, height: 370 };

function useDrawnWidth(): [RefObject<HTMLDivElement | null>, number | null] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState<number | null>(null);
  useEffect(() => {
    const node = ref.current;
    if (node === null || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (box !== undefined) setWidth(box.width);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

export function Hemicycle({
  chamber,
  blocs,
  colours,
  mode,
  label,
  arcLabels = true,
}: {
  chamber: string;
  blocs: readonly HemicycleBloc[];
  colours: Readonly<Record<string, string>>;
  /** `current`: filled = supporting if resolved now. `recorded` (Gate 4A3 M-4): filled = the
   * supporting seats a past vote RECORDED -- drawn the same way, named differently so a reader of
   * the DOM can never mistake one for the other. `seats`: every seat in its party colour. */
  mode: "current" | "recorded" | "seats";
  /** The accessible description, in words. */
  label: string;
  /** The result card's small diagrams leave naming to the bloc table, as the mockup does. */
  arcLabels?: boolean;
}) {
  const [ref, drawnWidth] = useDrawnWidth();
  const total = sumSeats(blocs);
  const layout = hemicycleLayout(total);
  const showLabels = arcLabels && drawnWidth !== null && drawnWidth >= LABELS_FROM_PX;
  const view = showLabels ? VIEW_WITH_LABELS : VIEW_PLAIN;
  const tooSmall = drawnWidth !== null && seatsTooSmall(layout, drawnWidth, view.width);
  const starts = blocStarts(blocs.map((b) => b.seats));
  const hollow = hollowSeat(layout.dotRadius);

  if (tooSmall) {
    const segments = barSegments(blocs.map((b) => b.seats));
    return (
      <div ref={ref} data-testid="hemicycle-bars" data-chamber={chamber}>
        <svg role="img" aria-label={label} viewBox="0 0 100 8" preserveAspectRatio="none" className="block h-6 w-full">
          {blocs.map((b, i) => {
            const segment = segments[i]!;
            const filled = mode === "seats" || b.supporting > 0;
            return (
              <rect
                key={b.key}
                x={segment.startPct}
                width={segment.widthPct}
                height={8}
                fill={filled ? colours[b.partyId] : "var(--color-navy-900)"}
                stroke={colours[b.partyId]}
                strokeWidth={0.4}
              />
            );
          })}
        </svg>
        <p className="mt-1 text-xs text-parchment-200/80">{BARS_NOTE}</p>
      </div>
    );
  }

  return (
    <div ref={ref} className="mx-auto w-full max-w-2xl">
      <svg
        data-testid="hemicycle"
        data-chamber={chamber}
        data-mode={mode}
        role="img"
        aria-label={label}
        viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`}
        className="block h-auto w-full"
      >
        {blocs.map((b, i) =>
          Array.from({ length: b.seats }, (_, k) => {
            const seat = layout.seats[seatIndex(starts[i] ?? 0, k)];
            if (seat === undefined) return null;
            const filled = mode === "seats" || seatFilled(k, b.supporting);
            const colour = colours[b.partyId] ?? "var(--color-parchment-200)";
            return (
              <circle
                key={`${b.key}-${k}`}
                data-seat
                data-party={b.partyId}
                data-filled={filled ? "true" : "false"}
                cx={seat.x}
                cy={seat.y}
                r={filled ? layout.dotRadius : hollow.r}
                fill={filled ? colour : "var(--color-navy-900)"}
                stroke={filled ? "none" : colour}
                strokeWidth={filled ? 0 : hollow.strokeWidth}
              />
            );
          }),
        )}
        {/* The speaker's dais, at the centre of the arc. */}
        <path
          d={daisPath()}
          fill="var(--color-navy-800)"
          stroke="var(--color-gold-600)"
        />
        {showLabels
          ? blocs.map((b, i) => {
              if (!namedOnArc(b.seats, total)) return null;
              const seat = layout.seats[middleSeatIndex(starts[i] ?? 0, b.seats)];
              if (seat === undefined) return null;
              const point = arcLabelPoint(seat);
              return (
                <text
                  key={`label-${b.key}`}
                  x={point.x}
                  y={point.y}
                  textAnchor={point.anchor}
                  fontSize={16}
                  fill="var(--color-parchment-200)"
                  aria-hidden="true"
                >
                  {b.shortName}
                </text>
              );
            })
          : null}
      </svg>
    </div>
  );
}
