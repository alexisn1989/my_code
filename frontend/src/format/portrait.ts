/**
 * Portraits, derived from the server-authored reference and from nothing else.
 *
 * WHY THIS FILE IS IN `src/format/`: deriving features from a reference is arithmetic, and
 * `format-boundary.test.ts` confines arithmetic to this directory by parsing the real AST. So the
 * hashing lives here and the component that draws the SVG does lookups only — the same split the
 * rest of this module already imposes on currency and percentages.
 *
 * WHAT THE REFERENCE IS. `portrait_ref` is an authored key on every character
 * (`CharacterState.portrait_ref`), projected onto every row that shows a person. It names how
 * somebody is DEPICTED, which is deliberately not who they are: two characters could share a
 * depiction, or one be re-depicted, without either touching identity.
 *
 * THE RULE THIS FILE EXISTS TO KEEP: a portrait is derived from the REF, never from
 * `character_id`. Deriving from the id would make the interface invent a likeness for a person the
 * content never described — the client guessing at something only authoring can say.
 *
 * NO FALLBACK. `portraitFeatures` is total over non-empty strings, so every authored reference
 * resolves. There is deliberately no "unknown person" default: a missing reference is a contract
 * failure that must surface, not be papered over with a generic face.
 *
 * GREYBOX, AND HONEST ABOUT IT. These are constructed figures — head, shoulders, hair, garment —
 * distinct and stable per reference, not illustrations. Real artwork is art production, tracked
 * separately; what this guarantees is that the identity is real and server-authored even while the
 * drawing is not.
 */

/** The visual signature of one portrait: every varying element, as indices into the palettes
 * below. Exported because it IS the distinctness contract — two references that produced equal
 * signatures would draw the same person, and a test compares these rather than rendered pixels. */
export interface PortraitFeatures {
  readonly skin: number;
  readonly hair: number;
  readonly hairStyle: number;
  readonly garment: number;
  readonly build: number;
}

/** Deterministic 32-bit hash of a reference. FNV-1a: no dependency, no randomness, no clock, and
 * the same answer in every session and every browser — which is what makes a portrait stable
 * across a reload rather than merely stable within one render. */
function hashRef(ref: string): number {
  let hash = 2166136261;
  for (let index = 0; index < ref.length; index += 1) {
    hash ^= ref.charCodeAt(index);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash >>> 0;
}

/** Palette sizes, chosen coprime-ish so successive hash slices vary independently rather than
 * marching together. */
const SKIN_TONES = 6;
const HAIR_COLOURS = 7;
const HAIR_STYLES = 5;
const GARMENTS = 6;
const BUILDS = 3;

/**
 * The features for one reference. Total: any non-empty string yields a signature.
 *
 * Each element takes its own slice of the hash, so changing one character of a reference moves
 * several features rather than nudging one — which is what keeps two similar refs
 * (`portrait_leader_kessia` / `portrait_leader_vetruska`) visibly different people.
 */
export function portraitFeatures(ref: string): PortraitFeatures {
  if (ref.length === 0) {
    throw new Error("a portrait reference is never empty; there is no default portrait");
  }
  const hash = hashRef(ref);
  return {
    skin: hash % SKIN_TONES,
    hair: (hash >>> 3) % HAIR_COLOURS,
    hairStyle: (hash >>> 7) % HAIR_STYLES,
    garment: (hash >>> 11) % GARMENTS,
    build: (hash >>> 17) % BUILDS,
  };
}

/** The palettes. Plain lookups, so the component that draws stays free of arithmetic. */
export const PORTRAIT_SKIN = [
  "#8d5524",
  "#c68642",
  "#e0ac69",
  "#f1c27d",
  "#ffdbac",
  "#5c3317",
] as const;

export const PORTRAIT_HAIR = [
  "#090806",
  "#2c222b",
  "#71635a",
  "#b7a69e",
  "#a55728",
  "#d6c4c2",
  "#e6cea8",
] as const;

export const PORTRAIT_GARMENT = [
  "#2f4858",
  "#33658a",
  "#55626f",
  "#5c4742",
  "#3f5e5a",
  "#4a4e69",
] as const;

/** Shoulder width per build index, as a ready-made path so the renderer interpolates nothing. */
export const PORTRAIT_SHOULDERS = [
  "M14 64 Q32 44 50 64 L50 68 L14 68 Z",
  "M10 64 Q32 42 54 64 L54 68 L10 68 Z",
  "M17 64 Q32 47 47 64 L47 68 L17 68 Z",
] as const;

/** Hair shape per style index. Index 0 is deliberately bald — a real variation, not an absence. */
export const PORTRAIT_HAIR_SHAPES = [
  "",
  "M18 26 Q32 10 46 26 Q46 16 32 14 Q18 16 18 26 Z",
  "M17 30 Q32 6 47 30 Q48 14 32 12 Q16 14 17 30 Z",
  "M19 24 Q32 12 45 24 Q44 14 32 15 Q20 14 19 24 Z M17 24 L17 38 L20 38 L20 26 Z",
  "M18 28 Q32 8 46 28 Q47 15 32 13 Q17 15 18 28 Z M44 26 L48 40 L44 40 Z",
] as const;
