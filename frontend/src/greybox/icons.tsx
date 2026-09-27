/**
 * Gate 4A3 Commit 4 — the stroke-only icon set the frozen plan's §13 asks for.
 *
 * WHAT IT REPLACES. Ten sites rendered meaning with typographic characters borrowed from the glyph
 * repertoire: `✓ ✗ ▲ ■` for tone, `▲ ▼ ■` for direction, and `→ ↔ ★` in the map's legend. Those
 * were never chosen as a set — they were the characters that happened to be available — and two of
 * them were doing two jobs at once: `▲` meant both CAUTION and UP, and `■` meant both NEUTRAL and
 * UNCHANGED. Separating them is a gain in meaning and not only in style: a warning and an upward
 * movement stop being the same mark.
 *
 * ONE WRAPPER, SO THE RULES ARE STRUCTURAL. Every icon below is a `<path>`/`<circle>` set handed to
 * `Icon`, which is the only place that writes `viewBox`, `fill`, `stroke`, the stroke geometry and
 * `aria-hidden`. So "stroke-only" and "never announced" are properties of the COMPONENT, provable
 * once from the DOM, rather than ten hand-written copies that could each drift. This is the same
 * split `Portrait.tsx` uses to make "this is a face" a property of the component.
 *
 * WHY `aria-hidden`, WHICH IS THE OPPOSITE OF `Portrait`'S CHOICE. A portrait IS the content, so it
 * carries `role="img"` and the person's name. An icon here sits beside an existing `sr-only` word
 * that already names it — `ToneValue` renders "positive", `DeltaText` renders "up", the map legend's
 * `<dt>` reads "One-way route". Labelling the icon too would make a screen reader announce
 * "positive positive". The never-colour-alone triple is unchanged and still travels together: the
 * mark, the colour, and the visually-hidden word.
 *
 * WHY `currentColor`. The stroke inherits the tone token from the element's own `color`, so an icon
 * cannot hard-code a colour past `check:palette`, and a token change moves the icons with it. It is
 * also what lets the contrast verification measure the icons at their OWN placements: the stroke
 * colour IS the computed text colour of the element, which the calibrated probe already resolves
 * against the effective background.
 *
 * WHY 2px AT 24px, AND WHAT MUST BE MEASURED. A 2px stroke is a graphical object under WCAG 2.2
 * SC 1.4.11 and needs 3:1 against its background. The tone tokens were measured at 6.24–8.86:1 in
 * Commit 3, but the direction icons render inside `DeltaText` and the policy cards' effect chips,
 * and the legend icons sit on the strategic map's own surface — different foregrounds on different
 * backgrounds. Those figures do not transfer, so `verify:fixes` measures all three groups where they
 * actually sit rather than borrowing the tone numbers.
 *
 * NO ARITHMETIC. Every number here is a literal SVG coordinate, which is not a computation; there is
 * nothing for `format-boundary.test.ts` to object to and nothing that belongs in `src/format/**`.
 */

import type { ReactNode } from "react";

import type { Direction, Tone } from "./types";

/** The names a DOM test can look for. One per icon, so an assertion can say WHICH icon rendered
 * rather than only that some `<svg>` did — the difference between "a mark is present" and "the right
 * mark is present", which is the whole point of pinning meaning. */
export type IconName =
  | "positive"
  | "negative"
  | "caution"
  | "neutral"
  | "up"
  | "down"
  | "unchanged"
  | "route-one-way"
  | "route-two-way"
  | "capital";

/** The one place stroke-only, kept-out-of-the-accessibility-tree and 24px geometry are written. */
function Icon({ name, children }: { name: IconName; children: ReactNode }) {
  return (
    <svg
      data-icon={name}
      viewBox="0 0 24 24"
      className="inline-block h-4 w-4 shrink-0 align-[-0.15em]"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

// ---------------------------------------------------------------------------------------------
// Tone. Four marks, each distinguishable from every other by SHAPE alone at 16 rendered pixels --
// which is the bar that matters, since colour is explicitly not allowed to carry the meaning.
// ---------------------------------------------------------------------------------------------

export function IconPositive() {
  return (
    <Icon name="positive">
      <path d="M5 13l4 4L19 7" />
    </Icon>
  );
}

export function IconNegative() {
  return (
    <Icon name="negative">
      <path d="M6 6l12 12" />
      <path d="M18 6L6 18" />
    </Icon>
  );
}

/** A warning triangle, no longer sharing `▲` with the UP direction. The bang is what separates a
 * caution from a mere triangle at small sizes. */
export function IconCaution() {
  return (
    <Icon name="caution">
      <path d="M12 4L21 19H3z" />
      <path d="M12 9v4" />
      <path d="M12 16.5h.01" />
    </Icon>
  );
}

/** An open circle: present, saying nothing either way. Deliberately NOT the horizontal bar, which
 * `unchanged` now owns -- `■` used to be both, and a reader could not tell "no valence" from "no
 * movement". */
export function IconNeutral() {
  return (
    <Icon name="neutral">
      <circle cx="12" cy="12" r="7" />
    </Icon>
  );
}

// ---------------------------------------------------------------------------------------------
// Direction. An arrow says movement; the bar says none. Both read at a glance without the colour.
// ---------------------------------------------------------------------------------------------

export function IconUp() {
  return (
    <Icon name="up">
      <path d="M12 19V5" />
      <path d="M6 11l6-6 6 6" />
    </Icon>
  );
}

export function IconDown() {
  return (
    <Icon name="down">
      <path d="M12 5v14" />
      <path d="M18 13l-6 6-6-6" />
    </Icon>
  );
}

export function IconUnchanged() {
  return (
    <Icon name="unchanged">
      <path d="M5 12h14" />
    </Icon>
  );
}

// ---------------------------------------------------------------------------------------------
// Strategic-map legend. These three are a KEY TO A MARK THE MAP ACTUALLY DRAWS, so each icon has to
// be recognisably the same shape as the drawn one: the map's routes carry SVG `<marker>` arrowheads
// and its capital is a five-point star polygon. The map keeps its filled marks -- it is a map, not
// an icon set -- while the legend uses the stroke-only form every other icon here uses, and the
// `<dd>` beside each one still describes the mark in words, so the pairing never rests on the icon.
// ---------------------------------------------------------------------------------------------

export function IconRouteOneWay() {
  return (
    <Icon name="route-one-way">
      <path d="M3 12h16" />
      <path d="M14 7l5 5-5 5" />
    </Icon>
  );
}

export function IconRouteTwoWay() {
  return (
    <Icon name="route-two-way">
      <path d="M5 12h14" />
      <path d="M9 7l-5 5 5 5" />
      <path d="M15 7l5 5-5 5" />
    </Icon>
  );
}

export function IconCapital() {
  return (
    <Icon name="capital">
      <path d="M12 3.5l2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 10l6.1-.9z" />
    </Icon>
  );
}

/** Tone -> icon, replacing `TONE_GLYPH`. A map rather than a switch, so the exhaustiveness is the
 * type's job and a new `Tone` member cannot ship without its mark. */
export const TONE_ICON: Record<Tone, () => ReactNode> = {
  positive: IconPositive,
  negative: IconNegative,
  caution: IconCaution,
  neutral: IconNeutral,
};

/** Direction -> icon, replacing `DIRECTION_GLYPH`. Exported for the same reason that map was: the
 * policy cards' effect chips render a `Direction` too, and a second copy of this mapping is exactly
 * how the two would drift apart. */
export const DIRECTION_ICON: Record<Direction, () => ReactNode> = {
  up: IconUp,
  down: IconDown,
  unchanged: IconUnchanged,
};
