/**
 * Gate 4A3 M-5 (G7): colour contrast DECIDED on a surface, shared by the `redesign` and `victory` specs.
 *
 * axe's `color-contrast` leaves some nodes "incomplete": SVG text sitting on drawn shapes (axe cannot
 * see them), single glyphs it declines to judge, and cells scrolled out of a table's own scroll box.
 * Each such node is MEASURED here instead, never exempted, and must reach 4.5:1:
 *   - SVG `<text>`: against the shapes actually painted under its centre (brought into view first),
 *     composited bottom-up over the page backdrop; a gradient is bounded by its WORST stop;
 *   - HTML text: against its first painted ancestor, the conformance sweeps' own rule.
 * A node that cannot be measured fails. The calibrated colour probe (`contrast-probe.ts`) does the
 * colour maths and must reproduce its calibration first; the page must have it installed
 * (`installColourProbe`) before its first navigation.
 */

import { AxeBuilder } from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

import { CALIBRATION, RATIO_TOLERANCE, TEXT_CONTRAST_MINIMUM } from "./contrast-probe";

/** Measure an SVG `<text>` axe could not decide: its fill against the SVG shapes actually painted
 * under its centre, composited bottom-up over the page backdrop, with the calibrated probe's own
 * colour maths. A gradient or other unparseable paint is returned UNMEASURED (ratio -1), never
 * guessed. */
export async function measureSvgText(page: Page, target: string) {
  return page.evaluate((sel) => {
    const probe = (window as unknown as { __mandateColour: any }).__mandateColour;
    return [...document.querySelectorAll(sel)].map((node) => {
      const text = node as SVGTextElement;
      // Hit-testing only sees what is on screen: bring the text into view first, and refuse to
      // measure a point still outside the viewport rather than fall back to the page backdrop.
      text.scrollIntoView({ block: "center", inline: "center" });
      const box = text.getBoundingClientRect();
      const x = box.left + box.width / 2;
      const y = box.top + box.height / 2;
      const onScreen = x >= 0 && y >= 0 && x <= window.innerWidth && y <= window.innerHeight;
      const shapes = document
        .elementsFromPoint(x, y)
        .filter((el) => el !== text && ["path", "rect", "circle", "ellipse", "polygon"].includes(el.tagName.toLowerCase()));
      const svg = text.ownerSVGElement as Element;
      // A shape's paint: a colour, or -- for a gradient -- each of its stop colours. Every
      // combination is composited and the WORST ratio kept, so a gradient is bounded, not guessed.
      const paints = (shape: Element): number[][] | null => {
        const style = getComputedStyle(shape);
        const opacity = parseFloat(style.fillOpacity || "1") * parseFloat(style.opacity || "1");
        const ref = /^url\("?#([^")]+)"?\)$/.exec(style.fill);
        if (ref !== null) {
          const stops = [...(document.getElementById(ref[1]!)?.querySelectorAll("stop") ?? [])].map((stop) => {
            const st = getComputedStyle(stop);
            const c = probe.normalise(st.stopColor);
            return [c[0], c[1], c[2], c[3] * parseFloat(st.stopOpacity || "1") * opacity];
          });
          return stops.length > 0 && stops.every((c) => Number.isFinite(c[0])) ? stops : null;
        }
        const c = probe.normalise(style.fill);
        return Number.isFinite(c[0]) ? [[c[0], c[1], c[2], c[3] * opacity]] : null;
      };
      let backdrops: number[][] = [probe.effectiveBg(svg)];
      let unmeasured = false;
      const layers: string[] = [];
      for (const shape of shapes.reverse()) {
        if (getComputedStyle(shape).fill === "none") continue;
        const options = paints(shape);
        if (options === null) { unmeasured = true; continue; }
        layers.push(`${shape.tagName.toLowerCase()}:${getComputedStyle(shape).fill}`);
        backdrops = backdrops.flatMap((bg) => options.map((p) => probe.composite([p[0], p[1], p[2]], bg, p[3])));
      }
      const style = getComputedStyle(text);
      const fg = probe.normalise(style.fill);
      const alpha = fg[3] * parseFloat(style.fillOpacity || "1") * parseFloat(style.opacity || "1");
      const ratios = backdrops.map((bg) => {
        const painted = alpha < 1 ? probe.composite([fg[0], fg[1], fg[2]], bg, alpha) : [fg[0], fg[1], fg[2]];
        return probe.ratio(painted, bg) as number;
      });
      const ratio = unmeasured || !onScreen || !Number.isFinite(fg[0]) ? -1 : Math.round(Math.min(...ratios) * 100) / 100;
      return { target: sel, text: (text.textContent ?? "").trim(), fill: style.fill, layers, backdrops: backdrops.length, ratio };
    });
  }, target);
}

/** axe on `selector`: no violation, and colour contrast DECIDED. Every node axe leaves "incomplete" is
 * MEASURED instead, at 4.5:1 or better: SVG `<text>` against the shapes painted under it
 * (`measureSvgText`), HTML text against its first painted ancestor. A node that cannot be measured
 * fails. The probe is calibrated first. */
export async function decidedContrast(page: Page, selector: string, label: string) {
  await page.locator(selector).first().scrollIntoViewIfNeeded();
  // The probe is trusted only once it reproduces its calibration: parchment-200 (#e8dcc0) at 60% over
  // navy-900 (#0f1626), computed offline as CALIBRATION.expectedRatio.
  const known = await page.evaluate(() => {
    const probe = (window as unknown as { __mandateColour: any }).__mandateColour;
    const fg = probe.normalise("#e8dcc0");
    const bg = probe.normalise("#0f1626");
    const painted = probe.composite([fg[0], fg[1], fg[2]], [bg[0], bg[1], bg[2]], 0.6);
    return probe.ratio(painted, [bg[0], bg[1], bg[2]]);
  });
  expect(Math.abs(known - CALIBRATION.expectedRatio), `${label}: the probe reproduces its calibration`).toBeLessThanOrEqual(RATIO_TOLERANCE);
  const all = await new AxeBuilder({ page }).include(selector).analyze();
  expect(all.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`), `${label}: axe`).toEqual([]);
  const contrast = await new AxeBuilder({ page }).include(selector).withRules(["color-contrast"]).analyze();
  const undecided = contrast.incomplete.flatMap((v) =>
    v.nodes.map((n) => ({ target: n.target[n.target.length - 1] as string, why: n.any.map((a) => a.message).join("; ") })),
  );
  const kinds = await page.evaluate((sels) => sels.map((sel) => {
    const found = [...document.querySelectorAll(sel)];
    if (found.length === 0) return "missing";
    if (found.every((el) => el instanceof SVGElement && el.tagName.toLowerCase() === "text")) return "svg-text";
    if (found.every((el) => el instanceof HTMLElement)) return "html";
    return "other";
  }), undecided.map((u) => u.target));
  expect(undecided.filter((_, i) => kinds[i] === "missing" || kinds[i] === "other"), `${label}: every undecided node is measurable`).toEqual([]);
  // SVG text: against the shapes under it. HTML text: the probe's own rule -- its colour against the
  // first painted ancestor (an authored surface), as the conformance sweeps measure every text owner.
  const measured: { target: string; why: string; kind: string; text: string; ratio: number; backdrop: string }[] = [];
  for (const [i, u] of undecided.entries()) {
    if (kinds[i] === "svg-text") {
      for (const m of await measureSvgText(page, u.target)) {
        measured.push({ target: u.target, why: u.why, kind: "svg-text", text: m.text, ratio: m.ratio, backdrop: m.layers.join(" > ") });
      }
    } else {
      const html = await page.evaluate((sel) => {
        const probe = (window as unknown as { __mandateColour: any }).__mandateColour;
        return [...document.querySelectorAll(sel)].map((el) => {
          const style = getComputedStyle(el);
          const fg = probe.normalise(style.color);
          const bg = probe.effectiveBg(el);
          const painted = fg[3] < 1 ? probe.composite([fg[0], fg[1], fg[2]], bg, fg[3]) : [fg[0], fg[1], fg[2]];
          return {
            text: (el.textContent ?? "").trim(),
            ratio: Number.isFinite(fg[0]) ? Math.round(probe.ratio(painted, bg) * 100) / 100 : -1,
            backdrop: `rgb(${bg.join(",")})`,
          };
        });
      }, u.target);
      for (const m of html) measured.push({ target: u.target, why: u.why, kind: "html", ...m });
    }
  }
  for (const m of measured) {
    expect(m.ratio, `${label}: ${m.target} "${m.text}" measured (${m.kind})`).toBeGreaterThanOrEqual(TEXT_CONTRAST_MINIMUM);
  }
  return { passes: all.passes.length, measuredSvgText: measured };
}

