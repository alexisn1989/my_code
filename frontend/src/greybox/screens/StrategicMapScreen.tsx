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

// --- Map ground, frame and decoration --------------------------------------
//
// Chart furniture, and nothing more. The engine authors five theaters, a handful of directed
// routes and one open ring per sovereign; it authors no coastline, terrain, river, city, road or
// border. So this layer adds a ground, a frame, a decorative grid and a compass -- presentation
// that makes the authored content read as a strategic map -- and invents no geography whatsoever.
// The grid is coordinate paper, not a graticule of anything: it carries no degrees, no
// coordinates and no distances, and the screen states in words that it is schematic.

const SEA_FILL = "var(--color-navy-950)";
const GRID_LINE = "var(--color-navy-800)";
const GRID_LINE_WIDTH = 10;
/** Interior grid lines only, every 1,250 units. Literal positions: no arithmetic in this file. */
const GRID_POSITIONS = [1250, 2500, 3750, 5000, 6250, 7500, 8750] as const;

const FRAME_LINE = "var(--color-navy-800)";
const FRAME_WIDTH = 40;
const INSET_FRAME_LINE = "var(--color-gold-600)";
const INSET_FRAME_WIDTH = 12;
const INSET_FRAME_ORIGIN = 130;
const INSET_FRAME_SIDE = 9740;
/** Corner index ticks on the inset frame, drawn as one static path. */
const CORNER_TICKS_PATH = [
  "M 130 520 L 130 130 L 520 130",
  "M 9480 130 L 9870 130 L 9870 520",
  "M 9870 9480 L 9870 9870 L 9480 9870",
  "M 520 9870 L 130 9870 L 130 9480",
].join(" ");

/** Presentation only: the compass enters no state, no API payload and no mechanic. */
const COMPASS_RADIUS = 260;
const COMPASS_NORTH_POINTS = "0,-205 78,60 0,15 -78,60";
const COMPASS_SOUTH_POINTS = "0,205 78,-60 0,-15 -78,-60";
const COMPASS_LABEL_Y = -330;
const COMPASS_LABEL_SIZE = 190;

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

/** The AUTHORED BOUNDARY of a political shape -- not a coastline. The engine authors a political
 * outline per sovereign and says nothing about where land meets water, so neither does this. The
 * outer stroke is a darker halo that separates the shape from the ground; the inner one is the
 * boundary itself. */
const SHAPE_OUTLINE_HALO = "var(--color-navy-950)";
const SHAPE_OUTLINE_HALO_WIDTH = 90;
const SHAPE_OUTLINE_PLAYER = "var(--color-gold-500)";
const SHAPE_OUTLINE_FOREIGN = "var(--color-parchment-200)";
const SHAPE_OUTLINE_WIDTH = 26;
const SHAPE_OUTLINE_OPACITY = 0.75;
const SHAPE_FILL_OPACITY = 0.62;

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

// A theater marker is a neutral map location symbol: a dark disc with a bright outer ring. Land
// and coastal differ by an inner glyph (a dot for land, a small square for coastal), which is a
// restrained difference that never becomes the only carrier of the fact -- the list row and the
// detail panel both say "Land" or "Coastal" in words.
const NODE_FILL = "var(--color-navy-950)";
const NODE_RING = "var(--color-parchment-100)";
const NODE_RING_WIDTH = 26;
const NODE_RADIUS = 130;
const NODE_RADIUS_SELECTED = 200;
const NODE_GLYPH_RADIUS = 46;
const NODE_GLYPH_SQUARE = 74;
const NODE_GLYPH_SQUARE_ORIGIN = -37;
/** A generous, invisible pointer target. It is centred on the very same authored centroid as the
 * marker, so an easier click changes nothing about the coordinate the node represents. */
const NODE_HIT_RADIUS = 380;

const SELECTED_FILL = "var(--color-gold-500)";
const SELECTED_STROKE = "var(--color-gold-500)";
const SELECTION_RING_RADIUS = 430;
const SELECTION_RING_WIDTH = 26;
const SELECTION_RING_DASH = "78 62";

/** A five-point star on the capital, drawn once as a static shape and translated to the
 * authoritative capital theater's own centroid -- so the star introduces no coordinate of its
 * own. Capital status is stated in words as well; the star is never its only representation. */
const CAPITAL_MARKER_COLOR = "var(--color-gold-500)";
const CAPITAL_STAR_POINTS =
  "0,-210 49,-68 200,-65 80,26 123,170 0,84 -123,170 -80,26 -200,-65 -49,-68";
const CAPITAL_STAR_OUTLINE = "var(--color-navy-950)";
const CAPITAL_STAR_OUTLINE_WIDTH = 34;

const LABEL_COLOR = "var(--color-parchment-100)";
const LABEL_HALO = "var(--color-navy-950)";
const LABEL_HALO_WIDTH = 60;
const LABEL_FONT_SIZE = 250;
const LABEL_LETTER_SPACING = 26;

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
            {/* Real, accessible text -- not SVG -- so the map's own caveat is never trapped inside
                the aria-hidden picture. */}
            <p className="font-[family-name:var(--font-display)] text-sm uppercase tracking-[0.2em] text-parchment-100">
              Strategic theater map
            </p>
            <p
              data-testid="strategic-map-caveat"
              className="mb-4 text-xs italic text-parchment-200/60"
            >
              Schematic — not to geographic scale
            </p>
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

              {/* Layer 0 -- the ground, its frame and its decorative coordinate grid. Chart
                  furniture only: the grid is ruled paper, carrying no degrees, no coordinates and
                  no distances, and the caption above says in words that the map is schematic. */}
              <g data-layer="ground">
                <rect
                  data-map-sea="true"
                  x={0}
                  y={0}
                  width={10000}
                  height={10000}
                  fill={SEA_FILL}
                />
                <g data-map-graticule="true">
                  {GRID_POSITIONS.map((position) => (
                    <line
                      key={`v-${position}`}
                      data-grid-line="vertical"
                      x1={position}
                      y1={0}
                      x2={position}
                      y2={10000}
                      stroke={GRID_LINE}
                      strokeWidth={GRID_LINE_WIDTH}
                    />
                  ))}
                  {GRID_POSITIONS.map((position) => (
                    <line
                      key={`h-${position}`}
                      data-grid-line="horizontal"
                      x1={0}
                      y1={position}
                      x2={10000}
                      y2={position}
                      stroke={GRID_LINE}
                      strokeWidth={GRID_LINE_WIDTH}
                    />
                  ))}
                </g>
                <rect
                  data-map-frame="outer"
                  x={0}
                  y={0}
                  width={10000}
                  height={10000}
                  fill="none"
                  stroke={FRAME_LINE}
                  strokeWidth={FRAME_WIDTH}
                />
                <rect
                  data-map-frame="inset"
                  x={INSET_FRAME_ORIGIN}
                  y={INSET_FRAME_ORIGIN}
                  width={INSET_FRAME_SIDE}
                  height={INSET_FRAME_SIDE}
                  fill="none"
                  stroke={INSET_FRAME_LINE}
                  strokeOpacity={0.35}
                  strokeWidth={INSET_FRAME_WIDTH}
                />
                <path
                  data-map-frame="corners"
                  d={CORNER_TICKS_PATH}
                  fill="none"
                  stroke={INSET_FRAME_LINE}
                  strokeOpacity={0.6}
                  strokeWidth={INSET_FRAME_WIDTH}
                />
              </g>

              {/* Layer 1 -- the authored political shapes, in authored vertex order. Two strokes:
                  a dark halo that lifts the shape off the ground, and the authored boundary
                  itself. Neither is a coastline -- the engine authors a political outline and
                  says nothing about land meeting water. */}
              <g data-layer="shapes">
                {data.shapes.map((shape) => (
                  <polygon
                    key={`halo-${shape.shape_id}`}
                    data-shape-halo={shape.shape_id}
                    points={polygonPoints(shape)}
                    fill="none"
                    stroke={SHAPE_OUTLINE_HALO}
                    strokeWidth={SHAPE_OUTLINE_HALO_WIDTH}
                    strokeLinejoin="round"
                  />
                ))}
                {data.shapes.map((shape) => (
                  <polygon
                    key={shape.shape_id}
                    data-shape-base={shape.shape_id}
                    data-owner-namespace={shape.owner_namespace}
                    data-owner-id={shape.owner_id}
                    points={polygonPoints(shape)}
                    fill={styleForShape(shape, ownerStyles).fill}
                    fillOpacity={SHAPE_FILL_OPACITY}
                    stroke={
                      shape.owner_namespace === FOREIGN_NAMESPACE
                        ? SHAPE_OUTLINE_FOREIGN
                        : SHAPE_OUTLINE_PLAYER
                    }
                    strokeOpacity={SHAPE_OUTLINE_OPACITY}
                    strokeWidth={SHAPE_OUTLINE_WIDTH}
                    strokeLinejoin="round"
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
                  return (
                    <g
                      key={theater.theater_id}
                      data-theater-node={theater.theater_id}
                      data-theater-kind={theater.kind}
                      data-centroid-x={String(theater.centroid_x)}
                      data-centroid-y={String(theater.centroid_y)}
                      data-selected={isSelected ? "true" : "false"}
                      transform={`translate(${theater.centroid_x} ${theater.centroid_y})`}
                      onClick={() => setSelectedTheaterId(theater.theater_id)}
                      style={{ cursor: "pointer" }}
                    >
                      {/* Invisible, generous pointer target on the very same centroid: an easier
                          click, not a different coordinate. */}
                      <circle r={NODE_HIT_RADIUS} fill="transparent" />
                      <circle
                        data-node-marker={theater.theater_id}
                        r={isSelected ? NODE_RADIUS_SELECTED : NODE_RADIUS}
                        fill={NODE_FILL}
                        stroke={isSelected ? SELECTED_STROKE : NODE_RING}
                        strokeWidth={NODE_RING_WIDTH}
                      />
                      {/* Kind glyph: a dot for a land theater, a small square for a coastal one.
                          Restrained, and never the only carrier -- the list row and the detail
                          panel both say "Land" or "Coastal" in words. */}
                      {theater.kind === "coastal" ? (
                        <rect
                          data-node-glyph="coastal"
                          x={NODE_GLYPH_SQUARE_ORIGIN}
                          y={NODE_GLYPH_SQUARE_ORIGIN}
                          width={NODE_GLYPH_SQUARE}
                          height={NODE_GLYPH_SQUARE}
                          fill={isSelected ? SELECTED_FILL : NODE_RING}
                        />
                      ) : (
                        <circle
                          data-node-glyph="land"
                          r={NODE_GLYPH_RADIUS}
                          fill={isSelected ? SELECTED_FILL : NODE_RING}
                        />
                      )}
                    </g>
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
                    <polygon
                      key={theater.theater_id}
                      data-capital-marker={theater.theater_id}
                      points={CAPITAL_STAR_POINTS}
                      transform={`translate(${theater.centroid_x} ${theater.centroid_y})`}
                      fill={CAPITAL_MARKER_COLOR}
                      stroke={CAPITAL_STAR_OUTLINE}
                      strokeWidth={CAPITAL_STAR_OUTLINE_WIDTH}
                      strokeLinejoin="round"
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
                      stroke={LABEL_HALO}
                      strokeWidth={LABEL_HALO_WIDTH}
                      fontSize={LABEL_FONT_SIZE}
                      pointerEvents="none"
                      // `paint-order="stroke"` puts the halo UNDER the glyphs, so the stroke
                      // reads as a backing plate that keeps a name legible over hatching or a
                      // route line, instead of thickening the letters themselves. Set as the SVG
                      // presentation ATTRIBUTE rather than an inline style: jsdom's CSS engine
                      // does not implement the `paint-order` property and silently drops it from
                      // a style object, which would leave this untestable.
                      paintOrder="stroke"
                      style={{
                        fontFamily: "var(--font-display)",
                        textTransform: "uppercase",
                        letterSpacing: LABEL_LETTER_SPACING,
                      }}
                    >
                      {theater.display_name}
                    </text>
                  );
                })}
              </g>

              {/* Layer 7 -- the compass. Presentation only: it enters no state, no API payload
                  and no mechanic, and it carries no coordinate, degree or distance. */}
              <g data-map-compass="true" transform="translate(9250 1150)" pointerEvents="none">
                <circle
                  r={COMPASS_RADIUS}
                  fill={SEA_FILL}
                  fillOpacity={0.85}
                  stroke={NODE_RING}
                  strokeOpacity={0.35}
                  strokeWidth={GRID_LINE_WIDTH}
                />
                <polygon points={COMPASS_NORTH_POINTS} fill={NODE_RING} />
                <polygon points={COMPASS_SOUTH_POINTS} fill={NODE_RING} fillOpacity={0.28} />
                <text
                  x={0}
                  y={COMPASS_LABEL_Y}
                  textAnchor="middle"
                  fontSize={COMPASS_LABEL_SIZE}
                  fill={LABEL_COLOR}
                  stroke={LABEL_HALO}
                  strokeWidth={LABEL_HALO_WIDTH}
                  paintOrder="stroke"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  N
                </text>
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
            <dd>Gold fill, solid, with no hatching.</dd>
            <dt className="text-parchment-200/60">Foreign territory</dt>
            <dd>
              A darker fill under diagonal hatching; each foreign state keeps its own fill and its
              own hatch angle.
            </dd>
            <dt className="text-parchment-200/60">Hatching</dt>
            <dd>Marks territory that is not yours. Ownership is also named in the list below.</dd>
            <dt className="text-parchment-200/60">One-way route</dt>
            <dd>
              <span aria-hidden="true">→</span> A line with a single arrowhead, at the end it leads
              to.
            </dd>
            <dt className="text-parchment-200/60">Two-way route</dt>
            <dd>
              <span aria-hidden="true">↔</span> A line with an arrowhead at both ends.
              &ldquo;Routes out&rdquo; and &ldquo;Routes in&rdquo; state every direction in words.
            </dd>
            <dt className="text-parchment-200/60">Theater marker</dt>
            <dd>
              A ringed dot: a solid centre for a land theater, a small square for a coastal one.
            </dd>
            <dt className="text-parchment-200/60">Capital</dt>
            <dd>
              <span aria-hidden="true">★</span> A star on the capital theater, which the detail
              panel also states as &ldquo;Capital: Yes&rdquo;.
            </dd>
            <dt className="text-parchment-200/60">Selected theater</dt>
            <dd>A dashed gold ring and an enlarged marker. Selecting only inspects.</dd>
            <dt className="text-parchment-200/60">Grid and compass</dt>
            <dd>
              Drawn to read as a map. The layout is schematic: it shows which theaters connect, not
              where they are.
            </dd>
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
