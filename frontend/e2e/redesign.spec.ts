/**
 * Gate 4A3 map-led redesign: the cumulative browser checks, one tagged block per step (`@m1`, ...).
 *
 * Its own server, on the REAL scenarios, with a temporary save root (the `verify-ux` pattern).
 * Output: `MANDATE_REDESIGN_OUT` names the artifact and is REQUIRED; it is written with `wx`.
 *
 * @m1 -- the map dashboard, at 1440, 960, 820, 720, 390 and 320:
 *   - the built stylesheet actually loads and its layout rules apply (the Places grid's columns);
 *   - the country map, its title plate (the national tint) and the Places list render;
 *   - every pin has a Places twin with the same accessible name, and both lead to the same screen;
 *   - pins never overlap, and every pin and place is at least 44 x 44 px;
 *   - one national wash: every part of the country carries the same fill;
 *   - no horizontal overflow; axe finds nothing on the map or the list;
 *   - the screen navigation is discoverable: all of it visible from 768 px, scroll arrows below;
 *   - on narrow maps the title plate sits above the picture, not over the country;
 *   - keyboard (Enter) on every pin and every place, and touch (`tap`) on phones: the destination
 *     opens, the nav marks it current, and focus lands on its heading.
 */

import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
const SCENARIO_ROOT = path.join(process.cwd(), "..", "data", "scenarios");
const OUT_NAME = process.env.MANDATE_REDESIGN_OUT;
const SAFE_NAME = /^[a-z0-9][a-z0-9.-]*$/;

const WIDTHS = [
  { width: 1440, height: 900 },
  { width: 960, height: 900 },
  { width: 820, height: 900 },
  { width: 720, height: 900 },
  { width: 390, height: 844 },
  { width: 320, height: 800 },
] as const;

/** The seven places and the nav entry each must open (`src/greybox/map/places.ts`). */
const PLACES = [
  { name: "Parliament", opens: "Legislature" },
  { name: "Palace", opens: "Government" },
  { name: "Constitution hall", opens: "Constitution" },
  { name: "Treasury", opens: "Decisions" },
  { name: "Archive", opens: "History" },
  { name: "Embassies", opens: "Relationships" },
  { name: "Garrison", opens: "Strategic map" },
] as const;

function freePort(): number {
  const script =
    "const s=require('node:net').createServer();" +
    "s.listen(0,'127.0.0.1',()=>{const a=s.address();" +
    "process.stdout.write(String(typeof a==='object'&&a?a.port:0));s.close();});";
  return Number(execFileSync(process.execPath, ["-e", script], { encoding: "utf-8" }).trim());
}

let server: ChildProcess | null = null;
let base = "";
const results: Record<string, unknown>[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  if (OUT_NAME === undefined || !SAFE_NAME.test(OUT_NAME) || OUT_NAME.includes("..")) {
    throw new Error("MANDATE_REDESIGN_OUT is required and must be a safe artifact name");
  }
});

test.afterAll(() => {
  server?.kill("SIGINT");
  if (OUT_NAME === undefined) return;
  mkdirSync(REVIEW_DIR, { recursive: true });
  writeFileSync(
    path.join(REVIEW_DIR, `${OUT_NAME}.json`),
    `${JSON.stringify({ gate: "4A3 map-led redesign", out: OUT_NAME, results }, null, 2)}\n`,
    { flag: "wx" },
  );
});

async function ensureServer(page: Page): Promise<void> {
  if (server !== null) return;
  const saveRoot = mkdtempSync(path.join(tmpdir(), "mandate-redesign-"));
  const port = freePort();
  server = spawn(
    "uv",
    [
      "run", "mandate-gui",
      "--port", String(port),
      "--frontend-dist", path.join(process.cwd(), "dist"),
      "--scenario-root", SCENARIO_ROOT,
      "--save-root", path.join(saveRoot, "saves"),
    ],
    { cwd: path.join(process.cwd(), "..", "backend"), stdio: "ignore" },
  );
  base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 60; i += 1) {
    const ok = await page.request.get(`${base}/api/scenarios`).then((r) => r.ok()).catch(() => false);
    if (ok) return;
    await page.waitForTimeout(500);
  }
  throw new Error("the redesign server never became ready");
}

async function startValdrun(page: Page): Promise<void> {
  await page.goto(`${base}/`);
  const start = page.getByRole("button", { name: "Start Kingdom of Valdrun" });
  await start.waitFor({ state: "visible", timeout: 30_000 });
  const pending = page.waitForResponse(
    (r) => r.url().includes("/api/game/new") && r.request().method() === "POST",
    { timeout: 60_000 },
  );
  await start.click();
  expect((await pending).status()).toBe(200);
  await page.getByRole("navigation", { name: "Screens" }).waitFor();
}

async function openDashboard(page: Page): Promise<void> {
  const entry = page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name: "Dashboard", exact: true });
  await entry.click();
  await expect(entry).toHaveAttribute("aria-current", "page");
  await page.locator("[data-map-pin]").first().waitFor();
}

/** Open `place` by `how` from the Dashboard, then check where we landed. */
async function openPlace(
  page: Page,
  scope: "map" | "list",
  place: (typeof PLACES)[number],
  how: "enter" | "tap",
): Promise<string> {
  await openDashboard(page);
  const name = `${place.name}: opens ${place.opens}`;
  const control =
    scope === "map"
      ? page.locator("[data-map-pin]").and(page.getByRole("button", { name, exact: true }))
      : page.getByTestId("places-list").getByRole("button", { name, exact: true });
  await expect(control).toHaveCount(1);
  if (how === "enter") {
    await control.focus();
    await page.keyboard.press("Enter");
  } else {
    await control.tap();
  }
  const navEntry = page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name: place.opens, exact: true });
  await expect(navEntry).toHaveAttribute("aria-current", "page");
  await expect
    .poll(() => page.evaluate(() => document.activeElement?.closest("main") !== null && document.activeElement?.tagName === "H2"))
    .toBe(true);
  return page.evaluate(() => document.activeElement?.textContent?.trim() ?? "");
}

function geometryLayoutIsTall(layout: string | null): boolean {
  return layout === "tall";
}

async function newPage(browser: Browser, width: number, height: number): Promise<Page> {
  const context = await browser.newContext({ viewport: { width, height }, hasTouch: width < 1024 });
  return context.newPage();
}

for (const viewport of WIDTHS) {
  test(`@m1 the map dashboard -- ${viewport.width}px`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newPage(browser, viewport.width, viewport.height);
    await ensureServer(page);

    // The built stylesheet loads, and its rules apply.
    const cssLoads: { url: string; status: number }[] = [];
    page.on("response", (r) => {
      if (r.url().endsWith(".css")) cssLoads.push({ url: r.url(), status: r.status() });
    });
    await startValdrun(page);
    await openDashboard(page);
    expect(cssLoads.length, "the stylesheet was requested").toBeGreaterThan(0);
    expect(cssLoads.every((c) => c.status === 200 || c.status === 304)).toBe(true);
    const css = await (await page.request.get(cssLoads[0]!.url)).text();
    expect(css).toContain("--color-navy-950");
    const applied = await page.evaluate(() => {
      const grid = document.querySelector('[data-testid="places-grid"]')!;
      const panel = document.querySelector('section[aria-label="The country"] section')!;
      return {
        gridDisplay: getComputedStyle(grid).display,
        tracks: getComputedStyle(grid).gridTemplateColumns.split(" ").filter(Boolean).length,
        panelBackground: getComputedStyle(panel).backgroundColor,
        token: getComputedStyle(document.documentElement).getPropertyValue("--color-navy-900").trim(),
      };
    });
    expect(applied.gridDisplay).toBe("grid");
    // The Places grid's responsive rule: 1 column on phones, 2 from `sm` (640), 4 from `xl` (1280).
    const expectedTracks = viewport.width >= 1280 ? 4 : viewport.width >= 640 ? 2 : 1;
    expect(applied.tracks, "the stylesheet's responsive grid rule applies").toBe(expectedTracks);
    expect(applied.token).toBe("#0f1626");
    expect(applied.panelBackground).toBe("rgb(15, 22, 38)");

    // The map, the plate and the list.
    const map = page.getByTestId("country-map");
    await expect(map).toBeVisible();
    await expect(page.getByTestId("national-tint")).toBeVisible();
    const pins = page.locator("[data-map-pin]");
    const places = page.getByTestId("places-list").getByRole("button");
    await expect(pins).toHaveCount(PLACES.length);
    await expect(places).toHaveCount(PLACES.length);
    const pinNames = await pins.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")).sort());
    const placeNames = await places.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")).sort());
    expect(pinNames, "every pin has a Places twin with the same name").toEqual(placeNames);
    expect(pinNames).toEqual(PLACES.map((p) => `${p.name}: opens ${p.opens}`).sort());

    // No overlap; 44 x 44 targets.
    const geometry = await page.evaluate(() => {
      const boxes = [...document.querySelectorAll("[data-map-pin]")].map((pin) => {
        const parts = [...pin.querySelectorAll(":scope > span")].map((p) => p.getBoundingClientRect());
        const own = pin.getBoundingClientRect();
        return {
          name: pin.getAttribute("aria-label")!,
          l: Math.min(...parts.map((r) => r.left)), t: Math.min(...parts.map((r) => r.top)),
          r: Math.max(...parts.map((r) => r.right)), b: Math.max(...parts.map((r) => r.bottom)),
          w: own.width, h: own.height,
        };
      });
      const overlaps: string[] = [];
      let minGap = Infinity;
      for (let i = 0; i < boxes.length; i += 1) for (let j = i + 1; j < boxes.length; j += 1) {
        const a = boxes[i]!, c = boxes[j]!;
        if (a.l < c.r && c.l < a.r && a.t < c.b && c.t < a.b) overlaps.push(`${a.name} x ${c.name}`);
        const gx = Math.max(0, Math.max(a.l, c.l) - Math.min(a.r, c.r));
        const gy = Math.max(0, Math.max(a.t, c.t) - Math.min(a.b, c.b));
        minGap = Math.min(minGap, Math.hypot(gx, gy));
      }
      const small = [...document.querySelectorAll('[data-map-pin], [data-testid="places-list"] button')]
        .map((e) => ({ name: e.getAttribute("aria-label"), r: e.getBoundingClientRect() }))
        .filter(({ r }) => r.width < 44 || r.height < 44)
        .map(({ name, r }) => `${name} ${Math.round(r.width)}x${Math.round(r.height)}`);
      const washes = [...document.querySelectorAll("[data-national-wash]")].map((e) => getComputedStyle(e).fill);
      // The conformance sweeps' own clipping rule, applied to every node of every pin: no badge or
      // placard may stick out of its box.
      const clipped = [...document.querySelectorAll("[data-map-pin], [data-map-pin] *")]
        .map((e) => e as HTMLElement)
        .filter((e) => e.clientWidth > 0 && e.scrollWidth > e.clientWidth + 2)
        .map((e) => `${e.closest("[data-map-pin]")!.getAttribute("aria-label")}: ${e.tagName.toLowerCase()}`);
      // Every text backdrop on a pin is an authored surface (the probe's navy-950), never parchment.
      const pinTextBackdrops = [...document.querySelectorAll("[data-map-pin] span")]
        .filter((e) => (e.textContent ?? "").trim() !== "" && e.children.length === 0)
        .map((e) => getComputedStyle(e).backgroundColor);
      return {
        overlaps, minGap, small, washes, clipped, pinTextBackdrops,
        layout: document.querySelector('[data-testid="country-map"]')!.getAttribute("data-layout"),
        overflow: { scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth },
      };
    });
    expect(geometry.overlaps, "no two pins overlap").toEqual([]);
    expect(geometry.small, "every pin and place is at least 44 x 44").toEqual([]);
    expect(geometry.clipped, "no pin's badge or placard sticks out of its box").toEqual([]);
    expect(geometry.pinTextBackdrops.length, "each pin carries a number or a name").toBe(PLACES.length);
    expect(new Set(geometry.pinTextBackdrops), "pin text sits on navy-950").toEqual(new Set(["rgb(10, 15, 26)"]));
    expect(geometry.washes.length).toBeGreaterThan(0);
    expect(new Set(geometry.washes).size, "one national wash over the whole country").toBe(1);
    expect(geometry.overflow.scrollWidth, `no page overflow at ${viewport.width}px`).toBeLessThanOrEqual(
      geometry.overflow.clientWidth,
    );

    // Navigation is discoverable: from 768 px every destination is visible (the row wraps); below,
    // the row scrolls and an arrow shows whenever more lies to that side.
    const nav = await page.evaluate(() => {
      const row = document.querySelector('[data-testid="nav-row"]')!;
      const box = row.getBoundingClientRect();
      const buttons = [...row.querySelectorAll("button")];
      return {
        count: buttons.length,
        clipped: buttons.filter((b) => {
          const r = b.getBoundingClientRect();
          return r.right > box.right + 1 || r.left < box.left - 1;
        }).length,
        overflowing: row.scrollWidth > row.clientWidth + 1,
        arrows: [...document.querySelectorAll("[data-nav-scroll]")].map((a) => (a as HTMLElement).dataset.navScroll),
      };
    });
    expect(nav.count).toBe(12);
    if (viewport.width >= 768) {
      expect(nav.clipped, "every destination visible from 768 px").toBe(0);
      expect(nav.arrows).toEqual([]);
    } else {
      expect(nav.overflowing, "the phone row scrolls").toBe(true);
      expect(nav.arrows, "an arrow shows the row continues").toContain("right");
      await page.locator('[data-nav-scroll="right"]').click();
      await expect(page.locator('[data-nav-scroll="left"]')).toBeVisible();
    }
    // On narrow (tall) maps the title plate sits above the picture, never over the country.
    const plateClear = await page.evaluate(() => {
      const plate = document.querySelector('[data-testid="national-tint"]')!.getBoundingClientRect();
      return [...document.querySelectorAll("[data-national-wash]")].every((land) => {
        const r = land.getBoundingClientRect();
        return plate.right <= r.left || r.right <= plate.left || plate.bottom <= r.top || r.bottom <= plate.top;
      });
    });
    if (geometryLayoutIsTall(await map.getAttribute("data-layout"))) {
      expect(plateClear, "the plate does not cover the country").toBe(true);
    }

    const axe = await new AxeBuilder({ page })
      .include('section[aria-label="The country"]')
      .analyze();
    expect(axe.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
    await page.screenshot({ path: path.join(REVIEW_DIR, `${OUT_NAME}-shots`, `dashboard-${viewport.width}.png`), fullPage: true });

    // Every place, both ways in: keyboard on all widths, touch on phones.
    const landed: Record<string, string> = {};
    for (const place of PLACES) {
      landed[`map:${place.name}`] = await openPlace(page, "map", place, "enter");
      landed[`list:${place.name}`] = await openPlace(page, "list", place, "enter");
      if (viewport.width < 1024) {
        landed[`tap:${place.name}`] = await openPlace(page, "map", place, "tap");
      }
    }
    for (const place of PLACES) {
      expect(landed[`map:${place.name}`], `pin and list land on the same heading: ${place.name}`).toBe(
        landed[`list:${place.name}`],
      );
    }

    results.push({
      block: "m1",
      width: viewport.width,
      layout: geometry.layout,
      css: cssLoads.map((c) => c.status),
      tracks: applied.tracks,
      minPinGapPx: Math.round(geometry.minGap * 10) / 10,
      wash: geometry.washes[0],
      landedHeadings: landed,
    });
    await page.context().close();
  });
}
