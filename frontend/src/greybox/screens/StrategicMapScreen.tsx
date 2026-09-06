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
import { useGameGeneration, useMilitary, useStrategicMap } from "../../api/queries";
import { useDraftStore } from "../../state/draft";
import {
  formationMarkerPlacements,
  formationOverflowLabel,
  formationSelectedAnnouncement,
  labelOffsetPosition,
  orderStagedAnnouncement,
  paletteIndex,
  plannedRouteAnnouncement,
} from "../../format/format";
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
/** Formation marker sizing, in authored grid units like every size in this file. The radius is
 * comfortably under the fan's slot separation, so two markers on adjacent slots never touch. */
const FORMATION_MARKER_RADIUS = 190;
const FORMATION_MARKER_RING_WIDTH = 26;
const FORMATION_MARKER_FONT_SIZE = 210;
const NODE_RADIUS_SELECTED = 200;
const NODE_GLYPH_RADIUS = 46;
const NODE_GLYPH_SQUARE = 74;
const NODE_GLYPH_SQUARE_ORIGIN = -37;
/** A generous, invisible pointer target. It is centred on the very same authored centroid as the
 * marker, so an easier click changes nothing about the coordinate the node represents. */
const NODE_HIT_RADIUS = 380;

const SELECTED_FILL = "var(--color-gold-500)";
const SELECTED_STROKE = "var(--color-gold-500)";
const FORMATION_MARKER_FILL = "var(--color-navy-800)";
const FORMATION_MARKER_RING = "var(--color-gold-500)";
const FORMATION_MARKER_TEXT = "var(--color-parchment-100)";
const PLANNED_ROUTE_WIDTH = 46;
const PLANNED_ROUTE_CASING_WIDTH = 110;
const PLANNED_ROUTE_DASH = "150 110";
/** The dashed gold ring that marks a selection. Never the only carrier: the Formations list names
 * the selection in words, and the live region announces it. */
const SELECTED_DASH = "120 90";
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

/**
 * Why a destination cannot be ordered, in words (frozen plan §9.4).
 *
 * Every ineligible destination is LISTED with its reason rather than omitted, and no reason is
 * ever carried by colour alone. Both foreign codes read as ownership failures and neither is ever
 * described as merely unreachable, so no wording can suggest that authoring a route would
 * authorize foreign entry.
 *
 * There is deliberately no "reachable only through another theater" sentence for the two-hop case.
 * Producing it needs graph traversal this one-edge slice otherwise never performs, and running a
 * search purely to improve an error message would smuggle multi-hop reachability into a slice that
 * forbids it.
 */
function ineligibilityReason(code: string | null | undefined, ownerName: string | null): string {
  switch (code) {
    case "destination_not_player_owned":
      return ownerName === null
        ? "Not eligible — foreign territory; foreign entry is unavailable."
        : `Not eligible — owned by ${ownerName}; foreign entry is unavailable.`;
    case "destination_not_directly_reachable":
      return "Not eligible — no direct outgoing LAND route from this theater.";
    case "destination_is_origin":
      return "Not eligible — this formation is already here.";
    default:
      // Never reached for a code this build emits; a visible sentence beats a blank row if a
      // future code arrives before its wording does.
      return "Not eligible.";
  }
}

export function StrategicMapScreen(_props: ScreenProps) {
  const { revision } = useSession();
  const generation = useGameGeneration();
  const map = useStrategicMap(generation.data, { enabled: revision !== null });
  // Two queries, two lifetimes: campaign-static geography above, per-turn positions here. The
  // military view is keyed on `revision`, so a resolve refetches it and never refetches the map.
  const military = useMilitary(revision, { enabled: revision !== null });
  const [enlarged, setEnlarged] = useState(false);
  // The map stages an order; it never resolves the turn. There is deliberately no `resolving`
  // state here -- resolution stays exactly where it already is, on the Decisions screen, and this
  // screen would otherwise become a second competing way to end a turn.
  const [selectedFormationId, setSelectedFormationId] = useState<string | null>(null);
  const [selectedDestinationId, setSelectedDestinationId] = useState<string | null>(null);
  const [movementAnnouncement, setMovementAnnouncement] = useState("");
  const stagedOrder = useDraftStore((state) => state.movement);
  const setMovementOrder = useDraftStore((state) => state.setMovementOrder);
  const clearMovementOrder = useDraftStore((state) => state.clearMovementOrder);
  const destinationHeadingRef = useRef<HTMLHeadingElement>(null);
  const reviewHeadingRef = useRef<HTMLHeadingElement>(null);
  const stagedSummaryRef = useRef<HTMLDivElement>(null);
  const formationButtonRefs = useRef(new Map<string, HTMLButtonElement | null>());
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
    setSelectedFormationId(null);
    setSelectedDestinationId(null);
  }, [generation.data]);

  // Focus follows the machine, and never lands on a control the player cannot use: with no
  // eligible destination the heading takes focus rather than an empty list.
  useEffect(() => {
    if (selectedFormationId !== null && selectedDestinationId === null) {
      destinationHeadingRef.current?.focus();
    }
  }, [selectedFormationId, selectedDestinationId]);

  useEffect(() => {
    if (selectedDestinationId !== null) {
      reviewHeadingRef.current?.focus();
    }
  }, [selectedDestinationId]);

  if (map.isPending) {
    return <LoadingPanel label="Loading strategic map…" />;
  }
  if (map.isError) {
    return <ErrorPanel error={map.error} onRefresh={() => map.refetch()} />;
  }

  const data = map.data;
  const theatersById = new Map(data.theaters.map((theater) => [theater.theater_id, theater]));
  // Formation ids grouped by where they stand, in the canonical order the server sent them.
  // Never re-sorted here: the picture and the textual list must agree, and the server already
  // decided that order.
  const formationsByTheater = new Map<string, string[]>();
  for (const formation of military.data?.formations ?? []) {
    const existing = formationsByTheater.get(formation.location_theater_id);
    if (existing === undefined) {
      formationsByTheater.set(formation.location_theater_id, [formation.formation_id]);
    } else {
      existing.push(formation.formation_id);
    }
  }

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

  // --- movement interaction -------------------------------------------------
  const formations = military.data?.formations ?? [];
  const selectedFormation =
    formations.find((formation) => formation.formation_id === selectedFormationId) ?? null;
  const eligibleDestinations =
    selectedFormation?.destination_options.filter((option) => option.eligible) ?? [];
  const selectedDestination =
    selectedFormation?.destination_options.find(
      (option) => option.theater_id === selectedDestinationId,
    ) ?? null;
  const stagedFormation =
    stagedOrder === null
      ? null
      : (formations.find((f) => f.formation_id === stagedOrder.formationId) ?? null);

  // Drawn only once a destination is chosen: neither `idle` nor `formationSelected` shows a route
  // or an arrowhead, because there is no direction to state yet.
  const plannedRoute =
    selectedFormation === null || selectedDestinationId === null
      ? null
      : (() => {
          const from = theatersById.get(selectedFormation.location_theater_id);
          const to = theatersById.get(selectedDestinationId);
          return from === undefined || to === undefined ? null : { from, to };
        })();

  function theaterName(theaterId: string): string {
    return theatersById.get(theaterId)?.display_name ?? theaterId;
  }

  function selectFormation(formationId: string): void {
    setSelectedFormationId(formationId);
    setSelectedDestinationId(null);
    const formation = formations.find((f) => f.formation_id === formationId);
    const count = formation?.destination_options.filter((o) => o.eligible).length ?? 0;
    setMovementAnnouncement(
      formation === undefined
        ? ""
        : formationSelectedAnnouncement(
            formation.display_name,
            formation.location_display_name,
            count,
          ),
    );
  }

  function selectDestination(option: { theater_id: string; display_name: string }): void {
    setSelectedDestinationId(option.theater_id);
    setMovementAnnouncement(
      selectedFormation === null
        ? ""
        : plannedRouteAnnouncement(selectedFormation.location_display_name, option.display_name),
    );
  }

  function stageOrder(): void {
    if (selectedFormation === null || selectedDestination === null) {
      return;
    }
    setMovementOrder(selectedFormation.formation_id, selectedDestination.theater_id);
    setMovementAnnouncement(
      orderStagedAnnouncement(selectedFormation.display_name, selectedDestination.display_name),
    );
    // Control returns to the shared turn draft: the map goes back to idle with the staged order
    // visible, and the player may add a budget, an amendment or investments as usual.
    setSelectedFormationId(null);
    setSelectedDestinationId(null);
  }

  function removeStagedOrder(): void {
    clearMovementOrder();
    setMovementAnnouncement("Movement order removed. Nothing has moved.");
    setSelectedFormationId(null);
    setSelectedDestinationId(null);
  }

  function escapeFromMovement(): void {
    if (selectedDestinationId !== null) {
      setSelectedDestinationId(null);
      return;
    }
    if (selectedFormationId !== null) {
      const returning = selectedFormationId;
      setSelectedFormationId(null);
      formationButtonRefs.current.get(returning)?.focus();
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <h2
        ref={headingRef}
        tabIndex={-1}
        className="font-[family-name:var(--font-display)] text-2xl text-parchment-100 focus:outline-none"
      >
        Strategic map
      </h2>

      {/* M0's existing polite region, reused rather than duplicated -- a second live region would
          compete with this one for a screen reader's attention. */}
      <div role="status" aria-live="polite" className="sr-only">
        {movementAnnouncement === "" ? announcement : movementAnnouncement}
      </div>

      <div className="flex flex-col gap-6 min-[900px]:flex-row">
        <div
          data-testid="strategic-map-visual"
          data-enlarged={enlarged ? "true" : "false"}
          // Enlarged mode is the SAME authored `0 0 10000 10000` viewBox and the same geometry,
          // given more of the row -- more pixels per grid unit, nothing rescaled or recentred.
          // There is deliberately no zoom or pan in this slice; if a real browser walkthrough
          // shows this is still not enough for hit targets or label legibility, that evidence
          // reopens the question, not a preference.
          className={
            enlarged
              ? "hidden min-[900px]:block min-[900px]:w-[63%] min-[900px]:shrink-0"
              : "hidden min-[900px]:block min-[900px]:w-1/2 min-[900px]:shrink-0"
          }
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
            {/* A real button, not a decoration on the aria-hidden picture: the map itself carries
                no keyboard stops, so this is the one control the enlarged mode needs. */}
            <button
              type="button"
              data-testid="strategic-map-enlarge-toggle"
              aria-pressed={enlarged}
              onClick={() => setEnlarged(!enlarged)}
              className="mb-4 rounded border border-navy-800 px-3 py-1 text-xs text-parchment-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
            >
              {enlarged ? "Reduce map" : "Enlarge map"}
            </button>
            <svg
              viewBox={MAP_VIEWBOX}
              aria-hidden="true"
              focusable="false"
              data-testid="strategic-map-svg"
              // `overflow-visible` matters: a theater whose authored `label_anchor` points outward
              // near the edge of the grid puts its label PAST the 0..10,000 viewBox -- "Port
              // District" (anchor w at x=2,100) runs left of x=0 once its 13 characters are laid
              // out at this font size. An SVG viewport clips by default, which silently truncated
              // such names mid-word. The viewBox stays exactly the authored grid, as the map's own
              // coordinate system must; only the clipping goes.
              //
              // The height cap is what keeps the framed map above the fold. The 500px comes from
              // measurement, not estimation: at 1440x900 in a real browser, 326px of application
              // chrome sits above this column and 156px of non-SVG content sits inside it (the
              // heading, the caveat, the panel's padding, and the collapsed legend disclosure),
              // leaving 18px of margin. The cap only binds on a short viewport: the square is
              // 442px wide in this column, so from about 942px of viewport height the width binds
              // first and this stops applying rather than stretching anything. Measured: 400px
              // tall at 1440x900, 442px at both 1440x1080 and 1440x1200.
              //
              // The SVG keeps `w-full`, so `preserveAspectRatio` letterboxes the square drawing
              // inside the capped box rather than distorting it -- the authored grid is never
              // cropped or stretched to make the layout fit.
              className="block h-auto max-h-[calc(100dvh-500px)] w-full overflow-visible"
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
                {/* The planned order's single arrowhead. SOLID, not dashed, and carrying the same
                    casing treatment as its line, so it stays legible where it approaches the
                    destination's ring. */}
                <marker
                  id="planned-route-arrowhead"
                  viewBox="0 0 12 12"
                  refX="26"
                  refY="6"
                  markerWidth="12"
                  markerHeight="12"
                  orient="auto"
                >
                  <path
                    data-planned-route-arrowhead=""
                    d="M 0 0 L 12 6 L 0 12 z"
                    fill={SELECTED_STROKE}
                    stroke={NODE_FILL}
                    strokeWidth="1"
                  />
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

              {/* Layer 5b -- formation markers (Military Movement, commit 7).
                  Drawn AFTER the nodes so a marker is never hidden behind one, and before the
                  labels so a name still wins where they meet. Positions come from
                  `formationMarkerPlacements`; this component computes no coordinate of its own
                  (`format-boundary.test.ts` walks its real AST and fails on arithmetic here). */}
              <g data-layer="formations">
                {formationsByTheater.size === 0
                  ? null
                  : data.theaters.map((theater) => {
                      const ids = formationsByTheater.get(theater.theater_id) ?? [];
                      if (ids.length === 0) {
                        return null;
                      }
                      return (
                        <g key={theater.theater_id} data-theater-formations={theater.theater_id}>
                          {formationMarkerPlacements(
                            theater.centroid_x,
                            theater.centroid_y,
                            theater.label_anchor,
                            ids,
                          ).map((placement, slot) => {
                            // A clustered selection must never be invisible on the map: when the
                            // selected formation is one of the ones this control hides, the
                            // control itself takes the selected styling. The picture is
                            // aria-hidden, so the ACCESSIBLE statement of the same fact is the
                            // Formations list, which never clusters and always names every
                            // formation individually.
                            const hidesSelection =
                              placement.formationId === null &&
                              selectedFormationId !== null &&
                              ids.slice(slot).includes(selectedFormationId);
                            const isSelectedMarker =
                              placement.formationId !== null &&
                              placement.formationId === selectedFormationId;
                            return (
                            <g
                              key={placement.formationId ?? "overflow"}
                              data-formation-marker={placement.formationId ?? "overflow"}
                              data-hidden-count={String(placement.hiddenCount)}
                              data-marker-x={String(placement.x)}
                              data-marker-y={String(placement.y)}
                              data-marker-selected={isSelectedMarker || hidesSelection ? "true" : "false"}
                              transform={`translate(${placement.x} ${placement.y})`}
                            >
                              <circle
                                r={FORMATION_MARKER_RADIUS}
                                fill={FORMATION_MARKER_FILL}
                                stroke={
                                  isSelectedMarker || hidesSelection
                                    ? SELECTED_STROKE
                                    : FORMATION_MARKER_RING
                                }
                                strokeDasharray={
                                  isSelectedMarker || hidesSelection ? SELECTED_DASH : undefined
                                }
                                strokeWidth={FORMATION_MARKER_RING_WIDTH}
                              />
                              {placement.formationId === null ? (
                                <text
                                  data-formation-overflow-label=""
                                  textAnchor="middle"
                                  dominantBaseline="central"
                                  fill={FORMATION_MARKER_TEXT}
                                  fontSize={FORMATION_MARKER_FONT_SIZE}
                                  pointerEvents="none"
                                >
                                  {formationOverflowLabel(placement.hiddenCount)}
                                </text>
                              ) : null}
                            </g>
                            );
                          })}
                        </g>
                      );
                    })}
              </g>

              {/* Layer 5c -- the planned route (frozen plan §9.5.1). Drawn AFTER the nodes and
                  markers so the reachability rings and discs cannot obscure it: a casing stroke
                  wide enough that nothing underneath shows through, the gold dashed foreground,
                  and ONE solid arrowhead at the DESTINATION end. A movement has one direction;
                  two arrowheads would state a reciprocal relationship the order does not have.
                  Origin and destination come from the authoritative projection, never from screen
                  geometry or the order the player clicked. */}
              {plannedRoute === null ? null : (
                <g data-layer="planned-route" data-planned-route="">
                  <line
                    data-planned-route-casing=""
                    x1={plannedRoute.from.centroid_x}
                    y1={plannedRoute.from.centroid_y}
                    x2={plannedRoute.to.centroid_x}
                    y2={plannedRoute.to.centroid_y}
                    stroke={NODE_FILL}
                    strokeWidth={PLANNED_ROUTE_CASING_WIDTH}
                    strokeLinecap="round"
                  />
                  <line
                    data-planned-route-line=""
                    x1={plannedRoute.from.centroid_x}
                    y1={plannedRoute.from.centroid_y}
                    x2={plannedRoute.to.centroid_x}
                    y2={plannedRoute.to.centroid_y}
                    stroke={SELECTED_STROKE}
                    strokeWidth={PLANNED_ROUTE_WIDTH}
                    strokeDasharray={PLANNED_ROUTE_DASH}
                    markerEnd="url(#planned-route-arrowhead)"
                  />
                </g>
              )}

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
              on colour (or on the picture) alone.

              It is a disclosure, and collapsed by default, because at 1440x900 the framed map and
              the nine expanded definitions cannot both clear the fold: the column has 574px to
              spend and the open legend alone wants 298px, which would leave a square map about
              162px tall -- roughly 4px lettering, since a label is LABEL_FONT_SIZE/10,000 of the
              rendered height. Collapsing costs nothing that is not recoverable by one keypress on
              the summary, and the definitions describe a picture that is `aria-hidden` anyway:
              ownership, routes and capital status are each stated again in the theater list and
              the detail panel, which is where a screen-reader user meets them regardless. */}
          <details className="mt-3 rounded border border-navy-800 bg-navy-900 p-3">
            <summary className="cursor-pointer text-xs text-parchment-200/70">Map legend</summary>
            <dl
              data-testid="strategic-map-legend"
              className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-parchment-200/80"
            >
              <dt className="text-parchment-200/60">Your territory</dt>
              <dd>Gold fill, solid, with no hatching.</dd>
              <dt className="text-parchment-200/60">Foreign territory</dt>
              <dd>
                A darker fill under diagonal hatching; each foreign state keeps its own fill and
                its own hatch angle.
              </dd>
              <dt className="text-parchment-200/60">Hatching</dt>
              <dd>Marks territory that is not yours. Ownership is also named in the list below.</dd>
              <dt className="text-parchment-200/60">One-way route</dt>
              <dd>
                <span aria-hidden="true">→</span> A line with a single arrowhead, at the end it
                leads to.
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
                Drawn to read as a map. The layout is schematic: it shows which theaters connect,
                not where they are.
              </dd>
            </dl>
          </details>
        </div>

        <div className="flex flex-1 flex-col gap-6">
          {/* Formations: the ACCESSIBLE SOURCE OF TRUTH, and it never clusters. The picture may
              cluster above six per theater; this list always carries every formation, so no
              formation becomes unreachable because its icon was clustered, and the whole
              interaction works in the narrow layout where no SVG renders at all. */}
          <Panel title="Formations">
            {formations.length === 0 ? (
              <EmptyNote>This campaign has no formations.</EmptyNote>
            ) : (
              <div
                data-testid="movement-panel"
                data-movement-state={
                  selectedFormation === null
                    ? "idle"
                    : selectedDestination === null
                      ? "formationSelected"
                      : "destinationSelected"
                }
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    event.stopPropagation();
                    escapeFromMovement();
                  }
                }}
              >
                <ul className="flex flex-col gap-2">
                  {formations.map((formation) => {
                    const staged = stagedOrder?.formationId === formation.formation_id;
                    return (
                      <li key={formation.formation_id}>
                        <button
                          type="button"
                          ref={(node) => {
                            formationButtonRefs.current.set(formation.formation_id, node);
                          }}
                          data-formation-option={formation.formation_id}
                          aria-pressed={selectedFormationId === formation.formation_id}
                          onClick={() => selectFormation(formation.formation_id)}
                          className="w-full rounded border border-navy-800 px-3 py-2 text-left text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500 aria-pressed:border-gold-500"
                        >
                          <span className="block text-parchment-100">{formation.display_name}</span>
                          <span className="block text-xs text-parchment-200/70">
                            {formation.location_display_name}
                          </span>
                          {/* Derived copy, never stored state: no `status` field exists on a
                              formation and none is added. Both lines are computed from the
                              authoritative location and the shared draft. */}
                          <span
                            data-formation-status={formation.formation_id}
                            className="block text-xs text-parchment-200/70"
                          >
                            {staged && stagedOrder !== null
                              ? `Order staged: → ${theaterName(stagedOrder.destinationTheaterId)}`
                              : "In position"}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>

                {selectedFormation === null ? null : (
                  <div className="mt-4 border-t border-navy-800 pt-4">
                    <h3
                      ref={destinationHeadingRef}
                      tabIndex={-1}
                      data-testid="destination-heading"
                      className="text-sm uppercase tracking-[0.15em] text-parchment-100 focus:outline-none"
                    >
                      Destinations for {selectedFormation.display_name}
                    </h3>
                    {eligibleDestinations.length === 0 ? (
                      // Reachable from a valid state and designed rather than assumed away: a
                      // player theater reached only by an incoming route from the capital has no
                      // outgoing row of its own. No review and no confirmation control are
                      // rendered -- there is nothing to review, and a disabled Confirm would imply
                      // an order is one step away.
                      <p data-testid="no-eligible-destinations" className="mt-2 text-sm text-parchment-200/80">
                        This formation has no eligible movement destination this turn.
                      </p>
                    ) : null}
                    <ul className="mt-2 flex flex-col gap-1">
                      {selectedFormation.destination_options.map((option) => (
                        <li key={option.theater_id}>
                          {option.eligible ? (
                            <button
                              type="button"
                              data-destination-option={option.theater_id}
                              aria-pressed={selectedDestinationId === option.theater_id}
                              onClick={() => selectDestination(option)}
                              className="w-full rounded border border-dashed border-gold-500 px-3 py-1 text-left text-sm text-parchment-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                            >
                              {option.display_name} — eligible
                            </button>
                          ) : (
                            <p
                              data-destination-ineligible={option.theater_id}
                              className="px-3 py-1 text-sm text-parchment-200/50"
                            >
                              {option.display_name} — {ineligibilityReason(
                                option.ineligible_reason_code,
                                theatersById.get(option.theater_id)?.owner_display_name ?? null,
                              )}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {selectedFormation !== null && selectedDestination !== null ? (
                  <div className="mt-4 rounded border border-gold-600 p-3">
                    <h3
                      ref={reviewHeadingRef}
                      tabIndex={-1}
                      data-testid="order-review-heading"
                      className="text-sm uppercase tracking-[0.15em] text-parchment-100 focus:outline-none"
                    >
                      Review movement order
                    </h3>
                    {/* From and To in words: the arrowhead on the map is never the sole carrier
                        of direction. */}
                    <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 text-sm">
                      <dt className="text-parchment-200/70">From</dt>
                      <dd data-testid="order-review-from">{selectedFormation.location_display_name}</dd>
                      <dt className="text-parchment-200/70">To</dt>
                      <dd data-testid="order-review-to">{selectedDestination.display_name}</dd>
                    </dl>
                    <button
                      type="button"
                      data-testid="add-movement-order"
                      onClick={stageOrder}
                      className="mt-3 rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                    >
                      Add movement order
                    </button>
                  </div>
                ) : null}

                {stagedOrder !== null && selectedFormation === null ? (
                  <div
                    ref={stagedSummaryRef}
                    tabIndex={-1}
                    data-testid="staged-order-summary"
                    onKeyDown={(event) => {
                      if (event.key === "Escape") {
                        event.stopPropagation();
                        removeStagedOrder();
                      }
                    }}
                    className="mt-4 rounded border border-gold-600 p-3 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                  >
                    <p>
                      Staged: {stagedFormation?.display_name ?? stagedOrder.formationId} →{" "}
                      {theaterName(stagedOrder.destinationTheaterId)}
                    </p>
                    <p className="mt-1 text-xs text-parchment-200/70">
                      Nothing has moved yet. Resolve the turn on the Decisions screen to apply it.
                    </p>
                    <div className="mt-2 flex gap-3">
                      <button
                        type="button"
                        data-testid="change-staged-order"
                        onClick={() => selectFormation(stagedOrder.formationId)}
                        className="rounded border border-navy-800 px-3 py-1 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                      >
                        Change
                      </button>
                      <button
                        type="button"
                        data-testid="remove-staged-order"
                        onClick={removeStagedOrder}
                        className="rounded border border-navy-800 px-3 py-1 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </Panel>

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
