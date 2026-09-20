/**
 * A counterpart's portrait, drawn from the server-authored reference and from nothing else.
 *
 * STRUCTURE IS CONSTANT, APPEARANCE VARIES. Every portrait has the same parts -- head, ears, brow,
 * two eyes, nose, mouth, shoulders, collar -- and `portraitFeatures` varies their colours plus two
 * of their shapes. That split is deliberate: it makes "this is a face" a property of the COMPONENT,
 * provable from the DOM through `data-portrait-part`, rather than a claim about one hash happening
 * to land well.
 *
 * NOT A BADGE. No initials, no monogram, no coloured disc standing in for a person. Those were
 * explicitly refused: a badge is a label wearing a portrait's shape, and it would let the interface
 * claim to depict somebody it never depicted.
 *
 * NO ARITHMETIC HERE. Every number below is a literal SVG coordinate; the derivation lives in
 * `src/format/portrait.ts`, the only directory `format-boundary.test.ts` permits arithmetic in.
 *
 * ACCESSIBLE NAME IS THE PERSON'S NAME -- `role="img"` with the projected display name, never the
 * reference and never the word "portrait", so a screen-reader user hears who they are looking at.
 */

import {
  PORTRAIT_GARMENT,
  PORTRAIT_HAIR,
  PORTRAIT_HAIR_SHAPES,
  PORTRAIT_SHOULDERS,
  PORTRAIT_SKIN,
  portraitFeatures,
} from "../format/portrait";

export interface PortraitProps {
  /** The server-authored `portrait_ref`. Never a character id: deriving a likeness from an
   * identifier would invent an appearance the content never described. */
  readonly portraitRef: string;
  /** The projected display name, used verbatim as the accessible name. */
  readonly displayName: string;
}

export function Portrait({ portraitRef, displayName }: PortraitProps) {
  const features = portraitFeatures(portraitRef);
  const skin = PORTRAIT_SKIN[features.skin];
  const hair = PORTRAIT_HAIR[features.hair];
  const garment = PORTRAIT_GARMENT[features.garment];
  const hairShape = PORTRAIT_HAIR_SHAPES[features.hairStyle];

  return (
    <svg
      viewBox="0 0 64 68"
      className="h-16 w-16 shrink-0 rounded-md bg-parchment-900/40"
      role="img"
      aria-label={displayName}
      data-portrait-ref={portraitRef}
    >
      {/* Shoulders first, so the head sits in front of them. */}
      <path data-portrait-part="shoulders" d={PORTRAIT_SHOULDERS[features.build]} fill={garment} />
      <ellipse data-portrait-part="head" cx="32" cy="32" rx="16" ry="19" fill={skin} />
      <path
        data-portrait-part="ear-left"
        d="M16 32 q-4 0 -4 4 q0 4 4 4"
        fill={skin}
        stroke="rgba(0,0,0,0.18)"
        strokeWidth="0.5"
      />
      <path
        data-portrait-part="ear-right"
        d="M48 32 q4 0 4 4 q0 4 -4 4"
        fill={skin}
        stroke="rgba(0,0,0,0.18)"
        strokeWidth="0.5"
      />
      {hairShape === "" ? null : <path data-portrait-part="hair" d={hairShape} fill={hair} />}
      <path
        data-portrait-part="brow-left"
        d="M23 28 q3 -2 6 0"
        stroke={hair}
        strokeWidth="1.4"
        fill="none"
        strokeLinecap="round"
      />
      <path
        data-portrait-part="brow-right"
        d="M35 28 q3 -2 6 0"
        stroke={hair}
        strokeWidth="1.4"
        fill="none"
        strokeLinecap="round"
      />
      <ellipse data-portrait-part="eye-left" cx="26" cy="33" rx="2.1" ry="2.4" fill="#1b1b1b" />
      <ellipse data-portrait-part="eye-right" cx="38" cy="33" rx="2.1" ry="2.4" fill="#1b1b1b" />
      <path
        data-portrait-part="nose"
        d="M32 34 l0 5 q-1.6 1 -2.6 0.4"
        stroke="rgba(0,0,0,0.28)"
        strokeWidth="1"
        fill="none"
        strokeLinecap="round"
      />
      <path
        data-portrait-part="mouth"
        d="M27 44 q5 3 10 0"
        stroke="rgba(0,0,0,0.42)"
        strokeWidth="1.3"
        fill="none"
        strokeLinecap="round"
      />
      <path
        data-portrait-part="collar"
        d="M26 62 q6 5 12 0"
        stroke="rgba(0,0,0,0.25)"
        strokeWidth="1"
        fill="none"
      />
    </svg>
  );
}
