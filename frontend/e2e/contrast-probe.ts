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
 * `text-parchment-200/60` is parchment-200 (#e8dcc0) at 60% over navy-900 (#0f1626): 5.45:1 offline,
 * 5.57:1 over navy-950. axe independently reported 4.16:1 for the same token at 50%, matching the
 * same offline calculation, which is why this figure is treated as known rather than assumed. The
 * band absorbs the 1-2% shift the OKLab -> sRGB round trip can introduce.
 */
export const CALIBRATION = {
  className: "text-parchment-200/60",
  minRatio: 5.2,
  maxRatio: 5.7,
  offlineNote:
    "parchment-200 at 60% measures 5.45:1 on navy-900 and 5.57:1 on navy-950 by offline calculation; " +
    "axe independently reported 4.16:1 for the same token at 50%",
} as const;

/** The WCAG bars used by the two callers. 4.5:1 is SC 1.4.3 for normal text; 3:1 is SC 1.4.11 for a
 * graphical object, which is what a 2px icon stroke is. */
export const TEXT_CONTRAST_MINIMUM = 4.5;
export const NON_TEXT_CONTRAST_MINIMUM = 3;

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
  const numbers = (body) => {
    const parts = body.split("/");
    const main = parts[0];
    const alphaPart = parts[1];
    const vals = main
      .trim()
      .split(/[\s,]+/)
      .map((piece) => (piece.endsWith("%") ? parseFloat(piece) / 100 : parseFloat(piece)));
    const alpha =
      alphaPart === undefined
        ? 1
        : alphaPart.trim().endsWith("%")
          ? parseFloat(alphaPart) / 100
          : parseFloat(alphaPart);
    return { vals: vals, alpha: Number.isFinite(alpha) ? alpha : 1 };
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
