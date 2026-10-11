/**
 * Gate 4A3 M-1: the illustrated country map on the Dashboard, and its ordinary twin, the Places list.
 *
 * - The picture is the game's own strategic-map outline, styled. The whole country carries ONE
 *   national wash (the national tint's rule), never a per-region value; hills, trees, the compass and
 *   the capital's street plan are decoration. The caption says so.
 * - The title plate keeps the national tint's contract (`data-testid="national-tint"`): its own
 *   inline mix, the country's name on a navy-950 label, and the same accessible name.
 * - The seven places are real buttons over the picture. Each has a twin in the Places list with the
 *   same name and destination (`places.ts`), so the map is never the only way in, and the main
 *   navigation is unchanged.
 * - Geometry comes from `format/countryMap.ts` (display arithmetic lives there only).
 */

import { useEffect, useRef, useState, type RefObject } from "react";

import type { DashboardProjection, StrategicMapProjection } from "../../api/client";
import { countryMapGeometry, landWash, mapIllustrationNote } from "../../format/countryMap";
import { formatBpsPercent, tintAccessibleName, tintCaption, tintFill } from "../../format/format";
import type { NavigateOptions, ScreenProps } from "../registry";
import { Landmark } from "./landmarks";
import { PLACES, placeAccessibleName } from "./places";

/** Below this container width the phone layout is used: a large inset and numbered pins. */
const TALL_BELOW_PX = 760;

function useNarrow(): [RefObject<HTMLDivElement | null>, boolean] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [narrow, setNarrow] = useState(
    () => typeof window !== "undefined" && window.innerWidth < TALL_BELOW_PX,
  );
  useEffect(() => {
    const element = ref.current;
    if (element === null || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width !== undefined && width > 0) setNarrow(width < TALL_BELOW_PX);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, narrow];
}

const GO: NavigateOptions = { focusHeading: true };

export function CountryMap({
  dashboard,
  map,
  navigate,
}: {
  dashboard: DashboardProjection;
  /** `null` while the map loads, or if it cannot be read: the plate and caption still show, and the
   * Places list still leads everywhere. */
  map: StrategicMapProjection | null;
  navigate: ScreenProps["navigate"];
}) {
  const [frameRef, narrow] = useNarrow();
  const bps = dashboard.map.tint_value_bps;
  const label = dashboard.map.tint_metric_label;
  // On wide maps the plate overlays the picture's top-left corner; on narrow (tall) maps it sits
  // above the picture, so it never covers the country.
  const plateInFlow = narrow && map !== null;
  const plate = (
    <div
      data-testid="national-tint"
      data-tint-bps={bps}
      role="img"
      aria-label={tintAccessibleName(dashboard.country_name, label, formatBpsPercent(bps))}
      style={{ backgroundColor: tintFill(bps) }}
      className={`${plateInFlow ? "relative m-3 inline-block" : "absolute left-[3%] top-[4%]"} rounded border border-gold-600 p-2 shadow-lg`}
    >
      {/* The name sits on its own navy-950 label rather than on the mix: every text backdrop is an
          authored palette surface (the contrast sweeps assert it), and the tint is a graphic. */}
      <span
        aria-hidden="true"
        className="block rounded bg-navy-950 px-3 py-1 font-[family-name:var(--font-display)] text-lg text-parchment-100 sm:text-2xl"
      >
        {dashboard.country_name}
      </span>
    </div>
  );
  const caption = (
    <figcaption className="mt-2 text-xs text-parchment-200/70">
      {tintCaption(label)} {mapIllustrationNote()}
    </figcaption>
  );
  if (map === null) {
    return (
      <figure className="m-0">
        <div ref={frameRef} data-testid="country-map" data-layout="plate-only" className="relative h-48 overflow-hidden rounded border border-gold-600 bg-navy-950">
          {plate}
        </div>
        {caption}
      </figure>
    );
  }
  const geometry = countryMapGeometry(map, narrow, PLACES.map((place) => (narrow ? place.plot.phone : place.plot.wide)));
  const { width, height, city } = geometry;
  const { box } = city;

  return (
    <figure className="m-0">
      <div
        ref={frameRef}
        data-testid="country-map"
        data-layout={narrow ? "tall" : "wide"}
        className="relative overflow-hidden rounded border border-gold-600 bg-navy-950 shadow-lg"
      >
        {plateInFlow ? plate : null}
        {/* The picture and its pins share one box, so pin percentages are of the picture alone. */}
        <div className="relative">
          <svg viewBox={`0 0 ${width} ${height}`} aria-hidden="true" focusable="false" className="block h-auto w-full">
            <defs>
              <filter id="map-grain">
                <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={4} />
                <feColorMatrix values="0 0 0 0 0.35  0 0 0 0 0.27  0 0 0 0 0.16  0 0 0 0.10 0" />
                <feComposite in2="SourceGraphic" operator="in" />
              </filter>
              <radialGradient id="map-sea" cx="40%" cy="40%" r="80%">
                <stop offset="0" stopColor="var(--color-navy-800)" />
                <stop offset="1" stopColor="var(--color-navy-950)" />
              </radialGradient>
              <clipPath id="map-city-clip">
                <path d={city.wall} />
              </clipPath>
            </defs>
            <rect width={width} height={height} fill="url(#map-sea)" />
            {geometry.neighbourPaths.map((d) => (
              <path key={d} d={d} fill="var(--color-parchment-200)" opacity={0.55} stroke="var(--color-charcoal-700)" strokeWidth={1.2} />
            ))}
            {geometry.countryPaths.map((d) => (
              <path key={`halo-${d}`} d={d} fill="none" stroke="var(--color-parchment-100)" strokeOpacity={0.25} strokeWidth={14} strokeLinejoin="round" />
            ))}
            {/* The ONE national wash: the same colour over the whole country. */}
            {geometry.countryPaths.map((d) => (
              <path key={`land-${d}`} data-national-wash d={d} style={{ fill: landWash(bps) }} stroke="var(--color-navy-950)" strokeWidth={2.4} strokeLinejoin="round" />
            ))}
            {geometry.countryPaths.map((d) => (
              <path key={`grain-${d}`} d={d} fill="var(--color-parchment-100)" filter="url(#map-grain)" />
            ))}
            {geometry.riverPaths.map((d) => (
              <path key={d} d={d} fill="none" stroke="var(--color-info-400)" strokeWidth={2.2} strokeLinecap="round" opacity={0.85} />
            ))}
            {geometry.terrain.map((mark) =>
              mark.kind === "hill" ? (
                <path key={`h${mark.x}-${mark.y}`} transform={`translate(${mark.x} ${mark.y})`} d="M-9 4 l9 -9 l9 9 M-3 -1 l3 -3 l3 3" fill="none" stroke="var(--color-charcoal-700)" strokeWidth={1.4} />
              ) : (
                <g key={`t${mark.x}-${mark.y}`} transform={`translate(${mark.x} ${mark.y})`}>
                  <circle cy={-3} r={4.2} fill="var(--color-success-400)" opacity={0.55} stroke="var(--color-charcoal-700)" strokeWidth={1} />
                  <path d="M0 1v4" stroke="var(--color-charcoal-700)" strokeWidth={1.2} />
                </g>
              ),
            )}
            <path d={`M${geometry.capital.x} ${geometry.capital.y} L${geometry.leaderEnd.x} ${geometry.leaderEnd.y}`} stroke="var(--color-parchment-100)" strokeWidth={1.6} strokeDasharray="6 5" />
            {geometry.neighbourLabels.map((name) => (
              <text key={name.text} x={name.x} y={name.y} textAnchor="middle" fontFamily="Georgia, serif" fontSize={15} letterSpacing={3} fill="var(--color-navy-950)">
                {name.text}
              </text>
            ))}
            <g transform={`translate(${geometry.capital.x} ${geometry.capital.y})`}>
              <circle r={11} fill="var(--color-parchment-100)" stroke="var(--color-navy-950)" strokeWidth={2} />
              <circle r={4.5} fill="var(--color-accent-red-600)" />
            </g>
            <g transform={`translate(${geometry.compass.x} ${geometry.compass.y})`} opacity={0.9}>
              <circle r={26} fill="none" stroke="var(--color-parchment-200)" strokeWidth={1} />
              <path d="M0 -34 L6 0 L0 34 L-6 0Z" fill="var(--color-parchment-200)" />
              <path d="M-34 0 L0 5 L34 0 L0 -5Z" fill="var(--color-gold-600)" />
              <text y={-38} textAnchor="middle" fontFamily="Georgia, serif" fontSize={13} fill="var(--color-parchment-200)">N</text>
            </g>
            {/* The capital: an illustrated town plan -- wall, streets, river, bridges, square, houses.
                Decoration only; the institutions stand on their plots as buttons over it. */}
            <rect x={box.x} y={box.y} width={box.w} height={box.h} rx={10} fill="var(--color-navy-800)" opacity={0.9} />
            <path d={city.wall} fill="var(--color-parchment-100)" />
            <g clipPath="url(#map-city-clip)">
              <path d={city.wall} fill="var(--color-parchment-100)" filter="url(#map-grain)" />
              {city.lanes.map((lane) => (
                <path key={`l${lane.x1}-${lane.y1}-${lane.x2}`} d={`M${lane.x1} ${lane.y1} L${lane.x2} ${lane.y2}`} stroke="var(--color-charcoal-700)" strokeOpacity={0.16} strokeWidth={narrow ? 6 : 4} />
              ))}
              {city.avenues.map((avenue) => (
                <path key={`a${avenue.x1}-${avenue.y1}-${avenue.x2}`} d={`M${avenue.x1} ${avenue.y1} L${avenue.x2} ${avenue.y2}`} stroke="var(--color-parchment-200)" strokeWidth={narrow ? 16 : 10} />
              ))}
              {city.houses.map((house) => (
                <rect key={`h${house.x}-${house.y}`} x={house.x} y={house.y} width={house.w} height={house.h} rx={1} fill="var(--color-parchment-200)" stroke="var(--color-charcoal-700)" strokeOpacity={0.45} strokeWidth={0.8} />
              ))}
              <path d={city.river} fill="none" stroke="var(--color-info-400)" strokeWidth={city.riverWidth} opacity={0.75} strokeLinecap="round" />
              {city.bridges.map((bridge) => (
                <rect key={`b${bridge.x}`} x={bridge.x} y={bridge.y} width={bridge.w} height={bridge.h} rx={2} fill="var(--color-parchment-200)" stroke="var(--color-charcoal-700)" strokeOpacity={0.6} strokeWidth={1.2} />
              ))}
              <circle cx={city.square.x} cy={city.square.y} r={city.square.r} fill="var(--color-parchment-200)" stroke="var(--color-charcoal-700)" strokeOpacity={0.5} strokeWidth={1.5} />
              {city.plots.map((plot) => (
                <ellipse key={`p${plot.x}-${plot.y}`} cx={plot.x} cy={plot.y} rx={narrow ? 70 : 36} ry={narrow ? 44 : 24} fill="var(--color-gold-600)" opacity={0.12} />
              ))}
            </g>
            <path d={city.wall} fill="none" stroke="var(--color-navy-950)" strokeWidth={narrow ? 7 : 4} strokeLinejoin="round" />
            {city.towers.map((tower) => (
              <circle key={`t${tower.x}-${tower.y}`} cx={tower.x} cy={tower.y} r={narrow ? 12 : 7} fill="var(--color-parchment-200)" stroke="var(--color-navy-950)" strokeWidth={narrow ? 4 : 2.5} />
            ))}
          </svg>

          {/* The title plate keeps the national tint's contract: one solid mix, the name on navy-950. */}
          {plateInFlow ? null : plate}

          <ul className="m-0 list-none p-0">
            {PLACES.map((place, index) => {
              const pin = geometry.pins[index]!;
              return (
                <li key={place.id}>
                  <button
                    type="button"
                    data-place={place.id}
                    data-map-pin
                    aria-label={placeAccessibleName(place)}
                    onClick={() => navigate(place.screen, GO)}
                    style={{ left: `${pin.left}%`, top: `${pin.top}%` }}
                    className="group absolute flex min-h-11 min-w-11 -translate-x-1/2 -translate-y-1/2 flex-col items-center rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                  >
                    {/* The building itself, standing on its plot: no disc, no badge frame. */}
                    <span className="relative grid h-11 w-11 place-items-center drop-shadow-md group-hover:scale-110 sm:h-14 sm:w-14">
                      <Landmark id={place.id} className="h-11 w-11 sm:h-14 sm:w-14" />
                      {narrow ? (
                        <span aria-hidden="true" className="absolute right-0 top-0 grid h-5 w-5 place-items-center rounded-full border border-gold-500 bg-navy-950 text-xs text-parchment-100">
                          {place.number}
                        </span>
                      ) : null}
                    </span>
                    {narrow ? null : (
                      <span aria-hidden="true" className="-mt-1 whitespace-nowrap rounded-sm border border-gold-600 bg-navy-950 px-1.5 font-[family-name:var(--font-display)] text-xs text-parchment-100 shadow group-hover:border-parchment-100">
                        {place.name}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
      {caption}
    </figure>
  );
}

/** The map's ordinary twin: the same seven places as plain, numbered buttons. */
export function PlacesList({ navigate }: { navigate: ScreenProps["navigate"] }) {
  return (
    <nav aria-labelledby="places-heading" data-testid="places-list">
      <h3 id="places-heading" className="mb-2 font-[family-name:var(--font-display)] text-lg text-parchment-100">
        Places
      </h3>
      <ol data-testid="places-grid" className="m-0 grid list-none grid-cols-1 gap-2 p-0 sm:grid-cols-2 xl:grid-cols-4">
        {PLACES.map((place) => (
          <li key={place.id}>
            <button
              type="button"
              data-place={place.id}
              aria-label={placeAccessibleName(place)}
              onClick={() => navigate(place.screen, GO)}
              className="grid min-h-14 w-full grid-cols-[2.5rem_minmax(0,1fr)] items-center gap-3 rounded border border-gold-600 bg-navy-800 px-3 py-2 text-left hover:border-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
            >
              <span className="grid h-10 w-10 place-items-center rounded-full border border-gold-600 bg-parchment-100">
                <Landmark id={place.id} className="h-7 w-7" />
              </span>
              <span className="min-w-0">
                <span className="block font-[family-name:var(--font-display)] text-parchment-100">
                  <span className="mr-1.5 text-xs text-gold-500">{place.number}</span>
                  {place.name}
                </span>
                <span className="block text-xs text-parchment-200/80">
                  {place.purpose} → {place.opens}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
