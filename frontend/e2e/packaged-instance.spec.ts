/**
 * Gate 4A3 Commit 6 — ONE TURN, THROUGH THE INTERFACE, AGAINST THE INSTALLED ARCHIVE.
 *
 * `scripts/verify_release.py` unpacks the release archive into an empty directory, installs it into a
 * fresh virtualenv, starts the installed `mandate-gui`, and runs this project with
 * `MANDATE_PACKAGED_BASE_URL` pointing at it. So this spec measures WHAT SHIPS, never the development
 * tree. It is not meant to be run by hand, and without the variable it skips rather than silently
 * testing the wrong server.
 *
 * It asserts three things:
 *   1. a turn can be played: start `decree_state`, resolve through Resolve turn -> Confirm and
 *      resolve, and read the Turn result;
 *   2. every request the page makes is same-origin (Gate 4A3 plan section 9.4 item 3, for the shipped
 *      artifact): no font CDN, no analytics, no third-party asset;
 *   3. the "interaction -> visible feedback" budget (section 5, STOP at 200 ms), measured IN the page
 *      with `performance.now()` and a MutationObserver armed before the click, for a navigation, a
 *      Preview and a Confirm and resolve. The worst of the three is compared with the STOP.
 */

import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const BASE = process.env.MANDATE_PACKAGED_BASE_URL;
const OUT_NAME = process.env.MANDATE_PACKAGED_OUT ?? "gate-4a3-commit6-packaged";
const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
const FEEDBACK_STOP_MS = 200;
const FEEDBACK_TARGET_MS = 100;

/** Arm a MutationObserver, click, and resolve with the milliseconds until the page first changes in a
 * way the predicate accepts. Timed inside the page, so no round trip to the test runner is counted. */
async function timeFeedback(page: Page, selector: string, predicate: string): Promise<number> {
  return page.evaluate(
    ({ selector, predicate }) =>
      new Promise<number>((resolve, reject) => {
        const target = document.querySelector(selector) as HTMLElement | null;
        if (!target) {
          reject(new Error(`no element for ${selector}`));
          return;
        }
        // eslint-disable-next-line no-new-func
        const accept = new Function("target", `return (${predicate});`) as (t: HTMLElement) => boolean;
        let started = 0;
        const observer = new MutationObserver(() => {
          if (accept(target)) {
            observer.disconnect();
            resolve(performance.now() - started);
          }
        });
        observer.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
        started = performance.now();
        target.click();
        setTimeout(() => {
          observer.disconnect();
          reject(new Error(`no visible feedback within 5 s for ${selector}`));
        }, 5_000);
      }),
    { selector, predicate },
  );
}

test("one turn against the installed archive, same-origin, within the feedback budget", async ({ page }) => {
  test.skip(!BASE, "run by scripts/verify_release.py against an installed archive");
  test.setTimeout(180_000);
  const requests: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (!url.startsWith("data:") && url !== "about:blank") requests.push(url);
  });

  const scenarios = (await page.request.get(`${BASE}/api/scenarios`).then((r) => r.json())) as {
    scenario_id: string;
    display_name: string;
  }[];
  const scenario = scenarios.find((s) => s.scenario_id === "decree_state");
  expect(scenario, "decree_state must ship").toBeDefined();

  await page.goto(`${BASE}/`);
  const start = page.getByRole("button", { name: `Start ${scenario!.display_name}` });
  await start.waitFor({ state: "visible", timeout: 30_000 });
  const started = page.waitForResponse((r) => r.url().includes("/api/game/new"), { timeout: 60_000 });
  await start.click();
  expect((await started).status()).toBe(200);

  const nav = page.getByRole("navigation", { name: "Screens" });
  await nav.getByRole("button", { name: "Decisions", exact: true }).waitFor({ state: "visible" });

  // Feedback 1: a navigation. Visible feedback is the entry becoming the current page.
  await page.evaluate(() => {
    for (const button of Array.from(document.querySelectorAll('nav[aria-label="Screens"] button'))) {
      if (button.textContent?.trim() === "Decisions") button.setAttribute("data-feedback-target", "nav");
    }
  });
  const navMs = await timeFeedback(
    page,
    '[data-feedback-target="nav"]',
    'target.getAttribute("aria-current") === "page"',
  );

  // Feedback 2: Preview. Visible feedback is the button going busy or a result appearing. Wait for the
  // screen to have rendered the control first -- tagging it is not part of what is timed.
  await page.getByRole("button", { name: "Preview", exact: true }).waitFor({ state: "visible", timeout: 30_000 });
  await page.evaluate(() => {
    for (const button of Array.from(document.querySelectorAll("main button"))) {
      if (button.textContent?.trim() === "Preview") button.setAttribute("data-feedback-target", "preview");
    }
  });
  const previewMs = await timeFeedback(
    page,
    '[data-feedback-target="preview"]',
    'target.disabled || target.textContent.includes("Previewing") || !!document.querySelector("[data-testid=consequences-panel]")',
  );
  await page.getByTestId("consequences-panel").waitFor({ state: "visible", timeout: 30_000 });

  // Feedback 3: Confirm and resolve. Visible feedback is the control going busy, or navigation away.
  await page.getByRole("button", { name: "Resolve turn" }).click();
  await page.getByRole("button", { name: "Confirm and resolve" }).waitFor({ state: "visible" });
  await page.evaluate(() => {
    for (const button of Array.from(document.querySelectorAll("main button"))) {
      if (button.textContent?.trim() === "Confirm and resolve") button.setAttribute("data-feedback-target", "confirm");
    }
  });
  const resolved = page.waitForResponse((r) => r.url().includes("/api/game/resolve"), { timeout: 120_000 });
  const confirmMs = await timeFeedback(
    page,
    '[data-feedback-target="confirm"]',
    'target.disabled || !target.isConnected || document.body.textContent.includes("Resolving")',
  );
  expect((await resolved).status(), "the turn must resolve").toBe(200);
  await expect(page.getByTestId("turn-result-view")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Why this happened" })).toBeVisible();

  const offOrigin = requests.filter((url) => !url.startsWith(`${BASE}/`));
  const feedback = { navigationMs: navMs, previewMs, confirmMs };
  const worst = Math.max(navMs, previewMs, confirmMs);

  mkdirSync(REVIEW_DIR, { recursive: true });
  writeFileSync(
    path.join(REVIEW_DIR, `${OUT_NAME}.json`),
    `${JSON.stringify(
      {
        against: "the installed release archive (see gate-4a3-commit6-release.json)",
        requests: requests.length,
        distinctPaths: [...new Set(requests.map((u) => new URL(u).pathname))].sort(),
        offOrigin,
        feedback: { ...feedback, worst, targetMs: FEEDBACK_TARGET_MS, stopMs: FEEDBACK_STOP_MS },
        method:
          "performance.now() in the page, with a MutationObserver armed on document.body before the " +
          "click; the first mutation after which the control's own feedback condition holds ends the " +
          "timing.",
      },
      null,
      2,
    )}\n`,
  );

  expect(offOrigin, "every request must be same-origin").toEqual([]);
  expect(worst, `interaction feedback ${JSON.stringify(feedback)} must stay under the STOP`).toBeLessThanOrEqual(
    FEEDBACK_STOP_MS,
  );
});
