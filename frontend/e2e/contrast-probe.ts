/**
 * Gate 4A3 — THE CALIBRATED COLOUR PROBE, in ONE place.
 *
 * WHY THIS IS A SHARED MODULE AND NOT A SECOND COPY. Commit 3 built this machinery inside
 * `verify-commit3-fixes.spec.ts`, and getting it right took three attempts, each of which looked like
 * an application defect rather than a probe defect because every element came back at exactly 1.00:1:
 *
 *   1. An `rgba(...)` regex matched nothing -- Tailwind v4 emits computed colours in OKLab, e.g.
 *      `oklab(0.896735 0.00171477 0.0394163 / 0.6)`.
 *   2. A canvas 2D `fillStyle` round-trip -- normally the reliable way to make a browser parse any
 *      colour -- ALSO failed: this Chromium's canvas rejects `oklab()` and returns
 *      `rgba(0,0,0,0)`, which composited to exactly the background and gave 1.00:1 again.
 *   3. `.sr-only` nodes were being measured at all, although they are never painted.
 *
 * Commit 4 needs the same machinery for a different question -- the icon set's 2px strokes under
 * WCAG 2.2 SC 1.4.11 -- and a second copy would be a second chance to regress into those three
 * failures independently. So the source lives here once, is injected into the page, and both
 * measurements read it from `window.__mandateColour`.
 *
 * IT IS A SOURCE STRING, not an imported function, because it runs INSIDE the page. Playwright
 * serializes an `evaluate` callback, so helpers must either be defined in that callback's own body or
 * installed on `window` beforehand. `installColourProbe` uses `addInitScript`, which survives
 * navigations -- which matters because these specs start a campaign and then move between screens.
 *
 * A NUMBER FROM THIS PROBE IS NOT TRUSTED UNTIL IT IS CALIBRATED. Every caller must assert that the
 * probe reproduces an independently computed ratio for a known token before relying on its other
 * figures; `CALIBRATION` states that expectation as data so the two callers cannot disagree about it.
 */

import type { Page } from "@playwright/test";

/**
 * The independently computed check every caller asserts before trusting a measurement.
 *
 * `text-parchment-200/60` is parchment-200 (#e8dcc0) at 60% over navy-900 (#0f1626), which computes
 * to 5.45:1. axe independently reported 4.16:1 for the same token at 50%, matching the same offline
 * model, which is why this figure is treated as known rather than assumed.
 *
 * THE BAND WAS TOO WIDE TO DO ITS JOB, and that is why it is tightened here. It used to be 5.2-5.7,
 * spanning navy-900 (5.45) AND navy-950 (5.57) AND the black-backdrop figure the broken parser
 * produced (5.65). A band that contains both the truth and the bug cannot detect the bug -- and it
 * did not: the calibration passed on every run while every ratio in the record was inflated. It is now
 * a tolerance around ONE expected value, so a wrong backdrop moves the figure outside it.
 */
export const CALIBRATION = {
  className: "text-parchment-200/60",
  /** parchment-200 at 60% over navy-900, computed offline. */
  expectedRatio: 5.45,
  offlineNote:
    "parchment-200 #e8dcc0 at alpha 0.6, source-over onto navy-900 #0f1626, gives 5.45:1; axe " +
    "independently reported 4.16:1 for the same token at 50% under the same model",
} as const;

/** The WCAG bars used by the callers. 4.5:1 is SC 1.4.3 for normal text; 3:1 is SC 1.4.11 for a
 * graphical object, which is what a 2px icon stroke is. */
export const TEXT_CONTRAST_MINIMUM = 4.5;
export const NON_TEXT_CONTRAST_MINIMUM = 3;

/* ------------------------------------------------------------------------------------------------
 * THE TOLERANCES, FIXED HERE SO THEY CANNOT BE CHOSEN AFTER SEEING A RESULT.
 *
 * A tolerance picked once a number is in hand is not a tolerance, it is a rationalisation -- and the
 * old calibration band is the worked example: wide enough to accept a 4-surface-wide spread, it
 * accepted a bug for two commits.
 * ---------------------------------------------------------------------------------------------- */

/** Conversion: how far the probe's normalised sRGB may sit from the AUTHORED token hex, per channel.
 *
 * Deliberately NOT "exactly equal". CSS Color 4 does not require serialization to preserve component
 * text, so an exact-integer rule would be brittle by specification rather than by luck -- a browser is
 * free to hand back a value that round-trips a unit away. One unit per 8-bit channel is tight enough
 * to catch a real conversion error and loose enough to be spec-legal. Measured today at delta 0 on
 * every token. */
export const CHANNEL_TOLERANCE = 1;

/** Ratio: absolute agreement required between the probe's in-page figure and an offline recomputation.
 *
 * 0.05 is roughly 1% at these magnitudes -- far tighter than the ~11% error the parser bug produced
 * (9.76 against a true 8.78), so it would have failed on the first run. It is applied twice, and the
 * second application is the one that matters:
 *
 *   1. FORMULA check -- recompute from the probe's OWN recorded inputs. Validates the arithmetic only,
 *      and should be near-exact.
 *   2. INDEPENDENCE check -- recompute from AUTHORED values: the `tokens.css` hex, the alpha, and the
 *      backdrop the placement authors. This is the one that catches a wrong backdrop, because it never
 *      consults what the probe believed the backdrop was.
 */
export const RATIO_TOLERANCE = 0.05;

/** The palette surfaces, authored in `src/styles/tokens.css`. Kept here so an expected backdrop is a
 * NAMED surface rather than a hex typed at a call site -- and so that "the probe found a colour that
 * is not a surface in this palette at all" is expressible. Pure black is not among them, which is
 * exactly what the broken parser reported. */
export const SURFACES = {
  "navy-950": "#0a0f1a",
  "navy-900": "#0f1626",
  "navy-800": "#182338",
} as const;

export type SurfaceName = keyof typeof SURFACES;

/** The foreground tokens these measurements read, authored in `src/styles/tokens.css`. */
export const FOREGROUNDS = {
  "success-400": "#86d3a0",
  "warning-400": "#e8b962",
  "danger-400": "#e58a8a",
  "info-400": "#8fb8dc",
  "parchment-100": "#f3ecd9",
  "parchment-200": "#e8dcc0",
} as const;

export type ForegroundName = keyof typeof FOREGROUNDS;

function channels(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

/**
 * The OFFLINE model, written out so it can be disagreed with rather than trusted.
 *
 * MIXING. Tailwind v4 compiles `text-X/NN` to `color-mix(in oklab, var(--color-X) NN%, transparent)`
 * (verified in the built stylesheet). Per CSS Color 4, `color-mix()` interpolates with PREMULTIPLIED
 * alpha, and `transparent` is `rgb(0 0 0 / 0)`: premultiplying by an alpha of 0 contributes nothing to
 * the colour components, the mix carries `alpha = NN%`, and un-premultiplying restores X's own
 * components. So modelling the foreground as "the authored hex at alpha NN%" is correct FOR THIS
 * PATTERN -- and callers keep each measurement's `rawColor` so that claim is checked against what the
 * browser actually serialized instead of being assumed.
 *
 * COMPOSITING. Source-over in sRGB against the backdrop -- `alpha*fg + (1-alpha)*bg` per channel,
 * rounded -- which is what the compositor does at paint time. Deliberately NOT an OKLab mix: alpha
 * compositing and colour interpolation are different operations, and conflating them is the sort of
 * error that produces a plausible wrong number.
 *
 * RATIO. WCAG relative luminance on the composited sRGB pair.
 */
export function offlineRatio({
  foreground,
  backdrop,
  alpha = 1,
}: {
  foreground: ForegroundName | string;
  backdrop: SurfaceName | string;
  alpha?: number;
}): number {
  const fg = channels(foreground.startsWith("#") ? foreground : FOREGROUNDS[foreground as ForegroundName]);
  const bg = channels(backdrop.startsWith("#") ? backdrop : SURFACES[backdrop as SurfaceName]);
  const composited = fg.map((f, i) => Math.round(alpha * f + (1 - alpha) * bg[i]!));
  const linear = (c: number) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  const luminance = (rgb: number[]) =>
    0.2126 * linear(rgb[0]!) + 0.7152 * linear(rgb[1]!) + 0.0722 * linear(rgb[2]!);
  const a = luminance(composited);
  const b = luminance(bg);
  return Math.round(((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)) * 100) / 100;
}

/** Which surface a given icon placement authors as its nearest painted backdrop.
 *
 * DERIVED FROM THE COMPONENTS' OWN `className`, not from anything the probe reports -- that
 * independence is the whole point. Restricting the check to "some navy token" would still accept
 * `navy-800` where `navy-900` is authored, i.e. a walk that stops one ancestor early: the same defect
 * as the pure-black one, wearing a less obvious value.
 *
 * Every placement below resolves to `bg-navy-900`, because they all sit inside `Panel`
 * (`src/greybox/components.tsx`), a policy card's own `<button>`, or the map legend's `<details>`. A
 * mismatch against this table is a finding either way and must stop the run: either the probe walks
 * wrong, or a component's backdrop changed and this table is stale. */
export const EXPECTED_BACKDROP: Record<string, SurfaceName> = {
  /** Dashboard concern cards -- each concern is wrapped in `Panel`. */
  "dashboard-concern": "navy-900",
  /** `ConsequencesPanel`, rendered inside a `Panel` on Decisions after Preview. */
  "preview-panel": "navy-900",
  /** A policy card's effect chips -- the card's own `<button className="... bg-navy-900 ...">`. */
  "policy-card": "navy-900",
  /** The strategic map's legend, inside `<details className="... bg-navy-900 ...">`. */
  "map-legend": "navy-900",
  /** `TurnResultView`'s outcome headline, inside a `Panel`. */
  "turn-result": "navy-900",
};

/** The in-page source. Defines `window.__mandateColour` and nothing else. */
const COLOUR_PROBE_SOURCE = String.raw`
(() => {
  const gamma = (c) => {
    const v = c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
    return Math.max(0, Math.min(255, Math.round(v * 255)));
  };
  const oklabToRgb = (L, a, b) => {
    const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
    const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
    const s_ = L - 0.0894841775 * a - 1.291485548 * b;
    const l = l_ * l_ * l_;
    const m = m_ * m_ * m_;
    const s = s_ * s_ * s_;
    return [
      gamma(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
      gamma(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
      gamma(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
    ];
  };
  /* Nullish coalescing below, never a falsy-or default. A NaN channel must PROPAGATE so the caller
     can report the element as UNMEASURED; a falsy-or would substitute a real-looking zero, which is
     the same silent substitution that produced two rounds of false 1.00:1 results.
     (No backticks anywhere in this template literal: one would close it and turn the rest of the
     source into code. That is exactly how this file failed to parse on its first run.) */
  /* THE BUG THIS FUNCTION SHIPPED WITH, and the reason every figure Commits 3 and 4 recorded was
     inflated. Alpha was read ONLY from a slash-separated component. But
     getComputedStyle(el).backgroundColor returns the LEGACY comma form for a transparent background --
     rgba(0, 0, 0, 0) -- where alpha is the fourth COMMA value. So vals became [0,0,0,0] and alpha
     defaulted to 1, the rgb() branch returned opaque black, and effectiveBg accepted the first
     transparent ancestor as a painted black backdrop and stopped walking.

     Black flatters light text on dark navy, so nothing looked broken: four separate tables of
     plausible ratios came out, each one too high. It was caught by arithmetic, not by a test --
     the recorded 5.65, 9.76, 11.84 and 15.43 all match a pure-black backdrop to two decimals and
     match no real surface in this palette. The file's own header had even noted that this spelling
     exists (see the canvas note above) while the parser went on mishandling it.

     Alpha is therefore taken from a trailing slash component when present, and otherwise from the
     FOURTH comma component when there is one. Both spellings are covered, and a value the function
     cannot make sense of still yields a non-finite alpha so the caller reports UNMEASURED. */
  const numbers = (body) => {
    const parts = body.split("/");
    const main = parts[0];
    const slashAlpha = parts[1];
    const components = main
      .trim()
      .split(/[\s,]+/)
      .map((piece) => (piece.endsWith("%") ? parseFloat(piece) / 100 : parseFloat(piece)));
    /* The legacy comma form puts alpha fourth: rgba(r, g, b, a). The modern form never does -- it
       uses a slash -- so a fourth component can only be alpha. */
    const commaAlpha = components.length > 3 ? components[3] : undefined;
    const vals = components.slice(0, 3);
    const rawAlpha = slashAlpha !== undefined ? slashAlpha.trim() : undefined;
    const alpha =
      rawAlpha !== undefined
        ? rawAlpha.endsWith("%")
          ? parseFloat(rawAlpha) / 100
          : parseFloat(rawAlpha)
        : commaAlpha !== undefined
          ? commaAlpha
          : 1;
    return { vals: vals, alpha: Number.isFinite(alpha) ? alpha : Number.NaN };
  };
  /* Returns [r, g, b, a], or NaNs for a colour this probe does not understand. NaNs are deliberate:
     an unparseable colour must be reported as UNMEASURED, never silently treated as transparent --
     that substitution is what produced two rounds of false 1.00:1 results. */
  const normalise = (colour) => {
    const c = String(colour).trim();
    if (c === "transparent") return [0, 0, 0, 0];
    let m = /^rgba?\(([^)]+)\)$/.exec(c);
    if (m !== null) {
      const parsed = numbers(m[1]);
      return [parsed.vals[0] ?? 0, parsed.vals[1] ?? 0, parsed.vals[2] ?? 0, parsed.alpha];
    }
    m = /^#([0-9a-f]{6})$/i.exec(c);
    if (m !== null) {
      const h = m[1];
      return [
        parseInt(h.slice(0, 2), 16),
        parseInt(h.slice(2, 4), 16),
        parseInt(h.slice(4, 6), 16),
        1,
      ];
    }
    m = /^oklab\(([^)]+)\)$/.exec(c);
    if (m !== null) {
      const parsed = numbers(m[1]);
      const rgb = oklabToRgb(parsed.vals[0] ?? 0, parsed.vals[1] ?? 0, parsed.vals[2] ?? 0);
      return [rgb[0], rgb[1], rgb[2], parsed.alpha];
    }
    m = /^oklch\(([^)]+)\)$/.exec(c);
    if (m !== null) {
      const parsed = numbers(m[1]);
      const L = parsed.vals[0] ?? 0;
      const C = parsed.vals[1] ?? 0;
      const rad = ((parsed.vals[2] ?? 0) * Math.PI) / 180;
      const rgb = oklabToRgb(L, C * Math.cos(rad), C * Math.sin(rad));
      return [rgb[0], rgb[1], rgb[2], parsed.alpha];
    }
    return [Number.NaN, Number.NaN, Number.NaN, Number.NaN];
  };
  const lin = (v) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  const lum = (rgb) => 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2]);
  const ratio = (fg, bg) => {
    const a = lum(fg);
    const b = lum(bg);
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  };
  /* The first ancestor with a non-transparent background: what is actually painted behind. This is
     the resolution step axe declines to take when elements overlap. */
  const effectiveBg = (el) => {
    let node = el;
    while (node !== null && node !== undefined) {
      const c = normalise(getComputedStyle(node).backgroundColor);
      if (c[3] > 0) return [c[0], c[1], c[2]];
      node = node.parentElement;
    }
    return [10, 15, 26]; /* navy-950, the documented page background */
  };
  const composite = (fg, bg, alpha) =>
    fg.map((f, i) => Math.round(alpha * f + (1 - alpha) * bg[i]));
  /* Visually hidden content carries no contrast obligation -- it is never painted. axe skips such
     nodes for the same reason, and including them manufactures failures against invisible elements. */
  const isVisuallyHidden = (el) => {
    const style = getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none") return true;
    if (parseFloat(style.opacity) === 0) return true;
    if (style.clipPath !== "none" && style.clipPath !== "") return true;
    if (el.classList && el.classList.contains("sr-only")) return true;
    const box = el.getBoundingClientRect();
    return box.width <= 1 || box.height <= 1;
  };
  window.__mandateColour = {
    normalise: normalise,
    ratio: ratio,
    effectiveBg: effectiveBg,
    composite: composite,
    isVisuallyHidden: isVisuallyHidden,
  };
})();
`;

/** Install the probe so it is present on every navigation in this page's lifetime. */
export async function installColourProbe(page: Page): Promise<void> {
  await page.addInitScript({ content: COLOUR_PROBE_SOURCE });
}
