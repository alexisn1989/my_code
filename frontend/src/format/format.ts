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
  // The sign is taken first and the digits from the magnitude, exactly as the backend does: a
  // truncated quotient loses the sign between -99 and -1 bps (-50 -> "-0" -> "0.50%").
  const sign = valueBps < 0 ? "-" : "";
  const magnitude = Math.abs(valueBps);
  const whole = Math.trunc(magnitude / 100);
  const fraction = (magnitude % 100).toString().padStart(2, "0");
  return `${sign}${whole}.${fraction}%`;
}

/**
 * The basis-point scale's endpoints, exported so a component can declare an ARIA value range without
 * doing arithmetic of its own (finding S1 needed exactly this: `role="meter"` requires
 * `aria-valuenow`, and `format-boundary.test.ts` forbids arithmetic outside `src/format/**`). They are
 * named constants rather than inline `10000` literals so the scale has one spelling.
 */
export const RATIO_BPS_MIN = 0;
export const RATIO_BPS_MAX = 10_000;

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

/** Gate 4A3 UX-4a (U9): a `Money` value -- an integer count of MINOR units, 100 to the denar
 * (`app/core/money.py`, `MINOR_UNITS_PER_DENAR`) -- as grouped denars: `10000000000` ->
 * "100,000,000.00". Mirrors the backend's player-facing `format_money_display`, so a driver param and
 * a projection headline state the same amount the same way. `formatAmount` is for counts, never for
 * money: using it on a Money param shows the amount 100 times too large, which is exactly the UX-2
 * tax-bases defect this exists to fix. */
export const MINOR_UNITS_PER_DENAR = 100;

export function formatMoney(minorUnits: number): string {
  const sign = minorUnits < 0 ? "-" : "";
  const magnitude = Math.abs(minorUnits);
  const whole = Math.trunc(magnitude / MINOR_UNITS_PER_DENAR);
  const minor = (magnitude % MINOR_UNITS_PER_DENAR).toString().padStart(2, "0");
  return `${sign}${formatAmount(whole)}.${minor}`;
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

/**
 * A turn-result driver's sentence, composed from the entry's OWN stored params.
 *
 * `DriverItem.label` is a generic sentence per `reason_id` ("A cabinet post changed hands."), which
 * is the right fallback and the wrong answer for a driver whose whole content is WHO. The engine
 * already snapshots every name a cabinet sentence needs into the entry -- for exactly this, so a
 * turn from ten turns ago renders the names it was resolved under -- and the CLI has composed from
 * them since the day they existed. This is the same rule for the browser.
 *
 * Unknown `reason_id`s fall back to `label` verbatim, so this cannot silently restyle the rest of
 * the screen and a future driver reads correctly before anyone writes wording for it here.
 */
export function driverSentence(
  reasonId: string,
  params: Record<string, string | number> | undefined,
  label: string,
): string {
  if (params === undefined) {
    return label;
  }
  const post = params["post_display_name"];
  const who = params["character_display_name"];
  const outgoing = params["outgoing_character_display_name"];
  const cost = params["capital_committed"];
  // Characters slice: the bargain's own params. `party` and `proposal` are server-supplied display
  // names -- there is no transformation of `constitutional_amendment` into prose anywhere on this
  // side, which is the same rule the cabinet rows follow for post labels.
  const party = params["party_display_name"];
  const proposal = params["proposal_display_name"];
  const price = params["asking_price"];
  // Characters slice: foreign assistance. `profile` and `counterpart` are server-supplied display
  // names; nothing here transforms an identifier into prose.
  const profile = params["profile_display_name"];
  const counterpart = params["counterpart_display_name"];
  const granted = params["granted"];
  const remaining = params["remaining_capacity"];
  // Characters slice: promises. `subject` is the server-supplied label for whatever was promised --
  // a post, a proposal or a counterpart -- so nothing here turns `chief_of_staff` into prose. The
  // deadline is stated as an absolute turn, matching the CLI: "through turn 9" means the same thing
  // whenever it is read, where "in four turns" would go stale the moment anyone read it later.
  const subject = params["subject_display_name"];
  const deadline = params["deadline_turn"];
  const trustDelta = params["trust_delta_bps"];
  switch (reasonId) {
    case "cabinet_appointed":
      return post === undefined || who === undefined
        ? label
        : `${who} was appointed ${post} for ${cost} political capital.`;
    case "cabinet_replaced":
      return post === undefined || who === undefined || outgoing === undefined
        ? label
        : `${who} replaced ${outgoing} as ${post} for ${cost} political capital.`;
    case "cabinet_dismissed":
      return post === undefined || outgoing === undefined
        ? label
        : `${outgoing} was dismissed as ${post}; the post is now vacant.`;
    case "legislative_bargain_accepted":
      return who === undefined || party === undefined || proposal === undefined || price === undefined
        ? label
        : `${who} of the ${party} backed ${proposal}, for ${price} political capital.`;
    case "legislative_bargain_refused_will_not_deal":
      // States no figure, and cannot: a refusal's params carry neither `asking_price` nor
      // `endorsement_bps`. Naming what the leader would have wanted is exactly the counteroffer
      // this design does not have.
      return who === undefined || party === undefined || proposal === undefined
        ? label
        : `${who} of the ${party} would not deal over ${proposal}.`;
    case "foreign_assistance_granted":
      // Money, so both figures go through `formatAmount` -- the CLI renderer prints these
      // thousands-grouped, and the two surfaces render the same entry, so an ungrouped
      // "38150000" here would be the same turn described two different ways.
      return profile === undefined || granted === undefined || remaining === undefined
        ? label
        : `${counterpart === undefined ? profile : `${counterpart} of ${profile}`} sent ${typeof granted === "number" ? formatAmount(granted) : granted} in assistance; ${typeof remaining === "number" ? formatAmount(remaining) : remaining} of their capacity remains.`;
    case "promise_made":
      return who === undefined || subject === undefined || deadline === undefined
        ? label
        : `${who} was promised ${subject} through turn ${deadline}.`;
    case "promise_fulfilled":
      return who === undefined || subject === undefined || trustDelta === undefined
        ? label
        : `${who} saw the promise of ${subject} kept, gaining ${trustDelta} bps of trust.`;
    case "promise_breached":
      // `trust_delta_bps` is NEGATIVE here, so the magnitude is rendered and the word carries the
      // sign -- "losing -2000" would read as a gain to anyone skimming.
      return who === undefined || subject === undefined || trustDelta === undefined
        ? label
        : `${who} saw the promise of ${subject} broken, losing ${typeof trustDelta === "number" ? Math.abs(trustDelta) : trustDelta} bps of trust.`;
    case "promise_released":
      // No trust figure, and that is the point: a release moves none. Naming a zero would imply the
      // counterparty shrugged it off, when the obligation was actually bought back for capital.
      return who === undefined || subject === undefined
        ? label
        : `${who} released the government from the promise of ${subject}.`;
    case "promise_expired":
      return who === undefined || subject === undefined || deadline === undefined
        ? label
        : `The released promise of ${subject} to ${who} ran out at turn ${deadline}.`;
    case "foreign_assistance_counterpart_is_hostile":
      // No figure, and none available: a refusal's params carry neither `granted` nor
      // `remaining_capacity`.
      return profile === undefined ? label : `${profile} is too hostile to send assistance.`;
    case "foreign_assistance_pool_exhausted":
      return profile === undefined ? label : `${profile} has no assistance left to give.`;
    default:
      return economySentence(reasonId, params) ?? consequenceSentence(reasonId, params) ?? label;
  }
}

/**
 * What a counterpart SAYS when you sit down with them — one first-person line per state.
 *
 * REQUIRED, not decorative: every applicable counterpart state has a line, so a row never shows a
 * person with nothing to say. The variants are exhaustive over the projected verdicts rather than a
 * default plus a few specials, which is why each function below takes the verdict rather than an
 * optional string.
 *
 * NO DIGITS, EVER. R8 removed counteroffers, price bands and the offer field from this design. A
 * line like "would a hundred and fifty change your mind?" would smuggle that mechanic back through
 * prose, so these sentences carry no figure at all — the price, the grant and the deadline are
 * rendered SEPARATELY, in their own labelled elements, exactly as the server sends them. A test
 * asserts no question contains a digit, and a companion test asserts the price is still on screen,
 * so the rule cannot be satisfied by hiding the number instead of the sentence.
 */
export function bargainQuestion(willDeal: boolean): string {
  return willDeal
    ? "I can bring my people with me. What is it worth to you?"
    : "Why would I carry your vote? You have given me no reason to trust you.";
}

export function assistanceQuestion(willAssist: boolean, refusalReason?: string | null): string {
  if (willAssist) {
    return "We are willing to help. How much of our capacity do you need?";
  }
  if (refusalReason === "foreign_assistance_pool_exhausted") {
    return "We have already given what we had. What else did you imagine was left?";
  }
  return "After everything between us, you come asking for help?";
}

export function promiseOfferQuestion(termKind: string): string {
  switch (termKind) {
    case "cabinet_tenure":
      return "Will you keep me where I am, or am I one bad turn from the door?";
    case "legislative_support":
      return "Put it to the chamber and I will stand with you. Do we have an understanding?";
    case "assistance_restraint":
      return "Leave our reserves alone and we will remember it. Can you hold to that?";
    default:
      return "What exactly are you offering me?";
  }
}

export function activePromiseQuestion(releasable: boolean, status: string): string {
  if (status === "cancelled") {
    return "You bought your way out of this one. I have not forgotten.";
  }
  return releasable
    ? "You gave me your word. Are you here to keep it, or to buy it back?"
    : "This settles now. We both know where we stand.";
}

/**
 * The meeting panel's own lines: prices, pools, deadlines and announcements.
 *
 * They live here for the reason every sentence above does — string composition is arithmetic under
 * `format-boundary.test.ts`, which parses every non-test file with the real TypeScript compiler and
 * fails a `BinaryExpression` outside `src/format/**`. A screen that built these inline would fail
 * that gate, and the gate is what keeps display logic testable without a DOM.
 *
 * Each takes an ALREADY-PROJECTED figure. Nothing here decides willingness, prices an approach,
 * computes a deadline or judges affordability: those are the server's answers, rendered verbatim.
 */
export function bargainPriceLine(askingPrice: number): string {
  return `Asking price: ${formatAmount(askingPrice)} political capital.`;
}

export function assistanceGrantLine(estimatedGrant: number): string {
  return `Would send ${formatAmount(estimatedGrant)}.`;
}

export function remainingCapacityLine(remainingCapacity: number): string {
  return `Remaining capacity: ${formatAmount(remainingCapacity)}.`;
}

export function earliestDeadlineLine(deadlineTurn: number): string {
  return `The earliest turn you could promise through is ${formatAmount(deadlineTurn)}.`;
}

export function promiseWindowLine(madeTurn: number, deadlineTurn: number): string {
  return `Given on turn ${formatAmount(madeTurn)}, runs through turn ${formatAmount(deadlineTurn)}.`;
}

/** Deliberately carries NO figure.
 *
 * The release price is a server constant, and restating it here would put a second copy of a game
 * number in the client — the duplication the no-duplication contract exists to stop. The exact
 * charge is `/preview`'s `promise_release_capital`, shown on the Decisions screen beside every
 * other capital term, which is also the only place it can be weighed against them. */
export function releaseCostLine(): string {
  return "Releasing it costs political capital and moves no trust — the Decisions screen shows the charge against this turn.";
}

/** Why a release is refused, from the projection's own two display reasons.
 *
 * A DIFFERENT namespace from the seven submission rejection codes: every blocked release is
 * `promise_release_names_no_live_promise` on the resolver and on preflight, and the detail is
 * projected only here. An unrecognised reason still reads as a refusal rather than leaking a code.
 */
export function releaseBlockedText(reason: string | null | undefined): string {
  switch (reason) {
    case "promise_already_released":
      return "Already released — it runs to its original deadline either way.";
    case "promise_past_releasing":
      return "Too late to release — this one settles on its merits this turn.";
    default:
      return "Cannot be released.";
  }
}

export function counterpartySelectedAnnouncement(displayName: string): string {
  return `${displayName} selected. Nothing is staged until you confirm.`;
}

export function bargainStagedAnnouncement(displayName: string, proposalName: string): string {
  return `Added to this turn's draft: ${displayName} backs ${proposalName}. Nothing has been agreed yet — resolve the turn to put it to them.`;
}

export function assistanceStagedAnnouncement(displayName: string): string {
  return `Added to this turn's draft: a request to ${displayName}. Nothing has been sent yet — resolve the turn to ask.`;
}

export function promiseStagedAnnouncement(displayName: string, subjectName: string): string {
  return `Added to this turn's draft: a promise to ${displayName} about ${subjectName}. Nothing has been given yet — resolve the turn to make it.`;
}

export function releaseStagedAnnouncement(displayName: string): string {
  return `Added to this turn's draft: releasing your promise to ${displayName}. Nothing has changed yet — resolve the turn to pay for it.`;
}

export function meetingDraftClearedAnnouncement(): string {
  return "Removed from this turn's draft. Nothing has changed.";
}

// ---------------------------------------------------------------------------------------------------
// Gate 4A3 UX-1 — route-aware preview copy and the decree rule
// ---------------------------------------------------------------------------------------------------

/** Display words for the server's chamber identities. Authored, never a transformation of the id;
 * an identity this build has no word for falls back to a neutral phrase rather than the raw id. */
export const CHAMBER_LABEL: Readonly<Record<string, string>> = {
  lower: "Lower chamber",
  upper: "Upper chamber",
};

export function chamberLabel(chamber: string): string {
  return CHAMBER_LABEL[chamber] ?? "The chamber";
}

/** Display words for a proposal route. */
export function routeLabel(route: string | null | undefined): string {
  if (route === "decree") return "Decree";
  if (route === "legislative") return "Legislative vote";
  return "No route";
}

/** Which proposals may be decreed, mirroring the resolver exactly
 * (`phases.py`: a budget needs unlimited decree authority; an amendment ALSO needs that no
 * legislature sits). Built only from fields `DecisionOptionsProjection` already carries. */
export function decreeAllowed(
  kind: "budget" | "amendment",
  options: { decree_available: boolean; chambers: readonly string[] },
): boolean {
  if (kind === "budget") return options.decree_available;
  return options.decree_available && options.chambers.length === 0;
}

/** The decree price for this proposal kind. */
export function decreeCost(
  kind: "budget" | "amendment",
  options: { decree_legislative_capital_cost: number; decree_amendment_capital_cost: number },
): number {
  return kind === "budget"
    ? options.decree_legislative_capital_cost
    : options.decree_amendment_capital_cost;
}

/** One line per FAILING chamber, from that chamber's own row -- never a pooled gap. */
export function chamberShortfallSentence(chamber: {
  chamber: string;
  supporting_seats: number;
  required_seats: number;
}): string {
  const short = chamber.required_seats - chamber.supporting_seats;
  return `${chamberLabel(chamber.chamber)}: ${formatAmount(short)} short of ${formatAmount(
    chamber.required_seats,
  )}.`;
}

/** What the player can do about a legislative proposal that would fail. The decree clause appears
 * only when this proposal kind may actually be decreed. */
export function failingVoteAdvice(decreeOption: { cost: number } | null): string {
  const base = "You can add influence capital for blocs above";
  return decreeOption === null
    ? `${base}.`
    : `${base}, or switch the route to decree (cost ${formatAmount(decreeOption.cost)}).`;
}

/** Pre-resolution wording for a decree. It never claims an enactment the resolver would refuse. */
export function decreePreviewSentence(preview: {
  affordable: boolean;
  route_capital_cost: number;
  committed_capital: number;
  opening_capital: number;
}): string {
  if (!preview.affordable) {
    return `Not affordable: ${formatCommitted(
      preview.committed_capital,
      preview.opening_capital,
    )} — resolving this draft would be refused.`;
  }
  return `If resolved now: enacted by decree — the legislature is bypassed. Route cost ${formatAmount(
    preview.route_capital_cost,
  )}.`;
}

// ---------------------------------------------------------------------------------------------------
// Gate 4A3 UX-2 — the turn result: cause first, bookkeeping folded away, nothing lost
// ---------------------------------------------------------------------------------------------------

/** Display names for the engine's eleven `SectorCategory` values. Authored here because a driver's
 * params carry the raw category and no display name; a backend test reads this map and pins its keys
 * to the enum, so a new sector cannot ship without a label. An unknown value falls back to the
 * generic driver label, never to the raw identifier. */
export const SECTOR_LABEL: Readonly<Record<string, string>> = {
  agriculture: "Agriculture",
  extraction: "Extraction",
  manufacturing: "Manufacturing",
  construction: "Construction",
  energy: "Energy",
  transportation: "Transportation",
  consumer_services: "Consumer services",
  finance_and_professional_services: "Finance and professional services",
  technology: "Technology",
  defense_industry: "Defence industry",
  public_services: "Public services",
};

function num(value: string | number | undefined): number | undefined {
  return typeof value === "number" ? value : undefined;
}

/** Sentences for the economy and bookkeeping drivers, composed ONLY from each driver's stored
 * params. `undefined` means "no wording for this reason or a param is missing", and the caller then
 * shows the generic label -- the same fallback rule every other driver follows. */
function economySentence(
  reasonId: string,
  params: Record<string, string | number>,
): string | undefined {
  switch (reasonId) {
    case "sector_inactive": {
      const category = params["category"];
      const name = typeof category === "string" ? SECTOR_LABEL[category] : undefined;
      return name === undefined ? undefined : `The ${name} sector produced nothing this turn.`;
    }
    case "resource_extraction_resolved": {
      const depleted = num(params["deposits_depleted"]);
      const unassigned = num(params["unassigned_resource_workers"]);
      if (depleted === undefined || unassigned === undefined) return undefined;
      const parts: string[] = [];
      if (depleted > 0) {
        parts.push(`${formatAmount(depleted)} deposit${depleted === 1 ? "" : "s"} ran dry`);
      }
      if (unassigned > 0) {
        parts.push(`${formatAmount(unassigned)} resource workers had no deposit to work`);
      }
      return parts.length === 0
        ? "Resource extraction ran normally: no deposit ran dry and every resource worker was placed."
        : `Resource extraction: ${parts.join("; ")}.`;
    }
    case "labor_market_resolved": {
      const employed = num(params["total_employment"]);
      const rate = num(params["unemployment_rate_bps"]);
      const unfilled = num(params["unfilled_jobs"]);
      if (employed === undefined || rate === undefined || unfilled === undefined) return undefined;
      return `Labour market: ${formatAmount(employed)} employed, ${formatBpsPercent(rate)} unemployment, ${formatAmount(unfilled)} unfilled jobs.`;
    }
    case "production_summary": {
      const output = num(params["total_gross_output"]);
      const capacity = num(params["sectors_capacity_constrained"]);
      const labour = num(params["sectors_labor_constrained"]);
      if (output === undefined || capacity === undefined || labour === undefined) return undefined;
      return `Production: ${formatAmount(output)} output; ${formatAmount(capacity)} sectors at capacity, ${formatAmount(labour)} short of workers.`;
    }
    case "tax_bases_derived": {
      const personal = num(params["personal_income"]);
      const corporate = num(params["corporate_profit"]);
      const consumption = num(params["taxable_consumption"]);
      if (personal === undefined || corporate === undefined || consumption === undefined) {
        return undefined;
      }
      // Money params: minor units, rendered as denars (UX-4a fixed these, which UX-2 had shown 100x
      // too large through `formatAmount`).
      return `Tax bases: personal income ${formatMoney(personal)}, corporate profit ${formatMoney(corporate)}, consumption ${formatMoney(consumption)}.`;
    }
    case "turn_resolved": {
      const turn = num(params["turn"]);
      return turn === undefined ? undefined : `Turn ${turn} resolved.`;
    }
    default:
      return undefined;
  }
}

/** Bookkeeping that says nothing about THIS turn's choices, folded into a collapsed "Routine steps"
 * section. Decided only from the driver's reason and stored params; consequential events stay
 * visible -- a sector producing nothing always, and resource extraction whenever a deposit ran dry
 * or resource workers went unplaced. */
const ALWAYS_ROUTINE = new Set([
  "labor_market_resolved",
  "production_summary",
  "tax_bases_derived",
  "turn_resolved",
  // Gate 4A3 UX-4e (DR1, ruled): the capital ledger repeats the capital line and the "What your
  // decision committed" panel, and a bloc's drift toward its baseline is mechanical, not a result of
  // this turn's choice. Both keep a named sentence inside Routine steps.
  "political_capital_ledger_resolved",
  "relationship_decay_resolved",
]);

export function isRoutineDriver(driver: {
  reason_id: string;
  params?: Record<string, string | number>;
}): boolean {
  if (ALWAYS_ROUTINE.has(driver.reason_id)) return true;
  if (driver.reason_id === "resource_extraction_resolved") {
    const depleted = num(driver.params?.["deposits_depleted"]);
    const unassigned = num(driver.params?.["unassigned_resource_workers"]);
    // Only a CONFIRMED quiet extraction is folded away; missing figures keep it visible.
    return depleted === 0 && unassigned === 0;
  }
  return false;
}

// ---------------------------------------------------------------------------------------------------
// Gate 4A3 UX-3 — the Dashboard's national tint, drawn rather than claimed
// ---------------------------------------------------------------------------------------------------

/** The tint's weakest and strongest mix of `gold-600` into `navy-950`, in percent: never so faint it
 * reads as empty, never so strong it outshouts the panel. No text sits on the mix -- the country name
 * has its own `navy-950` label, because every text backdrop is an authored palette surface. */
export const TINT_MIX_MIN_PERCENT = 15;
export const TINT_MIX_MAX_PERCENT = 60;

/** A server-provided ratio in basis points -> how much gold to mix into the box, linear between the
 * two bounds above and clamped to them. A purely visual figure; the value itself is stated in text. */
export function tintMixPercent(valueBps: number): number {
  const clamped = Math.min(RATIO_BPS_MAX, Math.max(RATIO_BPS_MIN, valueBps));
  const span = TINT_MIX_MAX_PERCENT - TINT_MIX_MIN_PERCENT;
  return Math.round((TINT_MIX_MIN_PERCENT + (span * clamped) / RATIO_BPS_MAX) * 100) / 100;
}

/** The opaque fill for the tint box: a mix of two palette tokens, so the box shows one solid colour. */
export function tintFill(valueBps: number): string {
  return `color-mix(in oklab, var(--color-gold-600) ${tintMixPercent(valueBps)}%, var(--color-navy-950))`;
}

/** The player-facing caption, composed from the server's metric label. It replaces the server's
 * `map.note`, whose developer-facing wording the interface no longer renders. */
export function tintCaption(metricLabel: string): string {
  return `The colour shows national ${metricLabel.toLowerCase()}: the stronger it is, the deeper the tint.`;
}

/** What the box draws, and nothing it does not: a name on a tint. No outline exists, so none is
 * claimed. */
export function tintAccessibleName(country: string, metricLabel: string, valueText: string): string {
  return `${country}: national tint by ${metricLabel.toLowerCase()}, ${valueText}.`;
}

// ---------------------------------------------------------------------------------------------------
// Gate 4A3 UX-4b — one wording per staged action, shared by every screen that states it
// ---------------------------------------------------------------------------------------------------

/** The policy proposal as a phrase inside a sentence. Moved here from `MeetingScreen` so the
 * bargain line reads identically there and in Decisions' draft list. */
export function proposalPhrase(slot: "budget" | "amendment" | null): string {
  return slot === "amendment" ? "the constitutional amendment" : "the budget";
}

export function proposalStagedLine(slot: "budget" | "amendment", route: "legislative" | "decree"): string {
  const what = slot === "amendment" ? "The constitutional amendment" : "The budget";
  return route === "decree" ? `${what}, by decree.` : `${what}, put to a legislative vote.`;
}

export function investmentStagedLine(politicalCapital: number, blocName: string): string {
  return `${formatAmount(politicalCapital)} political capital invested in ${blocName}.`;
}

export function bargainStagedLine(leaderName: string, slot: "budget" | "amendment"): string {
  return `${leaderName} is asked to back ${proposalPhrase(slot)}.`;
}

export function assistanceStagedLine(counterpartName: string): string {
  return `${counterpartName} is asked for assistance.`;
}

export function promiseMadeStagedLine(characterName: string, subjectName: string): string {
  return `A promise to ${characterName} about ${subjectName}.`;
}

export function promiseReleaseStagedLine(characterName: string): string {
  return `Releasing your promise to ${characterName}.`;
}

export function movementStagedLine(formationName: string, destinationName: string): string {
  return `${formationName} → ${destinationName}`;
}

/** The nav's count beside Decisions: "3 staged". */
export function stagedCountText(count: number): string {
  return `${count} staged`;
}

/** The resolve confirmation, pluralised: "Resolve turn 4 with 3 staged actions?". `turn` is the
 * dashboard's own turn; before it has loaded the sentence says "this turn" rather than guess. */
export function resolveConfirmSentence(turn: number | null, count: number): string {
  const which = turn === null ? "this turn" : `turn ${turn}`;
  if (count === 0) return `Resolve ${which} with nothing staged?`;
  return `Resolve ${which} with ${count} staged action${count === 1 ? "" : "s"}?`;
}

// ---------------------------------------------------------------------------------------------------
// Gate 4A3 UX-4e — the turn's consequences, named and in the order a player needs them
// ---------------------------------------------------------------------------------------------------

/** Display names for the three tax-rate fields a `tax_rate_changed` driver names. A backend drift guard
 * pins these keys to the engine's budget fields. */
export const TAX_FIELD_LABEL: Readonly<Record<string, string>> = {
  personal_income_rate_bps: "Personal income tax",
  corporate_rate_bps: "Corporate tax",
  consumption_rate_bps: "Consumption tax",
};

/** Display names for the seven `SpendingCategory` values; a backend drift guard pins the keys. */
export const SPENDING_LABEL: Readonly<Record<string, string>> = {
  health: "Health",
  education: "Education",
  welfare: "Welfare",
  infrastructure: "Infrastructure",
  defense: "Defence",
  security: "Security",
  administration: "Administration",
};

/** A signed change in percentage points from basis points: 250 -> "+2.50 points", -75 -> "-0.75 points". */
export function formatSignedPoints(bps: number): string {
  const sign = bps > 0 ? "+" : bps < 0 ? "-" : "±";
  const magnitude = formatBpsPercent(Math.abs(bps)).replace("%", "");
  return `${sign}${magnitude} points`;
}

function str(value: string | number | undefined): string | undefined {
  return typeof value === "string" ? value : undefined;
}

/** Sentences for the political drivers, composed ONLY from each driver's stored params (and the
 * projection's `bloc_display_name`). `undefined` -> the generic label, the same fallback rule as
 * every other driver; never a raw identifier. */
function consequenceSentence(
  reasonId: string,
  params: Record<string, string | number>,
): string | undefined {
  const bloc = str(params["bloc_display_name"]);
  switch (reasonId) {
    case "legislative_vote_resolved": {
      // THE contradiction this exists to remove: on a decree turn the generic label said "The
      // legislature voted." beside "The legislature was bypassed." The driver stores how the
      // budget was resolved; no vote is claimed unless one was held.
      const outcome = str(params["outcome"]);
      const passed = num(params["chambers_passed"]);
      const total = num(params["chambers_total"]);
      if (outcome === "enacted_by_decree") return "Enacted by decree — no vote was held.";
      if (outcome === "no_proposal") return "No budget was put to a vote.";
      if (passed === undefined || total === undefined) return undefined;
      const tally = `${passed} of ${total} chamber${total === 1 ? "" : "s"} carried.`;
      if (outcome === "passed_legislative") return `The legislature passed the budget: ${tally}`;
      if (outcome === "failed_legislative") return `The legislature voted the budget down: ${tally}`;
      return undefined;
    }
    case "budget_blocked_by_legislature": {
      const chamber = str(params["chamber"]);
      const supporting = num(params["supporting_seats"]);
      const required = num(params["required_yes_seats"]);
      const shortfall = num(params["shortfall_seats"]);
      if (chamber === undefined || supporting === undefined || required === undefined || shortfall === undefined) {
        return undefined;
      }
      return `${chamberLabel(chamber)} blocked the budget: ${formatAmount(supporting)} supporting votes; ${formatAmount(required)} required—${formatAmount(shortfall)} short.`;
    }
    case "tax_rate_changed": {
      const field = str(params["field"]);
      const name = field === undefined ? undefined : TAX_FIELD_LABEL[field];
      const before = num(params["old_bps"]);
      const after = num(params["new_bps"]);
      if (name === undefined || before === undefined || after === undefined) return undefined;
      return `${name}: ${formatBpsPercent(before)} → ${formatBpsPercent(after)}.`;
    }
    case "spending_category_changed": {
      const category = str(params["category"]);
      const name = category === undefined ? undefined : SPENDING_LABEL[category];
      const before = num(params["old_amount"]);
      const after = num(params["new_amount"]);
      if (name === undefined || before === undefined || after === undefined) return undefined;
      return `${name} spending: ${formatMoney(before)} → ${formatMoney(after)}.`;
    }
    case "legitimacy_resolved": {
      const opening = num(params["opening_legitimacy_bps"]);
      const closing = num(params["closing_legitimacy_bps"]);
      const change = num(params["total_legitimacy_change_bps"]);
      if (opening === undefined || closing === undefined || change === undefined) return undefined;
      return `Legitimacy: ${formatBpsPercent(opening)} → ${formatBpsPercent(closing)} (${formatSignedPoints(change)}).`;
    }
    case "political_capital_resolved": {
      const opening = num(params["opening"]);
      const closing = num(params["closing"]);
      const capacity = num(params["capacity"]);
      const spent = num(params["spent"]);
      const regained = num(params["regeneration"]);
      if ([opening, closing, capacity, spent, regained].some((v) => v === undefined)) return undefined;
      return `Political capital: ${formatAmount(opening!)} → ${formatAmount(closing!)} of ${formatAmount(capacity!)} (${formatAmount(spent!)} spent, ${formatAmount(regained!)} regained).`;
    }
    case "political_capital_ledger_resolved": {
      const total = num(params["total_committed"]);
      const vote = num(params["legislative_committed"]);
      const relationships = num(params["relationship_committed"]);
      if (total === undefined || vote === undefined || relationships === undefined) return undefined;
      return `Capital committed this turn: ${formatAmount(total)} (${formatAmount(vote)} to the vote or decree, ${formatAmount(relationships)} to relationships).`;
    }
    case "coup_risk_assessed": {
      // An ATTEMPT risk, never an outcome -- the same distinction the CLI and the Survival card keep.
      const coup = num(params["coup_attempt_risk_bps"]);
      const unrest = num(params["unrest_attempt_risk_bps"]);
      const impeachment = num(params["impeachment_attempt_risk_bps"]);
      const eligible = params["impeachment_eligible"] as unknown;
      if (coup === undefined || unrest === undefined) return undefined;
      const impeachmentPart =
        (eligible === true || eligible === 1) && impeachment !== undefined
          ? `, impeachment risk ${formatBpsPercent(impeachment)}`
          : "";
      return `Risk of an attempt this turn: coup ${formatBpsPercent(coup)}, unrest ${formatBpsPercent(unrest)}${impeachmentPart}.`;
    }
    case "enacted_policy_relationship_reaction": {
      const change = num(params["policy_reaction_component_bps"]);
      return bloc === undefined || change === undefined
        ? undefined
        : `${bloc} reacted to the enacted policy (${formatSignedPoints(change)}).`;
    }
    case "decree_bypass_relationship_reaction": {
      const change = num(params["decree_bypass_component_bps"]);
      return bloc === undefined || change === undefined
        ? undefined
        : `${bloc} resented being bypassed by decree (${formatSignedPoints(change)}).`;
    }
    case "relationship_decay_resolved": {
      const change = num(params["decay_component_bps"]);
      return bloc === undefined || change === undefined
        ? undefined
        : `${bloc} drifted toward its usual stance (${formatSignedPoints(change)}).`;
    }
    case "bloc_relationship_resolved": {
      const opening = num(params["opening_relationship_bps"]);
      const closing = num(params["closing_relationship_bps"]);
      const change = num(params["applied_total_change_bps"]);
      if (bloc === undefined || opening === undefined || closing === undefined || change === undefined) {
        return undefined;
      }
      return `${bloc}: relationship ${formatBpsPercent(opening)} → ${formatBpsPercent(closing)} (${formatSignedPoints(change)}).`;
    }
    default:
      return undefined;
  }
}

/** Gate 4A3 UX-4e (DR1, ruled): what the player's choice DID comes first. Rank 0 is the outcome of
 * this turn's decisions and the events that decide the campaign; everything else keeps server order
 * after them. Only the visible list is reordered; Routine steps and the Trace keep server order. */
const OUTCOME_FIRST = new Set([
  "legislative_vote_resolved",
  "budget_blocked_by_legislature",
  "constitutional_amendment_enacted",
  "peaceful_liberalization_completed",
  "tax_rate_changed",
  "spending_category_changed",
  "cabinet_appointed",
  "cabinet_replaced",
  "cabinet_dismissed",
  "legislative_bargain_accepted",
  "legislative_bargain_refused_will_not_deal",
  "foreign_assistance_granted",
  "promise_made",
  "promise_fulfilled",
  "promise_breached",
  "promise_released",
  "election_result",
  "coup_attempt_occurred",
  "coup_succeeded",
  "impeachment_motion_brought",
  "impeachment_succeeded",
  "game_concluded",
]);

export function driverPriority(reasonId: string): number {
  return OUTCOME_FIRST.has(reasonId) ? 0 : 1;
}

/** A stable sort by `driverPriority`: equal ranks keep the order the server recorded them in. */
export function outcomeFirst<T extends { reason_id: string }>(items: readonly T[]): T[] {
  return items
    .map((item, position) => ({ item, position }))
    .sort((a, b) => driverPriority(a.item.reason_id) - driverPriority(b.item.reason_id) || a.position - b.position)
    .map(({ item }) => item);
}
