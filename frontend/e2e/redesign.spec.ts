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
 *
 * @m2 -- Parliament and the shared preview:
 *   - at every width, on Arken (two chambers) and Valdrun: the engine's thresholds, every seat drawn,
 *     seats at least 6 px and never overlapping, the stylesheet applied, no overflow, axe clean, then
 *     a preview FROM Parliament whose numbers equal the response, with bloc rows that sum;
 *   - journeys at 1440 and 390 (touch): an edit after Preview, a held response edited away, a
 *     response held across a resolve, a decree (no tallies), a failed vote that appears only under
 *     "Last recorded vote";
 *   - keyboard: a late response never steals focus, from Decisions or from Parliament.
 *
 * @m3 -- the bloc panel and negotiation:
 *   - at every width, with the panel open: placement (beside from 1280 px, inline below), no overflow
 *     or clipped node, 44 px controls, axe clean on main;
 *   - journey A (Arken, 1440 and 390 touch): stage Maret Kuusk's bargain from the panel, preview,
 *     resolve, then both chambers' stored tallies under "Last recorded vote";
 *   - journey B (Valdrun, 1440 and 390): the qualifying reform, Nadia Brekke refuses (no price),
 *     influence 300 from the panel, preview, resolve, the amendment's totals and its note;
 *   - keyboard: open, stage, Escape back to the row, swap blocs;
 *   - replacement, on a LABELLED ALTERED decision-options response (a second willing leader), never
 *     previewed or resolved;
 *   - parity: the server refuses a decree-route bargain, and the panel gives the decree reason.
 *
 * @m4 -- the result restructure (and, per Revision 2a, the proposal card and reactions in journeys A
 * and B above):
 *   - at every width, on Arken's bargain turn: the proposal card's recorded tallies equal the resolve
 *     response, rows sum, filled seats equal the recorded support, no overflow or clipped node, 44 px
 *     controls, axe clean on main, every bloc reaction grouped, a screenshot;
 *   - one palette per vote: each party's colour in the result equals its colour on Parliament;
 *   - History after a LATER turn: the card, the people and the portrait equal what live showed;
 *   - Valdrun: a decree turn ("Enacted by decree", no tallies) and a no-proposal turn;
 *   - keyboard: Trace to a line in the card and to a reaction under a bloc.
 *
 * @m5 -- consolidation (the acceptance journeys and the gaps the M-5 audit found):
 *   - journeys A (Arken bargain) and B (Valdrun amendment influence) FROM THE DASHBOARD MAP, at the
 *     mockups' sizes 1440x900 (keyboard: Tab to a pin, Space or Enter), 390x844 and 320x800 (every
 *     step tapped): objective, place, bloc, stage, Preview (supporting seats), the draft surviving
 *     Dashboard -> Decisions -> Parliament, resolve, the card and reactions, History equal to live;
 *     the body's background token, every seat diagram with a box, and colour contrast DECIDED (no
 *     axe "incomplete") on the map, Parliament with the panel open, and the result;
 *   - input: every pin and Places button is a Tab stop and opens by Enter and by Space; every Places
 *     button opens by tap;
 *   - states: an unaffordable draft on Parliament (and the server refusing the same set), a failed
 *     vote's result card;
 *   - the visual record: the eleven approved M-V views re-shot at the mockups' own sizes.
 */

import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { AxeBuilder } from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

import { decidedContrast } from "./contrast-decided";
import { installColourProbe } from "./contrast-probe";

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

/**
 * The spec's OWN API calls (not the page's). `Connection: close`, so each call uses a fresh connection:
 * the server (uvicorn) closes an idle keep-alive connection after 5 seconds, and a pooled connection
 * reused at that moment can be closed under the request ("socket hang up", seen once in the M-2 gate
 * run `final5`, 5.02 s after the previous call on the same connection).
 */
function apiGet(page: Page, url: string) {
  return page.request.get(url, { headers: { Connection: "close" } });
}

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
    const ok = await apiGet(page, `${base}/api/scenarios`).then((r) => r.ok()).catch(() => false);
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
    const css = await (await apiGet(page, cssLoads[0]!.url)).text();
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

// ---- @m2: Parliament and the shared preview ---------------------------------------------------

const SCENARIOS = [
  { id: "arken", start: "Start Republic of Arken" },
  { id: "valdrun", start: "Start Kingdom of Valdrun" },
] as const;

async function startScenario(page: Page, start: string): Promise<void> {
  await page.goto(`${base}/`);
  const button = page.getByRole("button", { name: start });
  await button.waitFor({ state: "visible", timeout: 30_000 });
  const pending = page.waitForResponse(
    (r) => r.url().includes("/api/game/new") && r.request().method() === "POST",
    { timeout: 60_000 },
  );
  await button.click();
  expect((await pending).status()).toBe(200);
  await page.getByRole("navigation", { name: "Screens" }).waitFor();
}

function navEntry(page: Page, name: string) {
  return page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name, exact: true });
}

async function visitScreen(page: Page, name: string, how: "click" | "tap" = "click"): Promise<void> {
  const entry = navEntry(page, name);
  if (how === "tap") await entry.tap();
  else await entry.click();
  await expect(entry).toHaveAttribute("aria-current", "page");
}

async function openParliament(page: Page, how: "click" | "tap" = "click"): Promise<void> {
  await visitScreen(page, "Legislature", how);
  await page.getByTestId("parliament-draft").waitFor();
}

async function selectPolicyCard(page: Page, title: string, how: "click" | "tap" = "click"): Promise<void> {
  const select = page.getByRole("group", { name: title }).getByRole("button", { name: "Select" });
  if (how === "tap") await select.tap();
  else await select.click();
}

/** Holds every preview response until `release`; returns the release and a wait for the response. */
async function holdPreviews(page: Page): Promise<{ release: () => void }> {
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/game/preview", async (route) => {
    await gate;
    await route.continue();
  });
  return { release: () => release() };
}

/** The seats of every chamber: their diameters and whether any two overlap. */
async function seatGeometry(page: Page) {
  return page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>('[data-testid="chamber-card"]')].map((card) => {
      const seats = [...card.querySelectorAll("[data-seat]")].map((s) => s.getBoundingClientRect());
      let overlaps = 0;
      for (let i = 0; i < seats.length; i += 1) {
        for (let j = i + 1; j < seats.length; j += 1) {
          const a = seats[i]!;
          const b = seats[j]!;
          const d = Math.hypot(a.x + a.width / 2 - (b.x + b.width / 2), a.y + a.height / 2 - (b.y + b.height / 2));
          if (d < (a.width + b.width) / 2 - 0.01) overlaps += 1;
        }
      }
      return {
        chamber: card.dataset.chamber ?? "",
        seats: seats.length,
        minDiameter: Math.min(...seats.map((s) => Math.min(s.width, s.height))),
        overlaps,
        budget: card.querySelector('[data-testid="budget-threshold"]')?.textContent ?? "",
        amendment: card.querySelector('[data-testid="amendment-threshold"]')?.textContent ?? "",
        background: getComputedStyle(card).backgroundColor,
      };
    }),
  );
}

async function clippedNodes(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    for (const el of Array.from(document.querySelectorAll("main *"))) {
      const node = el as HTMLElement;
      const style = getComputedStyle(node);
      if (style.overflow !== "visible" && style.overflow !== "") continue;
      if (node.scrollWidth > node.clientWidth + 2 && node.clientWidth > 0) {
        out.push(`${node.tagName.toLowerCase()}.${node.className.toString().slice(0, 40)}`);
      }
    }
    return out.slice(0, 8);
  });
}

/** Each chamber card's shown tally, and the sum of its bloc rows. */
async function shownTallies(page: Page) {
  return page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>('[data-testid="chamber-card"]')].map((card) => ({
      chamber: card.dataset.chamber ?? "",
      mode: card.dataset.mode ?? "",
      supporting: card.querySelector('[data-testid="chamber-supporting"]')?.textContent ?? null,
      rowSum: [...card.querySelectorAll('[data-testid="bloc-supporting"]')]
        .map((n) => Number(n.textContent))
        .reduce((a, b) => a + (Number.isNaN(b) ? 0 : b), 0),
      filled: card.querySelectorAll('[data-seat][data-filled="false"]').length,
    })),
  );
}

for (const viewport of WIDTHS) {
  test(`@m2 Parliament -- ${viewport.width}px`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newPage(browser, viewport.width, viewport.height);
    await ensureServer(page);
    const how = viewport.width < 1024 ? "tap" : "click";
    const perScenario: Record<string, unknown>[] = [];
    for (const scenario of SCENARIOS) {
      await startScenario(page, scenario.start);
      const options = await (await apiGet(page, `${base}/api/game/decision-options`)).json();
      await openParliament(page, how);

      // The engine's thresholds, every seat drawn and readable, nothing overflowing.
      const seats = await seatGeometry(page);
      expect(seats.map((s) => s.chamber)).toEqual(options.chamber_details.map((d: { chamber: string }) => d.chamber));
      for (const detail of options.chamber_details as {
        chamber: string;
        total_seats: number;
        budget_required_seats: number;
        amendment_required_seats: number;
      }[]) {
        const shown = seats.find((s) => s.chamber === detail.chamber)!;
        expect(shown.budget).toBe(`A budget needs ${detail.budget_required_seats}`);
        expect(shown.amendment).toBe(`An amendment needs ${detail.amendment_required_seats}`);
        expect(shown.seats, "every seat is drawn").toBe(detail.total_seats);
        expect(shown.minDiameter, `seats at least 6 px at ${viewport.width}`).toBeGreaterThanOrEqual(6);
        expect(shown.overlaps, "no two seats overlap").toBe(0);
        expect(shown.background, "the stylesheet applies").toBe("rgb(15, 22, 38)");
      }
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
        "no page overflow",
      ).toBe(true);
      expect(await clippedNodes(page), "no clipped node").toEqual([]);
      const axe = await new AxeBuilder({ page }).include("main").analyze();
      expect(axe.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
      await page.screenshot({
        path: path.join(REVIEW_DIR, `${OUT_NAME}-shots`, `parliament-${scenario.id}-${viewport.width}.png`),
        fullPage: true,
      });

      // A legislative draft, previewed FROM Parliament: each chamber shows the preview's own tally.
      await visitScreen(page, "Decisions", how);
      await selectPolicyCard(page, "Lower the personal income tax", how);
      await openParliament(page, how);
      const pending = page.waitForResponse((r) => r.url().includes("/api/game/preview") && r.request().method() === "POST");
      const previewButton = page.getByTestId("parliament-draft").getByRole("button", { name: "Preview" });
      if (how === "tap") await previewButton.tap();
      else await previewButton.click();
      const preview = await (await pending).json();
      await expect(page.getByTestId("draft-status")).toHaveText("Preview is current for this draft");
      const tallies = await shownTallies(page);
      for (const chamber of preview.chambers as { chamber: string; supporting_seats: number }[]) {
        const shown = tallies.find((t) => t.chamber === chamber.chamber)!;
        expect(shown.mode).toBe("current");
        expect(shown.supporting).toBe(`${chamber.supporting_seats} supporting if resolved now`);
        expect(shown.rowSum, "bloc rows sum to the chamber's tally").toBe(chamber.supporting_seats);
      }
      expect(await clippedNodes(page), "no clipped node after Preview").toEqual([]);
      const axeAfter = await new AxeBuilder({ page }).include("main").analyze();
      expect(axeAfter.violations.map((v) => v.id)).toEqual([]);
      await page.screenshot({
        path: path.join(REVIEW_DIR, `${OUT_NAME}-shots`, `parliament-${scenario.id}-preview-${viewport.width}.png`),
        fullPage: true,
      });
      perScenario.push({
        scenario: scenario.id,
        seats: seats.map((s) => ({ chamber: s.chamber, seats: s.seats, minDiameterPx: Math.round(s.minDiameter * 100) / 100 })),
        preview: preview.chambers.map((c: { chamber: string; supporting_seats: number; required_seats: number; carries: boolean }) => ({
          chamber: c.chamber,
          supporting: c.supporting_seats,
          required: c.required_seats,
          carries: c.carries,
        })),
      });
    }
    results.push({ block: "m2", width: viewport.width, scenarios: perScenario });
    await page.context().close();
  });
}

for (const viewport of [WIDTHS[0], WIDTHS[4]]) {
  const how = viewport.width < 1024 ? "tap" : "click";

  test(`@m2 freshness journeys -- ${viewport.width}px`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newPage(browser, viewport.width, viewport.height);
    await ensureServer(page);
    const journal: Record<string, unknown> = {};

    // 1. Arken: preview from Parliament, then change the draft in Decisions: the estimate is gone.
    await startScenario(page, "Start Republic of Arken");
    await visitScreen(page, "Decisions", how);
    await selectPolicyCard(page, "Lower the personal income tax", how);
    await openParliament(page, how);
    const first = page.waitForResponse((r) => r.url().includes("/api/game/preview"));
    await page.getByTestId("parliament-draft").getByRole("button", { name: "Preview" }).click();
    await first;
    await expect(page.getByTestId("chamber-supporting").first()).toBeVisible();
    await visitScreen(page, "Decisions", how);
    await selectPolicyCard(page, "Raise the personal income tax", how);
    await openParliament(page, how);
    await expect(page.getByTestId("draft-status")).toContainText("Your draft has changed since the last preview");
    await expect(page.getByTestId("chamber-supporting")).toHaveCount(0);
    journal.editedAfterPreview = "estimate hidden";

    // 2. A held response: Preview, change the draft before it lands, then release it.
    const hold = await holdPreviews(page);
    await page.getByTestId("parliament-draft").getByRole("button", { name: "Preview" }).click();
    await visitScreen(page, "Decisions", how);
    await selectPolicyCard(page, "Lower the personal income tax", how);
    await openParliament(page, how);
    const held = page.waitForResponse((r) => r.url().includes("/api/game/preview"));
    hold.release();
    await held;
    await page.waitForTimeout(300);
    await expect(page.getByTestId("chamber-supporting")).toHaveCount(0);
    journal.heldResponseAfterEdit = "not shown";
    await page.unroute("**/api/game/preview");

    // 3. Held across a resolve: Preview on Decisions, resolve, then release.
    const hold2 = await holdPreviews(page);
    await visitScreen(page, "Decisions", how);
    await page.getByRole("button", { name: "Preview", exact: true }).click();
    await page.getByRole("button", { name: "Resolve turn" }).click();
    const resolved = page.waitForResponse((r) => r.url().includes("/api/game/resolve"));
    await page.getByRole("button", { name: "Confirm and resolve" }).click();
    expect((await resolved).status()).toBe(200);
    const late = page.waitForResponse((r) => r.url().includes("/api/game/preview"));
    hold2.release();
    await late;
    await openParliament(page, how);
    await page.waitForTimeout(300);
    await expect(page.getByTestId("chamber-supporting")).toHaveCount(0);
    journal.heldAcrossResolve = "not shown";
    await page.unroute("**/api/game/preview");

    // 4. Valdrun, decree: no vote is held, so no tallies, even after Preview.
    await startScenario(page, "Start Kingdom of Valdrun");
    await visitScreen(page, "Decisions", how);
    await selectPolicyCard(page, "Raise the personal income tax", how);
    await page.getByRole("radiogroup", { name: "Route" }).getByRole("radio", { name: /^Decree/ }).click();
    await openParliament(page, how);
    await expect(page.getByText("No vote is held on a decree, so the legislature is bypassed.")).toBeVisible();
    const decree = page.waitForResponse((r) => r.url().includes("/api/game/preview"));
    await page.getByTestId("parliament-draft").getByRole("button", { name: "Preview" }).click();
    expect((await (await decree).json()).chambers).toEqual([]);
    await expect(page.getByTestId("draft-status")).toHaveText("Preview is current for this draft");
    await expect(page.getByTestId("chamber-supporting")).toHaveCount(0);
    await expect(page.getByTestId("chamber-tally").first()).toContainText("No vote is held on a decree.");
    journal.decree = "no tallies";

    // 5. Valdrun, legislative: the vote fails, and afterwards it appears ONLY under Last recorded vote.
    await visitScreen(page, "Decisions", how);
    await page.getByRole("radiogroup", { name: "Route" }).getByRole("radio", { name: /^Legislative/ }).click();
    await openParliament(page, how);
    const legislative = page.waitForResponse((r) => r.url().includes("/api/game/preview"));
    await page.getByTestId("parliament-draft").getByRole("button", { name: "Preview" }).click();
    const failing = await (await legislative).json();
    expect(failing.chambers.some((c: { carries: boolean }) => !c.carries)).toBe(true);
    await expect(page.getByTestId("chamber-verdict").first()).toHaveText("Would not carry");
    await visitScreen(page, "Decisions", how);
    await page.getByRole("button", { name: "Resolve turn" }).click();
    const resolve = page.waitForResponse((r) => r.url().includes("/api/game/resolve"));
    await page.getByRole("button", { name: "Confirm and resolve" }).click();
    expect((await resolve).status()).toBe(200);
    const after = await (await apiGet(page, `${base}/api/game/decision-options`)).json();
    const last = after.last_recorded_vote as {
      turn: number;
      vote: { chambers: { chamber: string; supporting_seats: number; required_seats: number; passed: boolean }[] };
    };
    expect(last).not.toBeNull();
    await openParliament(page, how);
    await expect(page.getByRole("heading", { name: `Last recorded vote · turn ${last.turn}` })).toBeVisible();
    const lower = last.vote.chambers[0]!;
    await expect(page.getByTestId("recorded-chamber").first()).toHaveText(
      `Lower chamber: ${lower.supporting_seats} supporting; ${lower.required_seats} required — ${lower.passed ? "carried" : "did not carry"}`,
    );
    await expect(page.getByTestId("chamber-supporting")).toHaveCount(0);
    for (const t of await shownTallies(page)) {
      expect(t.mode, "today's chamber shows no recorded support").toBe("seats");
      expect(t.filled, "no hollow seats").toBe(0);
    }
    await page.screenshot({
      path: path.join(REVIEW_DIR, `${OUT_NAME}-shots`, `parliament-valdrun-recorded-${viewport.width}.png`),
      fullPage: true,
    });
    journal.recordedVote = { turn: last.turn, lower };

    results.push({ block: "m2-journeys", width: viewport.width, journal });
    await page.context().close();
  });
}

test("@m2 a late preview never steals focus (keyboard)", async ({ browser }) => {
  test.setTimeout(300_000);
  const page = await newPage(browser, 1440, 900);
  await ensureServer(page);
  await startScenario(page, "Start Republic of Arken");
  await visitScreen(page, "Decisions");
  await selectPolicyCard(page, "Lower the personal income tax");

  // Decisions -> Preview (held) -> keyboard to Legislature -> release.
  const hold = await holdPreviews(page);
  await page.getByRole("button", { name: "Preview", exact: true }).focus();
  await page.keyboard.press("Enter");
  await navEntry(page, "Legislature").focus();
  await page.keyboard.press("Enter");
  await expect(navEntry(page, "Legislature")).toHaveAttribute("aria-current", "page");
  await page.getByTestId("parliament-draft").waitFor();
  const focusedBefore = await page.evaluate(() => document.activeElement?.textContent?.trim() ?? "");
  const landed = page.waitForResponse((r) => r.url().includes("/api/game/preview"));
  hold.release();
  await landed;
  await expect(page.getByTestId("chamber-supporting").first()).toBeVisible();
  const focusedAfter = await page.evaluate(() => ({
    text: document.activeElement?.textContent?.trim() ?? "",
    inNav: document.activeElement?.closest('nav[aria-label="Screens"]') !== null,
  }));
  expect(focusedAfter.text).toBe(focusedBefore);
  expect(focusedAfter.inNav, "focus stays on the nav entry the player used").toBe(true);
  await expect(page.getByTestId("parliament-announcement")).toHaveText("");

  // Back to Decisions by keyboard: the preview heading does not take focus.
  await navEntry(page, "Decisions").focus();
  await page.keyboard.press("Enter");
  await expect(navEntry(page, "Decisions")).toHaveAttribute("aria-current", "page");
  await page.getByTestId("consequences-panel").waitFor();
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => document.activeElement?.id ?? "")).not.toBe("preview-result-heading");
  await page.unroute("**/api/game/preview");

  // The reverse: Parliament -> Preview (held) -> keyboard to Dashboard -> release.
  await visitScreen(page, "Decisions");
  await selectPolicyCard(page, "Raise the personal income tax");
  await openParliament(page);
  const hold2 = await holdPreviews(page);
  await page.getByTestId("parliament-draft").getByRole("button", { name: "Preview" }).focus();
  await page.keyboard.press("Enter");
  await navEntry(page, "Dashboard").focus();
  await page.keyboard.press("Enter");
  await expect(navEntry(page, "Dashboard")).toHaveAttribute("aria-current", "page");
  const landed2 = page.waitForResponse((r) => r.url().includes("/api/game/preview"));
  hold2.release();
  await landed2;
  await page.waitForTimeout(300);
  expect(
    await page.evaluate(() => document.activeElement?.closest('nav[aria-label="Screens"]') !== null && document.activeElement?.textContent?.trim()),
  ).toBe("Dashboard");
  await page.unroute("**/api/game/preview");
  results.push({ block: "m2-keyboard", focus: "unchanged after late responses, both directions" });
  await page.context().close();
});

// ---- @m3: the bloc panel and negotiation --------------------------------------------------------

function apiPost(page: Page, url: string, data: unknown) {
  return page.request.post(url, { data, headers: { Connection: "close" } });
}

function blocButton(page: Page, chamber: string, key: string) {
  return page.locator(`[data-testid="chamber-card"][data-chamber="${chamber}"] [data-bloc-open="${key}"]`);
}

async function openBlocPanel(page: Page, chamber: string, key: string, how: "click" | "tap" = "click") {
  const button = blocButton(page, chamber, key);
  if (how === "tap") await button.tap();
  else await button.click();
  const panelLocator = page.getByTestId("bloc-panel");
  await expect(panelLocator).toBeVisible();
  return panelLocator;
}

async function resolveFromDecisions(page: Page, how: "click" | "tap") {
  await visitScreen(page, "Decisions", how);
  await page.getByRole("button", { name: "Resolve turn" }).click();
  const pending = page.waitForResponse((r) => r.url().includes("/api/game/resolve") && r.request().method() === "POST", {
    timeout: 120_000,
  });
  await page.getByRole("button", { name: "Confirm and resolve" }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  const body = (await response.json()) as { turnResult: { outcome_headline: string } };
  await expect(page.getByTestId("turn-result-view")).toContainText(body.turnResult.outcome_headline);
  return body;
}

// ---- @m4 helpers: the restructured result ----------------------------------------------------------

type ResultBody = {
  turnResult: {
    turn: number;
    outcome_headline: string;
    no_vote_reason?: string | null;
    recorded_vote?: {
      outcome: string;
      proposal_kind: string;
      blocs_recorded: boolean;
      chambers: {
        chamber: string;
        supporting_seats: number;
        required_seats: number;
        total_seats: number;
        passed: boolean;
        blocs?: { party_id: string; supporting_seats: number }[];
      }[];
    } | null;
    drivers: { reason_id: string; params: Record<string, string | number> }[];
  };
};

const VERDICT_WORD: Record<string, string> = {
  passed_legislative: "Enacted",
  failed_legislative: "Did not carry",
  enacted_by_decree: "Enacted by decree",
  no_proposal: "No proposal",
};

/** The proposal card and the reactions agree with the resolve response, and nothing is ungrouped. */
async function checkResultCard(page: Page, body: ResultBody) {
  const result = body.turnResult;
  const view = page.getByTestId("turn-result-view");
  const card = view.getByTestId("proposal-card");
  await expect(view).toHaveAttribute("data-unmatched-components", "0");
  const word = VERDICT_WORD[result.recorded_vote?.outcome ?? result.no_vote_reason ?? ""]!;
  await expect(card.getByTestId("result-verdict")).toHaveText(word);
  const vote = result.recorded_vote ?? null;
  if (vote === null) {
    await expect(card.getByTestId("result-chamber")).toHaveCount(0);
    await expect(card.locator('[data-testid="hemicycle"], [data-testid="hemicycle-bars"]')).toHaveCount(0);
    return;
  }
  const chambers = card.getByTestId("result-chamber");
  await expect(chambers).toHaveCount(vote.chambers.length);
  for (const [i, c] of vote.chambers.entries()) {
    const node = chambers.nth(i);
    await expect(node.getByTestId("result-chamber-line")).toContainText(
      `${c.supporting_seats} supporting; ${c.required_seats} required — ${c.passed ? "carried" : "did not carry"}`,
    );
    if (vote.blocs_recorded) {
      const rows = c.blocs ?? [];
      expect(rows.reduce((n, r) => n + r.supporting_seats, 0), `${c.chamber}: rows sum`).toBe(c.supporting_seats);
      const svg = node.getByTestId("hemicycle");
      await expect(svg).toHaveAttribute("data-mode", "recorded");
      await expect(svg.locator('[data-seat][data-filled="true"]')).toHaveCount(c.supporting_seats);
    } else {
      await expect(node.locator('[data-testid="hemicycle"], [data-testid="hemicycle-bars"]')).toHaveCount(0);
    }
  }
  if (!vote.blocs_recorded) {
    await expect(card.getByTestId("amendment-blocs-note")).toHaveText("Per-bloc votes are not recorded for amendments.");
    await expect(card.getByTestId("result-bloc-votes")).toHaveCount(0);
  }
}

/** What a reader sees of the card and the reactions -- compared live against History. */
async function resultReading(page: Page) {
  return page.getByTestId("turn-result-view").evaluate((root) => {
    const text = (sel: string) =>
      Array.from(root.querySelectorAll<HTMLElement>(sel))
        .map((n) => n.innerText)
        .join("\n")
        .replace(/\s*Reviewing a past turn\. Rendered by the same component as the live result\./, "")
        .trimEnd();
    return {
      card: text('[data-testid="proposal-card"]'),
      people: text('[data-testid="result-person"]'),
      blocs: text('[data-testid="result-bloc"]'),
      portraits: Array.from(root.querySelectorAll("[data-portrait-ref]")).map((n) => n.getAttribute("data-portrait-ref")),
      filled: Array.from(root.querySelectorAll('[data-seat][data-filled="true"]')).map((n) => n.getAttribute("data-party")),
    };
  });
}

async function openHistoryTurn(page: Page, turn: number, how: "click" | "tap") {
  await visitScreen(page, "History", how);
  const button = page.getByRole("button", { name: new RegExp(`^Turn ${turn} — `) });
  if (how === "tap") await button.tap();
  else await button.click();
  await expect(page.getByTestId("turn-result-view")).toHaveAttribute("data-context", "history");
}

/** Plan the next turn from the result and resolve it with nothing staged. */
async function resolveEmptyTurn(page: Page, how: "click" | "tap") {
  const plan = page.getByRole("button", { name: /^Plan turn \d+$/ });
  if (how === "tap") await plan.tap();
  else await plan.click();
  return resolveFromDecisions(page, how);
}

/** party id -> the fill its seats are drawn in, read from every seat matching `selector`. */
async function seatColours(page: Page, selector: string) {
  return page.evaluate((sel) => {
    const out: Record<string, string[]> = {};
    for (const seat of Array.from(document.querySelectorAll(sel))) {
      const party = seat.getAttribute("data-party") ?? "";
      const fill = getComputedStyle(seat).fill;
      (out[party] ??= []).includes(fill) || out[party]!.push(fill);
    }
    return out;
  }, selector);
}

for (const viewport of WIDTHS) {
  test(`@m3 the bloc panel -- ${viewport.width}px`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newPage(browser, viewport.width, viewport.height);
    await ensureServer(page);
    const how = viewport.width < 1024 ? "tap" : "click";
    await startScenario(page, "Start Republic of Arken");
    await visitScreen(page, "Decisions", how);
    await selectPolicyCard(page, "Lower the personal income tax", how);
    await openParliament(page, how);
    const panelLocator = await openBlocPanel(page, "lower", "rural_alliance/farmers", how);
    await expect(panelLocator.getByRole("heading", { level: 3, name: "Rural Alliance Farmers" })).toBeVisible();
    await expect(panelLocator.getByTestId("leader-offer")).toContainText("Asking price: 105 political capital.");

    // Placement: beside the chambers from 1280 px, inline after its chamber below.
    const placement = await page.evaluate(() => {
      const panelNode = document.querySelector('[data-testid="bloc-panel"]')!;
      return {
        inAside: panelNode.parentElement?.tagName === "ASIDE",
        afterLowerCard:
          (panelNode.previousElementSibling as HTMLElement | null)?.dataset?.chamber === "lower",
      };
    });
    if (viewport.width >= 1280) expect(placement.inAside, "beside the chambers").toBe(true);
    else expect(placement.afterLowerCard, "inline after its chamber").toBe(true);

    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
      "no page overflow with the panel open",
    ).toBe(true);
    expect(await clippedNodes(page), "no clipped node with the panel open").toEqual([]);
    const small = await page.evaluate(() =>
      [...document.querySelectorAll('[data-testid="bloc-panel"] button, [data-testid="bloc-panel"] input')]
        .map((e) => ({ name: e.getAttribute("aria-label") ?? e.textContent?.trim() ?? "", r: e.getBoundingClientRect() }))
        .filter(({ r }) => r.height < 44 || r.width < 44)
        .map(({ name, r }) => `${name} ${Math.round(r.width)}x${Math.round(r.height)}`),
    );
    expect(small, "panel controls at least 44 x 44").toEqual([]);
    const axe = await new AxeBuilder({ page }).include("main").analyze();
    expect(axe.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
    await page.screenshot({
      path: path.join(REVIEW_DIR, `${OUT_NAME}-shots`, `parliament-panel-${viewport.width}.png`),
      fullPage: true,
    });
    results.push({ block: "m3", width: viewport.width, placement });
    await page.context().close();
  });
}

for (const viewport of [WIDTHS[0], WIDTHS[4]]) {
  const how = viewport.width < 1024 ? "tap" : "click";

  test(`@m3 journey A, budget bargaining (Arken) -- ${viewport.width}px`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newPage(browser, viewport.width, viewport.height);
    await ensureServer(page);
    await startScenario(page, "Start Republic of Arken");
    await visitScreen(page, "Decisions", how);
    await selectPolicyCard(page, "Lower the personal income tax", how);
    await openParliament(page, how);
    const panelLocator = await openBlocPanel(page, "lower", "rural_alliance/farmers", how);
    const stage = panelLocator.getByRole("button", { name: "Stage this bargain · 105" });
    if (how === "tap") await stage.tap();
    else await stage.click();
    await expect(panelLocator.getByTestId("bargain-staged-here")).toContainText(
      "Staged: endorsement from Maret Kuusk, which applies to Rural Alliance's one bloc.",
    );
    const pending = page.waitForResponse((r) => r.url().includes("/api/game/preview") && r.request().method() === "POST");
    await page.getByTestId("parliament-draft").getByRole("button", { name: "Preview" }).click();
    const preview = await (await pending).json();
    const sent = (await (await pending).request().postDataJSON()) as { decisions: { kind: string; character_id?: string }[] };
    expect(sent.decisions.some((d) => d.kind === "legislative_bargain" && d.character_id)).toBe(true);
    await expect(page.getByTestId("draft-status")).toHaveText("Preview is current for this draft");
    expect(preview.chambers.map((c: { chamber: string }) => c.chamber)).toEqual(["lower", "upper"]);
    const tallies = await shownTallies(page);
    for (const chamber of preview.chambers as { chamber: string; supporting_seats: number }[]) {
      const shown = tallies.find((t) => t.chamber === chamber.chamber)!;
      expect(shown.mode).toBe("current");
      expect(shown.rowSum).toBe(chamber.supporting_seats);
    }
    const resolved = (await resolveFromDecisions(page, how)) as ResultBody;
    // Gate 4A3 M-4 (Revision 2a): the proposal card and the reactions.
    await checkResultCard(page, resolved);
    const bargain = resolved.turnResult.drivers.find((d) => d.reason_id === "legislative_bargain_accepted")!;
    const leader = page.locator('[data-testid="result-person"][data-reason-id="legislative_bargain_accepted"]');
    await expect(leader).toContainText("Maret Kuusk");
    await expect(leader).toContainText("backed the budget, for 105 political capital.");
    await expect(leader.locator("[data-portrait-ref]")).toHaveAttribute("data-portrait-ref", String(bargain.params["character_portrait_ref"]));
    const blocRows = page.getByTestId("result-bloc-move");
    expect(await blocRows.count()).toBeGreaterThan(0);
    for (const move of await blocRows.allInnerTexts()) expect(move).toMatch(/^(▲ closer \+|▼ cooler -|• no change)/);
    const live = await resultReading(page);
    // History, after a LATER turn: the bargain turn reads exactly as it did live.
    await resolveEmptyTurn(page, how);
    await openHistoryTurn(page, resolved.turnResult.turn, how);
    expect(await resultReading(page), "History equals live, after a later turn").toEqual(live);
    const after = await (await apiGet(page, `${base}/api/game/decision-options`)).json();
    const last = after.last_recorded_vote as {
      turn: number;
      vote: { chambers: { chamber: string; supporting_seats: number; required_seats: number; passed: boolean }[] };
    };
    expect(last.vote.chambers.map((c) => c.chamber)).toEqual(["lower", "upper"]);
    await openParliament(page, how);
    await expect(page.getByRole("heading", { name: `Last recorded vote · turn ${last.turn}` })).toBeVisible();
    const lines = page.getByTestId("recorded-chamber");
    await expect(lines).toHaveCount(2);
    for (const [i, c] of last.vote.chambers.entries()) {
      await expect(lines.nth(i)).toContainText(`${c.supporting_seats} supporting; ${c.required_seats} required`);
    }
    results.push({ block: "m3-journey-a", width: viewport.width, recorded: last });
    await page.context().close();
  });

  test(`@m3 journey B, amendment influence (Valdrun) -- ${viewport.width}px`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newPage(browser, viewport.width, viewport.height);
    await ensureServer(page);
    await startScenario(page, "Start Kingdom of Valdrun");
    await visitScreen(page, "Constitution", how);
    const draftReform = page.getByRole("button", { name: "Draft the qualifying reform" });
    if (how === "tap") await draftReform.tap();
    else await draftReform.click();
    await expect(navEntry(page, "Decisions")).toHaveAttribute("aria-current", "page");
    await openParliament(page, how);
    const panelLocator = await openBlocPanel(page, "lower", "opposition_party/main", how);
    await expect(panelLocator.getByTestId("leader-refuses")).toHaveText("Will not deal at any price.");
    await expect(panelLocator.getByTestId("bloc-leader")).not.toContainText("Asking price");
    const influence = panelLocator.getByTestId("panel-influence");
    await expect(influence).toBeEnabled();
    await influence.fill("300");
    await expect(panelLocator.getByTestId("bloc-staged")).toContainText(
      "Influence on this vote: 300 capital (on your constitutional amendment).",
    );
    const pending = page.waitForResponse((r) => r.url().includes("/api/game/preview") && r.request().method() === "POST");
    await page.getByTestId("parliament-draft").getByRole("button", { name: "Preview" }).click();
    const preview = await (await pending).json();
    expect(preview.affordable, "the drafted reform with 300 influence is affordable").toBe(true);
    await expect(page.getByTestId("draft-status")).toHaveText("Preview is current for this draft");
    const resolved = (await resolveFromDecisions(page, how)) as ResultBody;
    // Gate 4A3 M-4 (Revision 2a): the amendment's card -- totals and the note, nothing invented.
    expect(resolved.turnResult.recorded_vote?.proposal_kind).toBe("constitutional_amendment");
    await checkResultCard(page, resolved);
    const live = await resultReading(page);
    await openHistoryTurn(page, resolved.turnResult.turn, how);
    expect(await resultReading(page), "History equals live").toEqual(live);
    const after = await (await apiGet(page, `${base}/api/game/decision-options`)).json();
    const last = after.last_recorded_vote as { turn: number; vote: { proposal_kind: string; blocs_recorded: boolean } };
    expect(last.vote.proposal_kind).toBe("constitutional_amendment");
    expect(last.vote.blocs_recorded).toBe(false);
    await openParliament(page, how);
    await expect(page.getByRole("heading", { name: `Last recorded vote · turn ${last.turn}` })).toBeVisible();
    await expect(page.getByTestId("amendment-blocs-note")).toHaveText("Per-bloc votes are not recorded for amendments.");
    results.push({ block: "m3-journey-b", width: viewport.width, recorded: last });
    await page.context().close();
  });
}

test("@m3 the panel by keyboard: open, stage, Escape back, swap blocs", async ({ browser }) => {
  test.setTimeout(300_000);
  const page = await newPage(browser, 1440, 900);
  await ensureServer(page);
  await startScenario(page, "Start Republic of Arken");
  await visitScreen(page, "Decisions");
  await selectPolicyCard(page, "Lower the personal income tax");
  await openParliament(page);
  const row = blocButton(page, "lower", "rural_alliance/farmers");
  await row.focus();
  await page.keyboard.press("Enter");
  await expect(row).toHaveAttribute("aria-expanded", "true");
  await expect
    .poll(() => page.evaluate(() => document.activeElement?.closest('[data-testid="bloc-panel"]') !== null && document.activeElement?.tagName))
    .toBe("H3");
  await page.getByTestId("bloc-panel").getByRole("button", { name: "Stage this bargain · 105" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("bargain-staged-here")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("bloc-panel")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("data-bloc-open"))).toBe("rural_alliance/farmers");

  await page.keyboard.press("Enter");
  await expect(page.getByTestId("bloc-panel")).toBeVisible();
  const other = blocButton(page, "upper", "national_front/conservatives");
  await other.focus();
  await page.keyboard.press("Enter");
  await expect
    .poll(() => page.evaluate(() => document.activeElement?.closest('[data-testid="bloc-panel"]')?.getAttribute("data-bloc")))
    .toBe("conservatives");
  results.push({ block: "m3-keyboard", focus: "heading on open, row on Escape, new heading on swap" });
  await page.context().close();
});

for (const viewport of [WIDTHS[0], WIDTHS[4]]) {
  const how = viewport.width < 1024 ? "tap" : "click";
  test(`@m3 replacing a staged bargain (ALTERED RESPONSE: a second willing leader) -- ${viewport.width}px`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newPage(browser, viewport.width, viewport.height);
    await ensureServer(page);
    // LABELLED ALTERED RESPONSE. No shipped campaign has two willing leaders at turn 0, so the
    // decision-options response is changed IN THE BROWSER ONLY to make Gustav Reiner willing at 137.
    // This exercises only the panel's replace / announce / keep behaviour: the state is never
    // previewed or resolved, and the server would refuse it.
    await page.route("**/api/game/decision-options", async (route) => {
      const response = await route.fetch();
      const body = (await response.json()) as { legislative_bargain_counterparties: Record<string, unknown>[] };
      body.legislative_bargain_counterparties = body.legislative_bargain_counterparties.map((c) =>
        c.display_name === "Gustav Reiner" ? { ...c, will_deal: true, asking_price: 137, refusal_reason: null } : c,
      );
      await route.fulfill({ response, json: body });
    });
    await startScenario(page, "Start Republic of Arken");
    await visitScreen(page, "Decisions", how);
    await selectPolicyCard(page, "Lower the personal income tax", how);
    await openParliament(page, how);
    let panelLocator = await openBlocPanel(page, "lower", "rural_alliance/farmers", how);
    const stage = panelLocator.getByRole("button", { name: "Stage this bargain · 105" });
    if (how === "tap") await stage.tap();
    else {
      await stage.focus();
      await page.keyboard.press("Enter");
    }
    panelLocator = await openBlocPanel(page, "lower", "national_front/conservatives", how);
    await expect(panelLocator.getByTestId("bargain-replace")).toContainText(
      "You already have a bargain staged: Maret Kuusk's endorsement, for 105.",
    );
    const keep = panelLocator.getByRole("button", { name: "Keep Maret Kuusk's bargain" });
    if (how === "tap") await keep.tap();
    else await keep.click();
    await expect(page.getByTestId("parliament-announcement")).toHaveText("Kept your staged bargain with Maret Kuusk.");
    const replace = panelLocator.getByRole("button", { name: "Replace bargain with Gustav Reiner · 137" });
    if (how === "tap") await replace.tap();
    else {
      await replace.focus();
      await page.keyboard.press("Enter");
    }
    await expect(page.getByTestId("parliament-announcement")).toHaveText(
      "Replaced your staged bargain with Maret Kuusk by Gustav Reiner.",
    );
    await expect(panelLocator.getByTestId("bargain-staged-here")).toContainText("Staged: endorsement from Gustav Reiner");
    await page.unroute("**/api/game/decision-options");
    results.push({ block: "m3-replacement-altered-response", width: viewport.width });
    await page.context().close();
  });
}

test("@m3 parity: the server refuses a bargain on the decree route, and the panel says why", async ({ browser }) => {
  test.setTimeout(300_000);
  const page = await newPage(browser, 1440, 900);
  await ensureServer(page);
  await startScenario(page, "Start Kingdom of Valdrun");
  await visitScreen(page, "Decisions");
  await selectPolicyCard(page, "Raise the personal income tax");
  await page.getByRole("radiogroup", { name: "Route" }).getByRole("radio", { name: /^Decree/ }).click();
  // The exact set the interface sends for this decree draft...
  const pending = page.waitForRequest((r) => r.url().includes("/api/game/preview") && r.method() === "POST");
  await page.getByRole("button", { name: "Preview", exact: true }).click();
  const sent = (await pending).postDataJSON() as { revision: string; campaign_id: string; decisions: unknown[] };
  // ...plus a bargain, which the interface never sends on this route.
  const refused = await apiPost(page, `${base}/api/game/preview`, {
    ...sent,
    decisions: [...sent.decisions, { kind: "legislative_bargain", character_id: "leader_opposition_party", proposal_kind: "budget" }],
  });
  expect(refused.status()).toBe(422);
  // The response carries the rule's MESSAGE, not its code name: this is the message the preflight
  // attaches to `legislative_bargain_requires_legislative_route` (`decision_preflight.py`).
  const problem = (await refused.json()) as { type: string; detail: string };
  expect(problem.type).toBe("decision_rejected");
  expect(problem.detail).toBe(
    "A bargain buys support in a chamber vote, and this proposal is being decreed rather than put to the chamber.",
  );
  await openParliament(page);
  const panelLocator = await openBlocPanel(page, "lower", "opposition_party/main");
  await expect(panelLocator.getByTestId("influence-blocked-reason")).toContainText("being decreed");
  results.push({ block: "m3-parity", status: refused.status() });
  await page.context().close();
});

// ---- @m4: the result restructure ---------------------------------------------------------------

for (const viewport of WIDTHS) {
  test(`@m4 the turn result -- ${viewport.width}px`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newPage(browser, viewport.width, viewport.height);
    await ensureServer(page);
    const how = viewport.width < 1024 ? "tap" : "click";
    await startScenario(page, "Start Republic of Arken");
    await visitScreen(page, "Decisions", how);
    await selectPolicyCard(page, "Lower the personal income tax", how);
    await openParliament(page, how);
    // Parliament's colour for every party, before the vote.
    const parliamentColours = await seatColours(page, '[data-testid="chamber-card"] [data-seat]');
    const panelLocator = await openBlocPanel(page, "lower", "rural_alliance/farmers", how);
    const stage = panelLocator.getByRole("button", { name: "Stage this bargain · 105" });
    if (how === "tap") await stage.tap();
    else await stage.click();
    const body = (await resolveFromDecisions(page, how)) as ResultBody;
    await checkResultCard(page, body);
    expect(body.turnResult.recorded_vote?.chambers.length, "two chambers voted").toBe(2);

    // One palette per vote, equal to Parliament's.
    const resultColours = await seatColours(page, '[data-testid="proposal-card"] [data-seat][data-filled="true"]');
    expect(Object.keys(resultColours).length).toBeGreaterThan(1);
    for (const [party, fills] of Object.entries(resultColours)) {
      expect(fills, `${party}: one colour across both chambers`).toHaveLength(1);
      expect(fills, `${party}: the same colour as on Parliament`).toEqual(parliamentColours[party]);
    }

    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
      "no page overflow on the result",
    ).toBe(true);
    expect(await clippedNodes(page), "no clipped node on the result").toEqual([]);
    const small = await page.evaluate(() =>
      [...document.querySelectorAll('[data-testid="turn-result-view"] button, [data-testid="turn-result-view"] summary')]
        .map((e) => ({ name: e.textContent?.trim() ?? "", r: e.getBoundingClientRect() }))
        .filter(({ r }) => r.height < 44)
        .map(({ name, r }) => `${name} ${Math.round(r.width)}x${Math.round(r.height)}`),
    );
    expect(small, "result controls at least 44 px tall").toEqual([]);
    const axe = await new AxeBuilder({ page }).include("main").analyze();
    expect(axe.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
    await page.screenshot({
      path: path.join(REVIEW_DIR, `${OUT_NAME}-shots`, `result-${viewport.width}.png`),
      fullPage: true,
    });
    results.push({
      block: "m4",
      width: viewport.width,
      verdict: body.turnResult.recorded_vote?.outcome,
      chambers: body.turnResult.recorded_vote?.chambers.map((c) => [c.chamber, c.supporting_seats, c.required_seats]),
      colours: resultColours,
    });
    await page.context().close();
  });
}

test("@m4 Valdrun: a decree turn and a turn with no proposal", async ({ browser }) => {
  test.setTimeout(300_000);
  const page = await newPage(browser, 1440, 900);
  await ensureServer(page);
  await startScenario(page, "Start Kingdom of Valdrun");
  await visitScreen(page, "Decisions");
  await selectPolicyCard(page, "Raise the personal income tax");
  await page.getByRole("radiogroup", { name: "Route" }).getByRole("radio", { name: /^Decree/ }).click();
  const decree = (await resolveFromDecisions(page, "click")) as ResultBody;
  expect(decree.turnResult.no_vote_reason).toBe("enacted_by_decree");
  await checkResultCard(page, decree);
  await expect(page.getByTestId("proposal-card")).toContainText("Enacted by decree — no vote was held.");
  await expect(page.getByTestId("result-bloc").first()).toBeVisible();

  const empty = await resolveEmptyTurn(page, "click") as ResultBody;
  expect(empty.turnResult.no_vote_reason).toBe("no_proposal");
  await checkResultCard(page, empty);
  await expect(page.getByTestId("result-proposal")).toHaveText("Your proposal: No proposal was put to a vote this turn.");
  results.push({ block: "m4-valdrun", decree: decree.turnResult.no_vote_reason, empty: empty.turnResult.no_vote_reason });
  await page.context().close();
});

test("@m4 keyboard: the Trace reaches a line in the card and a reaction under a bloc", async ({ browser }) => {
  test.setTimeout(300_000);
  const page = await newPage(browser, 1440, 900);
  await ensureServer(page);
  await startScenario(page, "Start Kingdom of Valdrun");
  await visitScreen(page, "Decisions");
  await selectPolicyCard(page, "Raise the personal income tax");
  await page.getByRole("radiogroup", { name: "Route" }).getByRole("radio", { name: /^Decree/ }).click();
  await resolveFromDecisions(page, "click");
  const view = page.getByTestId("turn-result-view");
  const toggle = view.getByRole("button", { name: "Show exact values" });
  await toggle.focus();
  await page.keyboard.press("Enter");
  const reached: Record<string, string> = {};
  for (const reason of ["legislative_vote_resolved", "decree_bypass_relationship_reaction"]) {
    await view.getByRole("button", { name: "Hide exact values" }).focus();
    let found = false;
    for (let i = 0; i < 80 && !found; i += 1) {
      await page.keyboard.press("Tab");
      found = await page.evaluate(
        (id) => document.activeElement?.tagName === "A" && document.activeElement.textContent === id,
        reason,
      );
    }
    expect(found, `Tab reaches the Trace link for ${reason}`).toBe(true);
    await page.keyboard.press("Enter");
    await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("data-reason-id"))).toBe(reason);
    const where = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement;
      return el.closest('[data-testid="proposal-card"]') ? "card" : el.closest('[data-testid="result-bloc"]') ? "bloc" : "elsewhere";
    });
    reached[reason] = where;
  }
  expect(reached).toEqual({ legislative_vote_resolved: "card", decree_bypass_relationship_reaction: "bloc" });
  results.push({ block: "m4-keyboard", reached });
  await page.context().close();
});

// ---- @m5: consolidation -- the acceptance journeys from the map, the state matrix, input, records ----

/** The three sizes the approved M-V mockups were drawn at. Phones are touch-only: every step taps. */
const M5_SIZES = [
  { width: 1440, height: 900, label: "desktop-1440x900", touch: false },
  { width: 390, height: 844, label: "mobile-390x844", touch: true },
  { width: 320, height: 800, label: "narrow-320x800", touch: true },
] as const;

/** A page with the calibrated colour probe installed (it must precede the first navigation). */
async function newProbedPage(browser: Browser, width: number, height: number): Promise<Page> {
  const page = await newPage(browser, width, height);
  await installColourProbe(page);
  return page;
}

async function press(locator: ReturnType<Page["locator"]>, touch: boolean) {
  if (touch) await locator.tap();
  else await locator.click();
}

/** The page's own background is the token, and every seat diagram on screen has a real box. */
async function paintedFacts(page: Page) {
  return page.evaluate(() => {
    const token = getComputedStyle(document.documentElement).getPropertyValue("--color-navy-950").trim();
    const probe = document.createElement("div");
    probe.style.backgroundColor = token;
    document.body.appendChild(probe);
    const tokenRgb = getComputedStyle(probe).backgroundColor;
    probe.remove();
    return {
      body: getComputedStyle(document.body).backgroundColor,
      tokenRgb,
      emptyDiagrams: [...document.querySelectorAll('[data-testid="hemicycle"]')]
        .map((svg) => svg.getBoundingClientRect())
        .filter((r) => r.width === 0 || r.height === 0).length,
      diagrams: document.querySelectorAll('[data-testid="hemicycle"]').length,
    };
  });
}

async function expectPainted(page: Page, label: string) {
  const facts = await paintedFacts(page);
  expect(facts.body, `${label}: the body's background is --color-navy-950`).toBe(facts.tokenRgb);
  expect(facts.emptyDiagrams, `${label}: every seat diagram has a box`).toBe(0);
  return facts;
}

/** From the Dashboard, open a place by its map pin (keyboard: Tab to it, then `key`) or, on a touch
 * screen, by tapping its Places button. */
async function placeFromDashboard(page: Page, place: (typeof PLACES)[number], touch: boolean, key: "Enter" | "Space") {
  await visitScreen(page, "Dashboard", touch ? "tap" : "click");
  const name = `${place.name}: opens ${place.opens}`;
  if (touch) {
    await page.getByTestId("places-list").getByRole("button", { name, exact: true }).tap();
  } else {
    await page.locator("[data-map-pin]").first().focus();
    let reached = false;
    for (let i = 0; i < 20 && !reached; i += 1) {
      reached = await page.evaluate((n) => document.activeElement?.getAttribute("aria-label") === n, name);
      if (!reached) await page.keyboard.press("Tab");
    }
    expect(reached, `Tab reaches ${name}`).toBe(true);
    await page.keyboard.press(key);
  }
  await expect(navEntry(page, place.opens)).toHaveAttribute("aria-current", "page");
  await expect
    .poll(() => page.evaluate(() => document.activeElement?.closest("main") !== null && document.activeElement?.tagName === "H2"))
    .toBe(true);
}

const PLACE = (name: string) => PLACES.find((p) => p.name === name)!;

/** Resolve from Decisions with every step touched on a phone. */
async function resolveTurn(page: Page, touch: boolean) {
  await visitScreen(page, "Decisions", touch ? "tap" : "click");
  await press(page.getByRole("button", { name: "Resolve turn" }), touch);
  const pending = page.waitForResponse((r) => r.url().includes("/api/game/resolve") && r.request().method() === "POST", {
    timeout: 120_000,
  });
  await press(page.getByRole("button", { name: "Confirm and resolve" }), touch);
  const response = await pending;
  expect(response.status()).toBe(200);
  const body = (await response.json()) as ResultBody;
  await expect(page.getByTestId("turn-result-view")).toContainText(body.turnResult.outcome_headline);
  return body;
}

/** Preview from Parliament; returns the response and the request it answered. */
async function previewFromParliament(page: Page, touch: boolean) {
  const pending = page.waitForResponse((r) => r.url().includes("/api/game/preview") && r.request().method() === "POST");
  await press(page.getByTestId("parliament-draft").getByRole("button", { name: "Preview" }), touch);
  const response = await pending;
  return { body: await response.json(), request: response.request().postDataJSON() as Record<string, unknown> };
}

async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(REVIEW_DIR, `${OUT_NAME}-shots`, name), fullPage: true });
}

for (const size of M5_SIZES) {
  const how = size.touch ? "tap" : "click";

  test(`@m5 journey A from the map: budget bargaining (Arken) -- ${size.label}`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newProbedPage(browser, size.width, size.height);
    await ensureServer(page);
    await startScenario(page, "Start Republic of Arken");

    // 1. The Dashboard: the objective, the map, contrast decided.
    await visitScreen(page, "Dashboard", how);
    await expect(page.getByTestId("objective-card").getByTestId("objective-headline")).toBeVisible();
    await expectPainted(page, "Dashboard");
    const mapContrast = await decidedContrast(page, 'section[aria-label="The country"]', "the map");
    await shot(page, `m5-a-dashboard-${size.width}.png`);

    // 2. The Treasury (Decisions) from the map: draft the budget.
    await placeFromDashboard(page, PLACE("Treasury"), size.touch, "Enter");
    await selectPolicyCard(page, "Lower the personal income tax", how);

    // 3. Parliament from the map (desktop: Tab to the pin, then SPACE).
    await placeFromDashboard(page, PLACE("Parliament"), size.touch, "Space");
    const panelLocator = await openBlocPanel(page, "lower", "rural_alliance/farmers", how);
    await press(panelLocator.getByRole("button", { name: "Stage this bargain · 105" }), size.touch);
    await expect(panelLocator.getByTestId("bargain-staged-here")).toContainText("Maret Kuusk");

    // 4. Preview from Parliament: supporting seats in both chambers, rows that sum.
    const preview = await previewFromParliament(page, size.touch);
    expect((preview.request.decisions as { kind: string }[]).map((d) => d.kind)).toContain("legislative_bargain");
    await expect(page.getByTestId("draft-status")).toHaveText("Preview is current for this draft");
    const tallies = await shownTallies(page);
    for (const chamber of preview.body.chambers as { chamber: string; supporting_seats: number }[]) {
      const shown = tallies.find((t) => t.chamber === chamber.chamber)!;
      expect(shown.mode).toBe("current");
      expect(shown.rowSum).toBe(chamber.supporting_seats);
    }
    await expectPainted(page, "Parliament");
    const parliamentContrast = await decidedContrast(page, "main", "Parliament, panel open, previewed");
    await shot(page, `m5-a-parliament-${size.width}.png`);

    // 5. The draft survives Dashboard -> Decisions -> Parliament.
    await visitScreen(page, "Dashboard", how);
    await visitScreen(page, "Decisions", how);
    await expect(page.getByRole("group", { name: "Lower the personal income tax" }).getByRole("button", { name: "Selected" })).toBeVisible();
    await expect(page.getByTestId("staged-actions")).toContainText("Maret Kuusk");
    await expect(page.getByTestId("staged-count")).toHaveText("· 2 staged");
    await openParliament(page, how);
    const again = await openBlocPanel(page, "lower", "rural_alliance/farmers", how);
    await expect(again.getByTestId("bargain-staged-here")).toContainText("Maret Kuusk");

    // 6. Resolve (every step touched on phones), then the card, the people, History.
    const body = await resolveTurn(page, size.touch);
    await checkResultCard(page, body);
    const leader = page.locator('[data-testid="result-person"][data-reason-id="legislative_bargain_accepted"]');
    await expect(leader).toContainText("backed the budget, for 105 political capital.");
    await expect(leader.locator("[data-portrait-ref]")).toHaveCount(1);
    for (const move of await page.getByTestId("result-bloc-move").allInnerTexts()) {
      expect(move).toMatch(/^(▲ closer \+|▼ cooler -|• no change)/);
    }
    await expectPainted(page, "Result");
    const resultContrast = await decidedContrast(page, "main", "the result");
    await shot(page, `m5-a-result-${size.width}.png`);
    const live = await resultReading(page);
    await openHistoryTurn(page, body.turnResult.turn, how);
    expect(await resultReading(page), "History equals live").toEqual(live);
    results.push({
      block: "m5-journey-a",
      size: size.label,
      recorded: body.turnResult.recorded_vote?.chambers.map((c) => [c.chamber, c.supporting_seats]),
      svgTextMeasured: {
        map: mapContrast.measuredSvgText,
        parliament: parliamentContrast.measuredSvgText,
        result: resultContrast.measuredSvgText,
      },
    });
    await page.context().close();
  });

  test(`@m5 journey B from the map: amendment influence (Valdrun) -- ${size.label}`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newProbedPage(browser, size.width, size.height);
    await ensureServer(page);
    await startScenario(page, "Start Kingdom of Valdrun");
    await visitScreen(page, "Dashboard", how);
    await expect(page.getByTestId("objective-card").getByTestId("objective-headline")).toBeVisible();

    // The Constitution hall from the map, then its own link.
    await placeFromDashboard(page, PLACE("Constitution hall"), size.touch, "Enter");
    await press(page.getByRole("button", { name: "Draft the qualifying reform" }), size.touch);
    await expect(navEntry(page, "Decisions")).toHaveAttribute("aria-current", "page");

    await placeFromDashboard(page, PLACE("Parliament"), size.touch, "Enter");
    const panelLocator = await openBlocPanel(page, "lower", "opposition_party/main", how);
    await expect(panelLocator.getByTestId("leader-refuses")).toHaveText("Will not deal at any price.");
    const influence = panelLocator.getByTestId("panel-influence");
    if (size.touch) await influence.tap();
    await influence.fill("300");
    await expect(panelLocator.getByTestId("bloc-staged")).toContainText("Influence on this vote: 300 capital");

    const preview = await previewFromParliament(page, size.touch);
    const tallies = await shownTallies(page);
    for (const chamber of preview.body.chambers as { chamber: string; supporting_seats: number }[]) {
      const shown = tallies.find((t) => t.chamber === chamber.chamber)!;
      expect(shown.mode, "supporting seats are shown after Preview").toBe("current");
      expect(shown.supporting, "the supporting count is on the card").not.toBeNull();
      expect(shown.rowSum).toBe(chamber.supporting_seats);
    }
    await expectPainted(page, "Parliament");

    const body = await resolveTurn(page, size.touch);
    expect(body.turnResult.recorded_vote?.proposal_kind).toBe("constitutional_amendment");
    await checkResultCard(page, body);
    const live = await resultReading(page);
    await openHistoryTurn(page, body.turnResult.turn, how);
    expect(await resultReading(page), "History equals live").toEqual(live);
    results.push({ block: "m5-journey-b", size: size.label, verdict: body.turnResult.recorded_vote?.outcome });
    await page.context().close();
  });
}

test("@m5 F1: the Dashboard's first desktop screen, introduction closed by default (1440x900)", async ({ browser }) => {
  test.setTimeout(300_000);
  const page = await newPage(browser, 1440, 900);
  await ensureServer(page);
  await startValdrun(page);
  await openDashboard(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(page.getByRole("complementary", { name: "How to govern" }), "the note starts closed").toHaveCount(0);
  await expect(page.getByRole("button", { name: "How to govern" })).toHaveAttribute("aria-expanded", "false");
  const fold = await page.evaluate(() => {
    const frame = document.querySelector('[data-testid="country-map"]')!.getBoundingClientRect();
    const pins = [...document.querySelectorAll("[data-map-pin]")].map((pin) => {
      const r = pin.getBoundingClientRect();
      return { name: pin.getAttribute("aria-label") ?? "", bottom: Math.round(r.bottom) };
    });
    return {
      frameTop: Math.round(frame.top),
      frameBottom: Math.round(frame.bottom),
      pinsInFirstScreen: pins.filter((p) => p.bottom <= window.innerHeight).map((p) => p.name),
      pinBottoms: pins.map((p) => p.bottom),
    };
  });
  // Measured with the note closed by default (the M-5 record gives the before and after figures):
  // the map frame starts at 511 px, and the capital's top row -- Parliament, Palace, Constitution
  // hall -- is inside the first 900 px. The rest of the capital and the Places list still lie below.
  expect(fold.frameTop, "the map starts within the top 520 px").toBeLessThanOrEqual(520);
  for (const name of ["Parliament: opens Legislature", "Palace: opens Government", "Constitution hall: opens Constitution"]) {
    expect(fold.pinsInFirstScreen, `${name} is in the first screen`).toContain(name);
  }
  await page.screenshot({ path: path.join(REVIEW_DIR, `${OUT_NAME}-shots`, "m5-f1-dashboard-1440x900.png") });
  results.push({ block: "m5-f1", fold });
  await page.context().close();
});

test("@m5 input: every pin and place is reached by Tab and opened by Enter and by Space", async ({ browser }) => {
  test.setTimeout(300_000);
  const page = await newPage(browser, 1440, 900);
  await ensureServer(page);
  await startValdrun(page);
  await openDashboard(page);
  // Tab order from the map's first control: every pin and every Places button is a Tab stop.
  await page.locator("[data-map-pin]").first().focus();
  const stops: string[] = [];
  for (let i = 0; i < 30; i += 1) {
    stops.push((await page.evaluate(() => document.activeElement?.getAttribute("aria-label"))) ?? "");
    await page.keyboard.press("Tab");
  }
  for (const place of PLACES) {
    const name = `${place.name}: opens ${place.opens}`;
    expect(stops.filter((s) => s === name).length, `${name}: a pin and a Places button, both Tab stops`).toBe(2);
  }
  const landed: Record<string, string> = {};
  for (const place of PLACES) {
    for (const key of ["Enter", "Space"] as const) {
      await placeFromDashboard(page, place, false, key);
      landed[`${place.name}:${key}`] = await page.evaluate(() => document.activeElement?.textContent?.trim() ?? "");
    }
    expect(landed[`${place.name}:Space`], `${place.name}: Space lands where Enter does`).toBe(landed[`${place.name}:Enter`]);
  }
  results.push({ block: "m5-input-keyboard", landed });
  await page.context().close();
});

test("@m5 input: every Places button opens its place by tap (390)", async ({ browser }) => {
  test.setTimeout(300_000);
  const page = await newPage(browser, 390, 844);
  await ensureServer(page);
  await startValdrun(page);
  const landed: Record<string, string> = {};
  for (const place of PLACES) landed[place.name] = await openPlace(page, "list", place, "tap");
  results.push({ block: "m5-input-touch", landed });
  await page.context().close();
});

for (const size of [M5_SIZES[0], M5_SIZES[1]]) {
  const how = size.touch ? "tap" : "click";

  test(`@m5 states: an unaffordable draft on Parliament -- ${size.label}`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newProbedPage(browser, size.width, size.height);
    await ensureServer(page);
    await startScenario(page, "Start Kingdom of Valdrun");
    await visitScreen(page, "Constitution", how);
    await press(page.getByRole("button", { name: "Draft the qualifying reform" }), size.touch);
    await openParliament(page, how);
    const panelLocator = await openBlocPanel(page, "lower", "opposition_party/main", how);
    await panelLocator.getByTestId("panel-influence").fill("400");
    await panelLocator.getByTestId("panel-investment").fill("200");
    const preview = await previewFromParliament(page, size.touch);
    expect(preview.body.affordable, "the backend's previewUnaffordable case").toBe(false);
    // The tallies still show; the draft says resolving would be refused; nothing claims enactment.
    expect((await shownTallies(page)).every((t) => t.mode === "current")).toBe(true);
    await expect(page.getByTestId("draft-unaffordable")).toHaveText(
      "This draft is not affordable, so resolving it would be refused.",
    );
    await expect(page.getByTestId("parliament-draft")).not.toContainText(/enacted|will pass/i);
    // The server agrees: the same set is refused, and the turn does not move.
    const before = (await (await apiGet(page, `${base}/api/game/state`)).json()) as { turn: number };
    const refused = await apiPost(page, `${base}/api/game/resolve`, preview.request);
    expect(refused.status()).toBe(422);
    const after = (await (await apiGet(page, `${base}/api/game/state`)).json()) as { turn: number };
    expect(after.turn).toBe(before.turn);
    await shot(page, `m5-unaffordable-${size.width}.png`);
    results.push({ block: "m5-unaffordable", size: size.label, refused: refused.status(), turn: after.turn });
    await page.context().close();
  });

  test(`@m5 states: a failed vote's result card -- ${size.label}`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newProbedPage(browser, size.width, size.height);
    await ensureServer(page);
    await startScenario(page, "Start Kingdom of Valdrun");
    await visitScreen(page, "Decisions", how);
    await selectPolicyCard(page, "Raise the personal income tax", how);
    const body = await resolveTurn(page, size.touch);
    expect(body.turnResult.recorded_vote?.outcome).toBe("failed_legislative");
    await checkResultCard(page, body);
    await expect(page.getByTestId("result-card-drivers")).toContainText(/chamber blocked the budget: [\d,]+ supporting votes/);
    const live = await resultReading(page);
    await openHistoryTurn(page, body.turnResult.turn, how);
    expect(await resultReading(page)).toEqual(live);
    results.push({ block: "m5-failed", size: size.label });
    await page.context().close();
  });
}

/** The approved M-V views, re-shot from the app at the mockups' own sizes (viewport, not full page),
 * each scrolled to the part the mockup shows. */
for (const size of M5_SIZES) {
  const how = size.touch ? "tap" : "click";
  test(`@m5 visual record -- ${size.label}`, async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await newProbedPage(browser, size.width, size.height);
    await ensureServer(page);
    const view = async (name: string, focus?: string) => {
      if (focus) await page.locator(focus).first().scrollIntoViewIfNeeded();
      else await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: path.join(REVIEW_DIR, `${OUT_NAME}-shots`, `visual-${name}__${size.label}.png`) });
    };

    // Valdrun.
    await startScenario(page, "Start Kingdom of Valdrun");
    await visitScreen(page, "Dashboard", how);
    await view("dashboard");
    await visitScreen(page, "Constitution", how);
    await press(page.getByRole("button", { name: "Draft the qualifying reform" }), size.touch);
    await openParliament(page, how);
    await view("parliament-valdrun-draft", '[data-testid="chamber-card"]');
    let panelLocator = await openBlocPanel(page, "lower", "opposition_party/main", how);
    await view("bloc-refuses", '[data-testid="bloc-panel"]');
    await press(panelLocator.getByRole("button", { name: /^Close / }), size.touch);
    await previewFromParliament(page, size.touch);
    await view("parliament-valdrun-preview", '[data-testid="chamber-card"]');

    // Arken.
    await startScenario(page, "Start Republic of Arken");
    await openParliament(page, how);
    panelLocator = await openBlocPanel(page, "lower", "rural_alliance/farmers", how);
    await view("bloc-no-proposal", '[data-testid="bloc-panel"]');
    await visitScreen(page, "Decisions", how);
    await selectPolicyCard(page, "Lower the personal income tax", how);
    await openParliament(page, how);
    panelLocator = await openBlocPanel(page, "lower", "rural_alliance/farmers", how);
    await view("bloc-offer", '[data-testid="bloc-panel"]');
    await press(panelLocator.getByRole("button", { name: "Stage this bargain · 105" }), size.touch);
    await view("bloc-staged", '[data-testid="bloc-panel"]');
    await press(panelLocator.getByRole("button", { name: /^Close / }), size.touch);
    await previewFromParliament(page, size.touch);
    await view("parliament-tiny-preview", '[data-testid="chamber-card"]');
    await resolveTurn(page, size.touch);
    await view("result");
    await openParliament(page, how);
    await view("parliament-tiny-recorded", '[data-testid="recorded-chamber"]');
    await page.context().close();

    // The replacement, on M-3's LABELLED ALTERED RESPONSE (a second willing leader; never resolved).
    const altered = await newPage(browser, size.width, size.height);
    await altered.route("**/api/game/decision-options", async (route) => {
      const response = await route.fetch();
      const body = (await response.json()) as { legislative_bargain_counterparties: Record<string, unknown>[] };
      body.legislative_bargain_counterparties = body.legislative_bargain_counterparties.map((c) =>
        c.display_name === "Gustav Reiner" ? { ...c, will_deal: true, asking_price: 137, refusal_reason: null } : c,
      );
      await route.fulfill({ response, json: body });
    });
    await startScenario(altered, "Start Republic of Arken");
    await visitScreen(altered, "Decisions", how);
    await selectPolicyCard(altered, "Lower the personal income tax", how);
    await openParliament(altered, how);
    const first = await openBlocPanel(altered, "lower", "rural_alliance/farmers", how);
    await press(first.getByRole("button", { name: "Stage this bargain · 105" }), size.touch);
    await openBlocPanel(altered, "lower", "national_front/conservatives", how);
    await altered.locator('[data-testid="bloc-panel"]').first().scrollIntoViewIfNeeded();
    await altered.screenshot({ path: path.join(REVIEW_DIR, `${OUT_NAME}-shots`, `visual-bloc-replace__${size.label}.png`) });
    await altered.context().close();
    results.push({ block: "m5-visual-record", size: size.label, views: 11 });
  });
}
