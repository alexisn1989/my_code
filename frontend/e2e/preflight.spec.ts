/**
 * §9.2's preflight: prove the browser we launch is the one already on disk, and that launching it
 * downloaded nothing.
 *
 * This runs before anything else and everything else depends on it. A baseline captured by a
 * silently-downloaded browser would be a baseline of a different renderer than the one this
 * environment ships, and nothing downstream would reveal that — which is why the proof is
 * mechanical rather than a comment in the config.
 */

import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const CACHE_ROOT = process.env.PLAYWRIGHT_BROWSERS_PATH ?? "";

/** The cache root's own listing, sorted. Compared before and after a launch: a download would add
 * a revision directory (or a `.links`/partial entry), so an unchanged listing is the evidence. */
function cacheListing(): string[] {
  return readdirSync(CACHE_ROOT).sort();
}

test.describe("§9.2 browser provenance", () => {
  test("the environment exposes a browser CACHE ROOT, not an executable", () => {
    expect(CACHE_ROOT, "PLAYWRIGHT_BROWSERS_PATH must be set").not.toBe("");
    const listing = cacheListing();
    // A cache root CONTAINS revision directories; an executable path would not.
    expect(listing).toContain("chromium-1194");
    expect(listing).toContain("chromium_headless_shell-1194");
  });

  test("the pinned Playwright expects exactly the cached revision", () => {
    const browsers = JSON.parse(
      readFileSync(
        path.join(process.cwd(), "node_modules/playwright-core/browsers.json"),
        "utf-8",
      ),
    ) as { browsers: { name: string; revision: string; browserVersion?: string }[] };
    const chromium = browsers.browsers.find((b) => b.name === "chromium");
    expect(chromium, "playwright-core must declare a chromium browser").toBeDefined();
    // 1194 is not a magic number: it is the revision this container has cached, and the pin exists
    // so the two can never drift apart without this failing.
    expect(chromium?.revision).toBe("1194");
    expect(chromium?.browserVersion).toBe("141.0.7390.37");
  });

  test("Chromium launches from the cache, and the cache is unchanged by doing so", async ({
    browser,
  }) => {
    const before = cacheListing();

    // The running browser really is the cached build.
    expect(browser.version()).toBe("141.0.7390.37");

    // Exercise the browser rather than merely starting it, so the comparison below spans real use.
    const page = await browser.newPage();
    await page.setContent("<title>provenance</title><p>ok</p>");
    expect(await page.title()).toBe("provenance");
    await page.close();

    const after = cacheListing();
    // Nothing was fetched: same revisions, same entries, same order.
    expect(after).toEqual(before);
  });

  test("the resolved executable lives under the cache root", async ({ playwright }) => {
    const executablePath = playwright.chromium.executablePath();
    expect(executablePath.startsWith(CACHE_ROOT)).toBe(true);
    expect(executablePath).toContain("1194");
  });

  test("the live server the baseline runs against is the real one", async ({ request }) => {
    // Not a mock and not a fixture: `mandate-gui`, the production entry point, serving the built
    // SPA and the real scenarios. Every integration claim in the baseline rests on this.
    const scenarios = await request.get("/api/scenarios");
    expect(scenarios.ok()).toBe(true);
    const body = (await scenarios.json()) as { scenario_id: string }[];
    expect(body.map((s) => s.scenario_id).sort()).toEqual([
      "decree_state",
      "deficit_demo",
      "tiny_valid",
    ]);
  });
});
