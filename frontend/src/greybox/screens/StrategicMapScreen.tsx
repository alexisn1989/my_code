/**
 * Strategic Military Map Gate M0 — the accessible read-only screen for
 * `GET /api/game/map/strategic` (`useStrategicMap`, `../../api/queries`).
 *
 * Commit 7a (fix-forward on commit 7) replaces the desktop placeholder with the real map the
 * frozen plan's §12/§14 always specified: authored political polygons, hatch overlays, route
 * lines with direction arrows, theater nodes, a capital marker and theater labels, rendered as a
 * native inline SVG on the map's own 0..10,000 authored grid (backend `geography.MAP_GRID_MAX`),
 * so no coordinate is rescaled on the way to the screen.
 *
 * Still read-only, matching §12: selecting a theater queues nothing, matches no order, and
 * implies no movement -- there is no button, menu item, or form control anywhere on this screen
 * that mentions an order, a deployment or a unit.
 *
 * ACCESSIBILITY SPLIT. The SVG is `aria-hidden` and holds no tab stop: every fact it draws and
 * every interaction it offers has an equivalent in the always-present theater list and detail
 * panel, which stay the keyboard and screen-reader surface. Clicking a node and focusing (or
 * clicking) a list row write the SAME `selectedTheaterId`, so the two views cannot disagree --
 * they are one state, not two synchronised ones. Below 900px the SVG is not rendered at all and
 * the list carries the complete map, directions included.
 *
 * The map is campaign-static content, not per-turn state, so it is keyed on `useGameGeneration()`
 * (bumped only when a game starts or loads) rather than `revision` (which changes every turn and
 * would cause a needless refetch on every resolve).
 */

import { useEffect, useRef, useState } from "react";

import type {
  StrategicMapProjection,
  StrategicShapeProjection,
  StrategicTheaterProjection,
} from "../../api/client";
import { useGameGeneration, useStrategicMap } from "../../api/queries";
import { labelOffsetPosition, paletteIndex } from "../../format/format";
import { useSession } from "../../state/SessionContext";
import { ErrorPanel } from "../../status/ErrorPanel";
import { LoadingPanel } from "../../status/StatusPanels";
import { EmptyNote, Panel } from "../components";
import type { ScreenProps } from "../registry";

const KIND_LABEL: Record<StrategicTheaterProjection["kind"], string> = {
  land: "Land",
  coastal: "Coastal",
};

function theaterListItemLabel(theater: StrategicTheaterProjection): string {
  return `${theater.display_name} — ${KIND_LABEL[theater.kind]}, ${theater.owner_display_name}${
    theater.is_capital ? ", capital" : ""
  }`;
}

// --- Presentation constants ------------------------------------------------
//
// Every colour is an EXISTING token from `src/styles/tokens.css`, referenced through its own CSS
// custom property rather than a copied hex value, so the map cannot drift from the palette. No
// token is added here. SVG presentation attributes are CSS properties, so `var(...)` resolves in
// them exactly as it does in a stylesheet.
//
// Sizes are authored grid units (the viewBox is the authored grid), and every one of them is a
// literal constant: the component performs no coordinate arithmetic at all, which is what keeps
// it on the right side of `src/format/format-boundary.test.ts`.

/** The authored grid, 1:1. Backend `geography.MAP_GRID_MAX` is 10,000 on both axes. */
const MAP_VIEWBOX = "0 0 10000 10000";

/** The one player country's territory: solid, no hatch (`--color-gold-600`). */
const PLAYER_SHAPE_FILL = "var(--color-gold-600)";

/**
 * Foreign territory: a different fill AND a hatch overlay, so player-vs-foreign is carried on two
 * independent channels rather than by colour alone. Distinct foreign sovereigns additionally get
 * different fills and different hatch angles from each other.
 *
 * Exactly one player country can own map area (`map_player_ref_not_player`, frozen plan §9.1,
 * rejects a `PlayerCountryRef` that is not THE player country), so the player never needs a
 * palette of its own; foreign profiles genuinely can be many, so they get one.
 */
const FOREIGN_SHAPE_STYLES = [
  { fill: "var(--color-charcoal-700)", hatchPatternId: "mandate-map-hatch-0" },
  { fill: "var(--color-accent-red-600)", hatchPatternId: "mandate-map-hatch-1" },
] as const;

const SHAPE_BORDER = "var(--color-navy-800)";
const SHAPE_BORDER_WIDTH = 22;
const SHAPE_FILL_OPACITY = 0.55;

const HATCH_LINE = "var(--color-parchment-200)";
const HATCH_LINE_WIDTH = 26;
const HATCH_TILE = 260;
/** `d` for one tile of the hatch pattern: a single stroke across the middle of the tile, rotated
 * per owner. Drawn down the tile's centre line rather than its edge, because pattern content is
 * clipped to its own tile -- an edge stroke would lose the half of its width that falls outside. */
const HATCH_TILE_CENTRE = 130;
const HATCH_TILE_PATH = `M ${HATCH_TILE_CENTRE} 0 L ${HATCH_TILE_CENTRE} ${HATCH_TILE}`;

const ROUTE_LINE = "var(--color-parchment-200)";
const ROUTE_LINE_WIDTH = 18;
const ROUTE_ARROW_END_ID = "mandate-map-route-arrow-end";
const ROUTE_ARROW_START_ID = "mandate-map-route-arrow-start";

const NODE_FILL = "var(--color-navy-950)";
const NODE_STROKE = "var(--color-parchment-100)";
const NODE_STROKE_WIDTH = 26;
const NODE_RADIUS = 120;
const NODE_RADIUS_SELECTED = 190;
/** A coastal theater is drawn as a square, a land theater as a circle: kind is legible without
 * colour. The offsets are the negative half-sides, written as literals so no arithmetic is
 * needed to centre the square on its own centroid. */
const COASTAL_SIDE = 240;
const COASTAL_ORIGIN = -120;
const COASTAL_SIDE_SELECTED = 380;
const COASTAL_ORIGIN_SELECTED = -190;

const SELECTED_FILL = "var(--color-gold-500)";
const SELECTED_STROKE = "var(--color-gold-500)";
const SELECTION_RING_RADIUS = 420;
const SELECTION_RING_WIDTH = 22;
const SELECTION_RING_DASH = "70 60";

const CAPITAL_MARKER_COLOR = "var(--color-gold-500)";
const CAPITAL_RING_RADIUS = 290;
const CAPITAL_RING_WIDTH = 26;

const LABEL_COLOR = "var(--color-parchment-100)";
const LABEL_FONT_SIZE = 260;

// --- Owner styling ---------------------------------------------------------

interface OwnerStyle {
  fill: string;
  /** `null` for the player country, which is deliberately never hatched. */
  hatchPatternId: string | null;
}

const FOREIGN_NAMESPACE = "foreign_profile";

/** One sovereign, as the projection identifies it. */
interface OwnerRef {
  namespace: string;
  id: string;
}

/**
 * Owner styles, nested `namespace -> owner id -> style`.
 *
 * A NESTED map, not one keyed by a joined string: `StrictMapId` constrains only length and
 * strictness, never the character set, so no separator is guaranteed to be absent from an id.
 * Nesting sidesteps the question entirely rather than answering it -- and serializing the pair
 * into a key is not on the table either, since this codebase's raw-data boundary
 * (`src/raw-data-boundary.test.ts`) rightly keeps JSON serialization out of the rendering layer.
 */
type OwnerStyles = Map<string, Map<string, OwnerStyle>>;

/** Total order on owners, so the palette assignment below cannot depend on response order. */
function compareOwners(left: OwnerRef, right: OwnerRef): number {
  if (left.namespace !== right.namespace) {
    return left.namespace < right.namespace ? -1 : 1;
  }
  if (left.id !== right.id) {
    return left.id < right.id ? -1 : 1;
  }
  return 0;
}

/** Every distinct sovereign the map mentions -- as a shape owner or a theater owner -- sorted. */
function distinctOwners(map: StrategicMapProjection): OwnerRef[] {
  const idsByNamespace = new Map<string, Set<string>>();
  const remember = (namespace: string, id: string) => {
    const ids = idsByNamespace.get(namespace) ?? new Set<string>();
    ids.add(id);
    idsByNamespace.set(namespace, ids);
  };
  for (const shape of map.shapes) {
    remember(shape.owner_namespace, shape.owner_id);
  }
  for (const theater of map.theaters) {
    remember(theater.owner_namespace, theater.owner_id);
  }

  const owners: OwnerRef[] = [];
  for (const [namespace, ids] of idsByNamespace) {
    for (const id of ids) {
      owners.push({ namespace, id });
    }
  }
  return owners.sort(compareOwners);
}

/**
 * One visual style per distinct owner, assigned from a DETERMINISTICALLY SORTED owner set.
 *
 * Styling by owner rather than by shape position is what makes two islands of one sovereign look
 * like one sovereign, and what makes the assignment independent of the order the server happened
 * to emit `shapes`/`theaters` in -- the same property §10.3 proves server-side, held here too.
 */
function buildOwnerStyles(map: StrategicMapProjection): OwnerStyles {
  const styles: OwnerStyles = new Map();
  const assign = (owner: OwnerRef, style: OwnerStyle) => {
    const forNamespace = styles.get(owner.namespace) ?? new Map<string, OwnerStyle>();
    forNamespace.set(owner.id, style);
    styles.set(owner.namespace, forNamespace);
  };

  const owners = distinctOwners(map);
  for (const owner of owners) {
    if (owner.namespace !== FOREIGN_NAMESPACE) {
      assign(owner, { fill: PLAYER_SHAPE_FILL, hatchPatternId: null });
    }
  }
  owners
    .filter((owner) => owner.namespace === FOREIGN_NAMESPACE)
    .forEach((owner, index) => {
      const style = FOREIGN_SHAPE_STYLES[paletteIndex(index, FOREIGN_SHAPE_STYLES.length)];
      assign(owner, { fill: style.fill, hatchPatternId: style.hatchPatternId });
    });

  return styles;
}

function styleForShape(shape: StrategicShapeProjection, styles: OwnerStyles): OwnerStyle {
  return (
    styles.get(shape.owner_namespace)?.get(shape.owner_id) ?? {
      fill: PLAYER_SHAPE_FILL,
      hatchPatternId: null,
    }
  );
}

/** The authored ring, in the AUTHORED point order, as an SVG `points` string. Vertices are only
 * joined -- never sorted, rotated, normalized or recomputed (frozen plan §5.4). */
function polygonPoints(shape: StrategicShapeProjection): string {
  return shape.polygon.map(([x, y]) => `${x},${y}`).join(" ");
}

/**
 * The first route whose endpoints the projection does not actually contain, described in words.
 *
 * A route pointing at a theater that is not in the same response is an inconsistent map, not a
 * cosmetic problem: silently dropping the line would draw a map that looks complete and is not,
 * and drawing a zero-length stub would invent an edge nobody authored. Either way the player
 * would be shown a coherent-looking lie, so the screen refuses to draw any of it.
 */
function routeIntegrityProblem(
  map: StrategicMapProjection,
  theatersById: Map<string, StrategicTheaterProjection>,
): string | null {
  for (const route of map.routes) {
    const hasFrom = theatersById.has(route.from_theater_id);
    const hasTo = theatersById.has(route.to_theater_id);
    if (!hasFrom || !hasTo) {
      const missing = hasFrom ? route.to_theater_id : route.from_theater_id;
      return `This campaign's strategic map is inconsistent: a route between ${route.from_theater_id} and ${route.to_theater_id} refers to theater ${missing}, which the map does not contain. No part of the map is shown, because a partial map would misrepresent which theaters connect.`;
    }
  }
  return null;
}

// --- The screen ------------------------------------------------------------

export function StrategicMapScreen(_props: ScreenProps) {
  const { revision } = useSession();
  const generation = useGameGeneration();
  const map = useStrategicMap(generation.data, { enabled: revision !== null });
  const [selectedTheaterId, setSelectedTheaterId] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  // The loaded game changed (a new campaign started, or a different save
  // loaded) -- any previously selected theater id may no longer even exist
  // on the new map, so selection is cleared. Keyed on the SAME generation
  // value the query itself uses, so both invalidate together by
  // construction.
  useEffect(() => {
    setSelectedTheaterId(null);
  }, [generation.data]);

  if (map.isPending) {
    return <LoadingPanel label="Loading strategic map…" />;
  }
  if (map.isError) {
    return <ErrorPanel error={map.error} onRefresh={() => map.refetch()} />;
  }

  const data = map.data;
  const theatersById = new Map(data.theaters.map((theater) => [theater.theater_id, theater]));

  const integrityProblem = routeIntegrityProblem(data, theatersById);
  if (integrityProblem !== null) {
    return <ErrorPanel error={new Error(integrityProblem)} onRefresh={() => map.refetch()} />;
  }

  const ownerStyles = buildOwnerStyles(data);
  const selected = selectedTheaterId === null ? null : (theatersById.get(selectedTheaterId) ?? null);

  const outgoing = selected ? selected.outgoing_theater_ids.map((id) => theatersById.get(id)) : [];
  const incoming = selected ? selected.incoming_theater_ids.map((id) => theatersById.get(id)) : [];

  const announcement = selected
    ? `${selected.display_name}, ${selected.kind}, owned by ${selected.owner_display_name}, ${outgoing.length} routes out, ${incoming.length} routes in`
    : "";

  return (
    <div className="flex flex-col gap-6">
      <h2
        ref={headingRef}
        tabIndex={-1}
        className="font-[family-name:var(--font-display)] text-2xl text-parchment-100 focus:outline-none"
      >
        Strategic map
      </h2>

      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>

      <div className="flex flex-col gap-6 min-[900px]:flex-row">
        <div
          data-testid="strategic-map-visual"
          className="hidden min-[900px]:block min-[900px]:w-1/2 min-[900px]:shrink-0"
        >
          {/* The horizontal padding is not decoration: it is the gutter the labels overflow INTO
              (see the `overflow-visible` note on the SVG below), so a name anchored at the edge of
              the grid still lands inside this panel's own border. */}
          <div className="rounded border border-navy-800 bg-navy-900 px-16 py-6">
            <svg
              viewBox={MAP_VIEWBOX}
              aria-hidden="true"
              focusable="false"
              data-testid="strategic-map-svg"
              // `overflow-visible` matters: a theater whose authored `label_anchor` points outward
              // near the edge of the grid puts its label PAST the 0..10,000 viewBox -- "Arken
              // Coast" (anchor w at x=1,200) and "Vetruskan Frontier" (anchor e at x=8,200) both
              // do. An SVG viewport clips by default, which silently truncated those names to
              // "n Coast" and "Vetruskan F". The viewBox stays exactly the authored grid, as the
              // map's own coordinate system must; only the clipping goes.
              className="block h-auto w-full overflow-visible"
            >
              <defs>
                {FOREIGN_SHAPE_STYLES.map((style, index) => (
                  <pattern
                    key={style.hatchPatternId}
                    id={style.hatchPatternId}
                    patternUnits="userSpaceOnUse"
                    width={HATCH_TILE}
                    height={HATCH_TILE}
                    patternTransform={index === 0 ? "rotate(45)" : "rotate(135)"}
                  >
                    <path d={HATCH_TILE_PATH} stroke={HATCH_LINE} strokeWidth={HATCH_LINE_WIDTH} />
                  </pattern>
                ))}
                {/* `refX` deliberately sits outside the marker viewBox: it backs the arrowhead
                    off the line's own endpoint so the tip lands clear of the theater node drawn
                    on top of it, WITHOUT shortening the line -- the route's endpoints stay
                    exactly on the two authored centroids. Markers scale with stroke width, so
                    each viewBox unit here is `ROUTE_LINE_WIDTH` user units. */}
                <marker
                  id={ROUTE_ARROW_END_ID}
                  viewBox="0 0 12 12"
                  refX="26"
                  refY="6"
                  markerWidth="12"
                  markerHeight="12"
                  orient="auto"
                >
                  <path d="M 0 0 L 12 6 L 0 12 z" fill={ROUTE_LINE} />
                </marker>
                <marker
                  id={ROUTE_ARROW_START_ID}
                  viewBox="0 0 12 12"
                  refX="-14"
                  refY="6"
                  markerWidth="12"
                  markerHeight="12"
                  orient="auto"
                >
                  <path d="M 12 0 L 0 6 L 12 12 z" fill={ROUTE_LINE} />
                </marker>
              </defs>

              {/* Layer 1 -- base political polygons, in authored vertex order. */}
              <g data-layer="shapes">
                {data.shapes.map((shape) => (
                  <polygon
                    key={shape.shape_id}
                    data-shape-base={shape.shape_id}
                    data-owner-namespace={shape.owner_namespace}
                    data-owner-id={shape.owner_id}
                    points={polygonPoints(shape)}
                    fill={styleForShape(shape, ownerStyles).fill}
                    fillOpacity={SHAPE_FILL_OPACITY}
                    stroke={SHAPE_BORDER}
                    strokeWidth={SHAPE_BORDER_WIDTH}
                  />
                ))}
              </g>

              {/* Layer 2 -- hatch overlays. A separate polygon, because one SVG element takes one
                  fill paint: the solid owner colour and the hatch cannot both be that one fill. */}
              <g data-layer="hatch">
                {data.shapes
                  .filter((shape) => styleForShape(shape, ownerStyles).hatchPatternId !== null)
                  .map((shape) => (
                    <polygon
                      key={shape.shape_id}
                      data-shape-hatch={shape.shape_id}
                      points={polygonPoints(shape)}
                      fill={`url(#${styleForShape(shape, ownerStyles).hatchPatternId})`}
                      stroke="none"
                      pointerEvents="none"
                    />
                  ))}
              </g>

              {/* Layer 3 -- routes. One line per PROJECTED row: the contract already collapses a
                  reciprocal pair into a single row, so a two-way route is drawn once, with an
                  arrow at each end. A one-way route keeps its authored from -> to direction and
                  gets one arrow, at the end it actually points at. */}
              <g data-layer="routes">
                {data.routes.map((route) => {
                  const from = theatersById.get(route.from_theater_id);
                  const to = theatersById.get(route.to_theater_id);
                  if (!from || !to) {
                    return null; // unreachable: `routeIntegrityProblem` returned above
                  }
                  return (
                    <line
                      key={`${route.from_theater_id}->${route.to_theater_id}`}
                      data-route={`${route.from_theater_id}->${route.to_theater_id}`}
                      data-route-bidirectional={route.bidirectional ? "true" : "false"}
                      x1={from.centroid_x}
                      y1={from.centroid_y}
                      x2={to.centroid_x}
                      y2={to.centroid_y}
                      stroke={ROUTE_LINE}
                      strokeWidth={ROUTE_LINE_WIDTH}
                      markerEnd={`url(#${ROUTE_ARROW_END_ID})`}
                      markerStart={
                        route.bidirectional ? `url(#${ROUTE_ARROW_START_ID})` : undefined
                      }
                    />
                  );
                })}
              </g>

              {/* Layer 4 -- theater nodes. Circle = land, square = coastal. Clicking one writes
                  the SAME selection state the list writes; the nodes carry no tabindex, so they
                  add no keyboard stop of their own. */}
              <g data-layer="nodes">
                {data.theaters.map((theater) => {
                  const isSelected = theater.theater_id === selectedTheaterId;
                  const shared = {
                    "data-theater-node": theater.theater_id,
                    "data-theater-kind": theater.kind,
                    "data-centroid-x": String(theater.centroid_x),
                    "data-centroid-y": String(theater.centroid_y),
                    "data-selected": isSelected ? "true" : "false",
                    fill: isSelected ? SELECTED_FILL : NODE_FILL,
                    stroke: isSelected ? SELECTED_STROKE : NODE_STROKE,
                    strokeWidth: NODE_STROKE_WIDTH,
                    onClick: () => setSelectedTheaterId(theater.theater_id),
                    style: { cursor: "pointer" },
                  };
                  return theater.kind === "coastal" ? (
                    <rect
                      key={theater.theater_id}
                      {...shared}
                      transform={`translate(${theater.centroid_x} ${theater.centroid_y})`}
                      x={isSelected ? COASTAL_ORIGIN_SELECTED : COASTAL_ORIGIN}
                      y={isSelected ? COASTAL_ORIGIN_SELECTED : COASTAL_ORIGIN}
                      width={isSelected ? COASTAL_SIDE_SELECTED : COASTAL_SIDE}
                      height={isSelected ? COASTAL_SIDE_SELECTED : COASTAL_SIDE}
                    />
                  ) : (
                    <circle
                      key={theater.theater_id}
                      {...shared}
                      cx={theater.centroid_x}
                      cy={theater.centroid_y}
                      r={isSelected ? NODE_RADIUS_SELECTED : NODE_RADIUS}
                    />
                  );
                })}
              </g>

              {/* Layer 5 -- capital and selection markers, drawn over the nodes. Both are
                  decorative redundancy: capital status and the current selection are already
                  stated in words in the list and the detail panel. */}
              <g data-layer="markers">
                {data.theaters
                  .filter((theater) => theater.is_capital)
                  .map((theater) => (
                    <circle
                      key={theater.theater_id}
                      data-capital-marker={theater.theater_id}
                      cx={theater.centroid_x}
                      cy={theater.centroid_y}
                      r={CAPITAL_RING_RADIUS}
                      fill="none"
                      stroke={CAPITAL_MARKER_COLOR}
                      strokeWidth={CAPITAL_RING_WIDTH}
                      pointerEvents="none"
                    />
                  ))}
                {selected ? (
                  <circle
                    data-selection-marker={selected.theater_id}
                    cx={selected.centroid_x}
                    cy={selected.centroid_y}
                    r={SELECTION_RING_RADIUS}
                    fill="none"
                    stroke={SELECTED_STROKE}
                    strokeWidth={SELECTION_RING_WIDTH}
                    strokeDasharray={SELECTION_RING_DASH}
                    pointerEvents="none"
                  />
                ) : null}
              </g>

              {/* Layer 6 -- theater labels, placed per authored `label_anchor`. */}
              <g data-layer="labels">
                {data.theaters.map((theater) => {
                  const position = labelOffsetPosition(
                    theater.centroid_x,
                    theater.centroid_y,
                    theater.label_anchor,
                  );
                  return (
                    <text
                      key={theater.theater_id}
                      data-theater-label={theater.theater_id}
                      x={position.x}
                      y={position.y}
                      textAnchor={position.textAnchor}
                      dominantBaseline="middle"
                      fill={LABEL_COLOR}
                      fontSize={LABEL_FONT_SIZE}
                      pointerEvents="none"
                    >
                      {theater.display_name}
                    </text>
                  );
                })}
              </g>
            </svg>
          </div>

          {/* Real, non-SVG legend: the drawing's vocabulary stated in words, so no meaning rests
              on colour (or on the picture) alone. */}
          <dl
            data-testid="strategic-map-legend"
            className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded border border-navy-800 bg-navy-900 p-3 text-xs text-parchment-200/80"
          >
            <dt className="text-parchment-200/60">Your territory</dt>
            <dd>Solid fill, no hatching.</dd>
            <dt className="text-parchment-200/60">Foreign territory</dt>
            <dd>Darker fill with diagonal hatching; each foreign state hatches at its own angle.</dd>
            <dt className="text-parchment-200/60">Theater shape</dt>
            <dd>Circle for a land theater, square for a coastal one.</dd>
            <dt className="text-parchment-200/60">Routes</dt>
            <dd>
              A line per route: one arrowhead for a one-way route, an arrowhead at both ends for a
              two-way one. &ldquo;Routes out&rdquo; and &ldquo;Routes in&rdquo; below state the same
              directions in words.
            </dd>
            <dt className="text-parchment-200/60">Capital</dt>
            <dd>Ringed marker on the capital theater.</dd>
            <dt className="text-parchment-200/60">Selected</dt>
            <dd>Dashed ring, and the enlarged node.</dd>
          </dl>
        </div>

        <div className="flex flex-1 flex-col gap-6">
          <Panel title="Theaters">
            {data.theaters.length === 0 ? (
              <EmptyNote>This campaign has no theaters.</EmptyNote>
            ) : (
              <ul className="flex flex-col gap-2">
                {data.theaters.map((theater) => (
                  <li key={theater.theater_id}>
                    <button
                      type="button"
                      aria-pressed={selectedTheaterId === theater.theater_id}
                      onClick={() => setSelectedTheaterId(theater.theater_id)}
                      onFocus={() => setSelectedTheaterId(theater.theater_id)}
                      className="w-full rounded border border-navy-800 px-3 py-2 text-left text-sm aria-pressed:border-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                    >
                      {theaterListItemLabel(theater)}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          {selected ? (
            <Panel title={selected.display_name}>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-parchment-200/60">Kind</dt>
                <dd>{KIND_LABEL[selected.kind]}</dd>
                <dt className="text-parchment-200/60">Owner</dt>
                <dd>{selected.owner_display_name}</dd>
                <dt className="text-parchment-200/60">Capital</dt>
                <dd>{selected.is_capital ? "Yes" : "No"}</dd>
              </dl>

              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div>
                  <h4 className="mb-1 text-sm font-semibold text-parchment-100">Routes out</h4>
                  {outgoing.length === 0 ? (
                    <EmptyNote>No routes out.</EmptyNote>
                  ) : (
                    <ul className="text-sm">
                      {outgoing.map((theater, index) => (
                        // eslint-disable-next-line react/no-array-index-key -- ids may not resolve
                        <li key={theater?.theater_id ?? index}>
                          {theater?.display_name ?? selected.outgoing_theater_ids[index]}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div>
                  <h4 className="mb-1 text-sm font-semibold text-parchment-100">Routes in</h4>
                  {incoming.length === 0 ? (
                    <EmptyNote>No routes in.</EmptyNote>
                  ) : (
                    <ul className="text-sm">
                      {incoming.map((theater, index) => (
                        // eslint-disable-next-line react/no-array-index-key -- ids may not resolve
                        <li key={theater?.theater_id ?? index}>
                          {theater?.display_name ?? selected.incoming_theater_ids[index]}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </Panel>
          ) : (
            <Panel title="Theater detail">
              <EmptyNote>Select a theater to see its detail.</EmptyNote>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
