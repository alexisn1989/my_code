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
 * How far a CENTRE-anchored label drops below its own node.
 *
 * A centre anchor means "no side preferred", not "printed on top of the symbol": placing the text
 * exactly on the node hid the marker, and on the capital hid the star entirely (caught in the
 * Gate 9 preview pass). Slightly larger than the directional offset because a centre label has to
 * clear the capital star, which is the tallest symbol drawn at a node.
 */
const LABEL_CENTRE_DROP_UNITS = 380;

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
      return { x, y: y + LABEL_CENTRE_DROP_UNITS, textAnchor: "middle" };
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

// --------------------------------------------------------------------------
// Formation markers on the strategic map (Military Movement, commit 7)
// --------------------------------------------------------------------------

/** How far a formation marker sits from its theater's node, in authored grid units.
 *
 * Larger than `LABEL_OFFSET_UNITS` so a marker never sits between a node and its own name, and
 * chosen with the fan geometry in mind: markers one 60-degree step apart on this radius are
 * exactly this many units apart from each other, which is comfortably wider than a marker. */
const FORMATION_FAN_RADIUS_UNITS = 620;

/** Six 60-degree slots, and therefore six markers maximum around one node. */
export const FORMATION_FAN_SLOTS = 6;

/** Above the ceiling, this many formations still render individually; the last slot becomes the
 * overflow control. Five, not six: the control OCCUPIES a slot rather than being a seventh marker
 * squeezed between them, which is what makes the non-overlap provable rather than asserted. */
const FORMATION_ICONS_WHEN_OVERFLOWING = FORMATION_FAN_SLOTS - 1;

const DEGREES_PER_SLOT = 360 / FORMATION_FAN_SLOTS;

/**
 * Where slot 0 points, given where the theater's own name sits.
 *
 * Away from the label, always. A naive fan starting due north puts slot 0 straight through the
 * name of every `anchor: n` theater -- three of the five in `tiny_valid` -- which is what drawing
 * the mockups found. Angles are SVG-style: 0 is east and they increase clockwise, because the
 * authored grid's y axis grows downward.
 *
 * With six slots covering the full circle, some slot must eventually point at the label; the
 * guarantee is about slot 0, which is the only one occupied when a theater holds one formation --
 * overwhelmingly the common case, and the one worth protecting.
 */
function fanStartDegrees(anchor: LabelAnchorValue): number {
  switch (anchor) {
    case "n":
      return 90; // label above, fan opens below
    case "s":
      return 270; // label below, fan opens above
    case "e":
      return 180; // label to the right, fan opens left
    case "w":
      return 0; // label to the left, fan opens right
    case "center":
      return 270; // a centre label drops BELOW the node, so the fan opens above
  }
}

/** One marker to draw at a theater: either a single formation, or the overflow control. */
export interface FormationMarkerPlacement {
  /** The formation this marker stands for, or `null` for the overflow control. */
  formationId: string | null;
  /** How many formations this marker hides. `0` for an individual formation. */
  hiddenCount: number;
  x: number;
  y: number;
}

/**
 * Deterministic marker positions for one theater's formations.
 *
 * `formationIds` must already be in canonical order; the caller gets them that way from the
 * server and this function never re-sorts, so the picture cannot disagree with the list beside it.
 *
 * Six is a RENDERING ceiling, never a gameplay one -- the state model caps formations per theater
 * at nothing, and the renderer must not become the reason a limit exists:
 *
 * - 1 to 6 formations: one individual marker each.
 * - 7 or more: the first five render individually and the sixth slot carries one overflow marker
 *   standing for the rest.
 *
 * Coordinates are rounded to whole grid units so the same map always produces the same picture,
 * byte for byte, and so a test can assert positions rather than approximate them.
 */
export function formationMarkerPlacements(
  centroidX: number,
  centroidY: number,
  anchor: LabelAnchorValue,
  formationIds: readonly string[],
): FormationMarkerPlacement[] {
  const total = formationIds.length;
  const overflowing = total > FORMATION_FAN_SLOTS;
  const individual = overflowing ? FORMATION_ICONS_WHEN_OVERFLOWING : total;
  const startDegrees = fanStartDegrees(anchor);

  const placements: FormationMarkerPlacement[] = [];
  for (let slot = 0; slot < individual; slot += 1) {
    placements.push({
      formationId: formationIds[slot],
      hiddenCount: 0,
      ...slotPosition(centroidX, centroidY, startDegrees, slot),
    });
  }
  if (overflowing) {
    placements.push({
      formationId: null,
      hiddenCount: total - FORMATION_ICONS_WHEN_OVERFLOWING,
      ...slotPosition(centroidX, centroidY, startDegrees, FORMATION_ICONS_WHEN_OVERFLOWING),
    });
  }
  return placements;
}

function slotPosition(
  centroidX: number,
  centroidY: number,
  startDegrees: number,
  slot: number,
): { x: number; y: number } {
  const radians = ((startDegrees + slot * DEGREES_PER_SLOT) * Math.PI) / 180;
  return {
    x: Math.round(centroidX + FORMATION_FAN_RADIUS_UNITS * Math.cos(radians)),
    y: Math.round(centroidY + FORMATION_FAN_RADIUS_UNITS * Math.sin(radians)),
  };
}

/** The overflow control's visible label: the exact number of formations it stands for. */
export function formationOverflowLabel(hiddenCount: number): string {
  return `+${hiddenCount}`;
}

/**
 * The movement interaction's spoken sentences.
 *
 * Composing a sentence from parts is string arithmetic, so it lives here with every other
 * arithmetic in this codebase -- `format-boundary.test.ts` walks the real TypeScript AST and fails
 * on any binary expression outside `src/format/**`, string concatenation included. It caught these
 * when they were written inline in the screen.
 *
 * Each is announced through the map's single polite live region.
 */
export function formationSelectedAnnouncement(
  formationName: string,
  locationName: string,
  eligibleCount: number,
): string {
  const plural = eligibleCount === 1 ? "destination" : "destinations";
  return `${formationName} selected, in ${locationName}, ${eligibleCount} eligible ${plural}`;
}

export function plannedRouteAnnouncement(originName: string, destinationName: string): string {
  return `Planned route: ${originName} to ${destinationName}`;
}

/** Explicit that nothing has moved: staging an order changes the draft, never the game. */
export function orderStagedAnnouncement(
  formationName: string,
  destinationName: string,
): string {
  return `Movement order added to this turn's draft: ${formationName} to ${destinationName}. Nothing has moved yet — resolve the turn to apply it.`;
}

/**
 * The cabinet interaction's spoken sentences and its refusal wording.
 *
 * Here for the same reason the movement sentences are: composing a sentence from parts is string
 * arithmetic, and `format-boundary.test.ts` walks the real AST and fails on any binary expression
 * outside `src/format/**`. `refusalReasonText` joins them because it is a MAPPING worth testing on
 * its own -- a switch buried in a screen can only be exercised through a rendered DOM, and the one
 * thing most worth proving about it is what it does with a code nobody has written wording for yet.
 */

/**
 * Plain English for a candidate's refusal, from the server's stable code.
 *
 * Never the raw code. `cabinet_candidate_refuses_low_legitimacy` is a contract identifier, not a
 * sentence, and showing it to a player would be the raw-identifier failure this codebase tests for
 * everywhere else. An UNRECOGNISED code gets generic prose rather than a blank or the code itself:
 * a future refusal that arrives before its wording does should read as a refusal, not as a leak.
 */
export function refusalReasonText(code: string | null | undefined): string {
  switch (code) {
    case "cabinet_character_leads_a_party":
      return "Will not serve — leads a party, and a party leader does not take a cabinet post.";
    case "cabinet_candidate_refuses_low_legitimacy":
      return "Will not serve — this government does not command enough legitimacy for them.";
    case "cabinet_candidate_refuses_this_post":
      return "Will not serve — considers this post beneath them.";
    default:
      return "Will not serve.";
  }
}

export function postSelectedAnnouncement(postName: string, candidateCount: number): string {
  const plural = candidateCount === 1 ? "candidate" : "candidates";
  return `${postName} selected, ${candidateCount} ${plural} available`;
}

export function candidateSelectedAnnouncement(candidateName: string, postName: string): string {
  return `${candidateName} proposed as ${postName}. Nothing is staged until you confirm.`;
}

/** Explicit that nothing has happened: confirming changes the draft, never the game. */
export function appointmentStagedAnnouncement(candidateName: string, postName: string): string {
  return `Added to this turn's draft: ${candidateName} as ${postName}. Nobody has been appointed yet — resolve the turn to apply it.`;
}

export function transferStagedAnnouncement(
  candidateName: string,
  postName: string,
  vacatedPostName: string,
): string {
  return `Added to this turn's draft: ${candidateName} as ${postName}, leaving ${vacatedPostName} vacant. Nothing has changed yet — resolve the turn to apply it.`;
}

export function dismissalStagedAnnouncement(holderName: string, postName: string): string {
  return `Added to this turn's draft: ${holderName} dismissed as ${postName}. Nobody has been dismissed yet — resolve the turn to apply it.`;
}

export function cabinetOrderRemovedAnnouncement(postName: string): string {
  return `Order removed for ${postName}. Nothing has changed.`;
}

/** The review's line for a post whose staged order this action deliberately leaves alone. */
export function keepsStagedOrderLine(postName: string, description: string): string {
  return `${postName} keeps its staged order: ${description}.`;
}

export function becomesLine(candidateName: string, postName: string): string {
  return `${candidateName} becomes ${postName}.`;
}

export function leftVacantLine(postName: string): string {
  return `${postName} is left vacant.`;
}

export function dismissedLine(holderName: string, postName: string): string {
  return `${holderName} is dismissed as ${postName}.`;
}

export function appointmentCostLine(cost: number): string {
  return `Costs ${cost} political capital.`;
}
