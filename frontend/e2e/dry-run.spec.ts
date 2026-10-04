/**
 * Gate 4A3 UX-4d — the INTERNAL dry run, through the interface, against the INSTALLED release.
 *
 * Not one of the five external playtesters, and not a substitute for them: this is the build's own
 * last walk-through before the playtest, recorded as internal. It drives a server started from the
 * installed archive (`.venv/bin/mandate-gui` from the README's own commands), given by
 * `MANDATE_DRYRUN_URL`; it never starts the repository's server for its own use.
 *
 * The walk: Kingdom of Valdrun; turn 1 by DECREE (preview, then resolve); four more turns by the
 * legislative route, each previewed; every result read -- headline, the consequences, the folded
 * routine steps, the Trace -- and the next turn reached through "Plan turn N". Then History re-reads
 * turn 1, and a Dashboard Details link lands on its card. Console errors are counted, not ignored.
 *
 * Output: `MANDATE_DRYRUN_OUT` names the JSON record and a screenshot directory beside it. REQUIRED,
 * and written with `wx` / refused if the directory exists: a record is never overwritten.
 *
 * Gate 4A3 UX-4e: the run ENFORCES what it records. Under the dedicated command
 * (`MANDATE_DRYRUN_REQUIRED=1`) a missing server address FAILS instead of skipping; every turn's
 * preview must agree with its resolution (`would_pass` against the vote driver's recorded outcome,
 * and a decree must be affordable and enacted); and a console error fails the run. The record is
 * written only after every assertion holds.
 */

import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
const BASE = process.env.MANDATE_DRYRUN_URL;
const OUT = process.env.MANDATE_DRYRUN_OUT;
const SAFE_NAME = /^[a-z0-9][a-z0-9.-]*$/;
const TURNS = [
  { card: "Raise the personal income tax", route: "decree" as const },
  { card: "Lower the personal income tax", route: "legislative" as const },
  { card: "Raise the personal income tax", route: "legislative" as const },
  { card: "Lower the personal income tax", route: "legislative" as const },
  { card: "Raise the personal income tax", route: "legislative" as const },
];

const REQUIRED = process.env.MANDATE_DRYRUN_REQUIRED === "1";
// Skipped only when nobody asked for a dry run (an unrelated run of every project); the dedicated
// command sets MANDATE_DRYRUN_REQUIRED, and then a missing address is a failure, not a skip.
test.skip(BASE === undefined && !REQUIRED, "the dry run needs MANDATE_DRYRUN_URL: a server started from the installed archive");

async function visit(page: Page, name: string): Promise<void> {
  const entry = page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name, exact: true });
  await entry.click();
  await expect(entry).toHaveAttribute("aria-current", "page");
}

test("internal dry run: five turns through the interface of the installed build", async ({ page }) => {
  test.setTimeout(600_000);
  if (BASE === undefined) {
    throw new Error("MANDATE_DRYRUN_URL is required: start the installed archive's server and pass its address");
  }
  if (OUT === undefined || !SAFE_NAME.test(OUT) || OUT.includes("..")) {
    throw new Error("MANDATE_DRYRUN_OUT is required and must be a safe artifact name");
  }
  const shots = path.join(REVIEW_DIR, `${OUT}-shots`);
  if (existsSync(shots) || existsSync(path.join(REVIEW_DIR, `${OUT}.json`))) {
    throw new Error(`refusing to overwrite an existing record: ${OUT}`);
  }
  mkdirSync(shots, { recursive: false });

  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  const offOrigin: string[] = [];
  page.on("request", (request) => {
    if (!request.url().startsWith(`${BASE}/`)) offOrigin.push(request.url());
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${BASE}/`);
  const scenarios = (await (await page.request.get(`${BASE}/api/scenarios`)).json()) as unknown[];
  const started = page.waitForResponse((r) => r.url().includes("/api/game/new") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Start Kingdom of Valdrun" }).click();
  expect((await started).status()).toBe(200);
  await visit(page, "Dashboard");
  await expect(page.getByTestId("win-and-loss").first()).toBeVisible();
  await page.screenshot({ path: path.join(shots, "00-dashboard.png"), fullPage: false });

  const turns: Record<string, unknown>[] = [];
  for (const [index, plan] of TURNS.entries()) {
    if (index === 0) {
      await page.getByRole("heading", { name: "Your current priority" }).locator("xpath=ancestor::section[1]")
        .getByRole("button", { name: "Build a decision" }).click();
    }
    await expect(
      page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name: "Decisions", exact: true }),
    ).toHaveAttribute("aria-current", "page");

    await page.getByRole("group", { name: plan.card }).getByRole("button", { name: "Select" }).click();
    const route = page.getByRole("radiogroup", { name: "Route" });
    await route.getByRole("radio", { name: plan.route === "decree" ? /^Decree/ : /^Legislative/ }).click();

    const previewed = page.waitForResponse((r) => r.url().includes("/api/game/preview") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Preview", exact: true }).click();
    const preview = (await (await previewed).json()) as { would_pass: boolean; route: string; affordable: boolean };
    const panel = page.getByTestId("consequences-panel");
    await expect(panel).toBeVisible();
    const previewText = (await panel.innerText()).split("\n").filter((line) => line.trim() !== "").slice(0, 8);

    await page.getByRole("button", { name: "Resolve turn" }).click();
    const confirmText = await page.getByText(/^Resolve turn \d+ with /).innerText();
    const resolved = page.waitForResponse((r) => r.url().includes("/api/game/resolve") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Confirm and resolve" }).click();
    const body = (await (await resolved).json()) as {
      turnResult: {
        turn: number;
        outcome_headline: string;
        drivers: { reason_id: string; params: Record<string, string | number> }[];
      };
    };
    expect((await resolved).status()).toBe(200);

    // The preview must have told the truth about this turn.
    const voteDriver = body.turnResult.drivers.find((d) => d.reason_id === "legislative_vote_resolved");
    expect(voteDriver, "the turn records how its budget was resolved").toBeDefined();
    const outcome = String(voteDriver!.params["outcome"]);
    const enacted = outcome === "passed_legislative" || outcome === "enacted_by_decree";
    expect(preview.would_pass, `turn ${index + 1}: preview would_pass vs resolved outcome ${outcome}`).toBe(enacted);
    if (plan.route === "decree") {
      expect(preview.affordable, "a decree the preview called affordable").toBe(true);
      expect(outcome).toBe("enacted_by_decree");
    }

    const view = page.getByTestId("turn-result-view");
    await expect(view).toHaveAttribute("data-context", "live");
    await expect(view).toContainText(body.turnResult.outcome_headline);
    const consequences = await view.getByTestId("drivers-consequential").locator(":scope > li").allInnerTexts();
    const routine = await view.getByTestId("drivers-routine").locator("li[data-reason-id]").count();
    await view.getByRole("button", { name: "Show exact values" }).click();
    const reasons = await view.getByTestId("trace-reasons").getByRole("link").count();
    await view.getByRole("button", { name: "Hide exact values" }).click();
    await page.screenshot({ path: path.join(shots, `${String(index + 1).padStart(2, "0")}-turn-result.png`) });

    turns.push({
      card: plan.card,
      route: plan.route,
      preview: { route: preview.route, would_pass: preview.would_pass, affordable: preview.affordable, text: previewText },
      confirm: confirmText,
      resultTurn: body.turnResult.turn,
      resolvedOutcome: outcome,
      previewAgreed: preview.would_pass === enacted,
      headline: body.turnResult.outcome_headline,
      consequences,
      routineSteps: routine,
      traceReasons: reasons,
    });

    await page.getByRole("button", { name: `Plan turn ${body.turnResult.turn}` }).click();
  }

  // History re-reads the first turn as it was resolved.
  await visit(page, "History");
  const first = turns[0] as { resultTurn: number; headline: string };
  await page.getByRole("button", { name: new RegExp(`^Turn ${first.resultTurn} — `) }).click();
  await expect(page.getByTestId("turn-result-view")).toHaveAttribute("data-context", "history");
  await expect(page.getByTestId("turn-result-view")).toContainText(first.headline);
  await page.screenshot({ path: path.join(shots, "06-history-turn-1.png") });

  // A Details link lands on its own card.
  await visit(page, "Dashboard");
  await page.getByRole("button", { name: "Details: Money" }).click();
  await expect(page.getByTestId("concern-summaries").getByRole("heading", { name: "Money", exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(shots, "07-economy-summary.png") });

  expect(offOrigin, "every request stays on the installed server's origin").toEqual([]);
  expect(consoleErrors, "no console error anywhere in the walk").toEqual([]);
  writeFileSync(
    path.join(REVIEW_DIR, `${OUT}.json`),
    `${JSON.stringify(
      {
        gate: process.env.MANDATE_DRYRUN_REQUIRED === "1" ? "4A3 UX-4f (enforced)" : "4A3 UX-4d",
        kind: "INTERNAL dry run -- not one of the five external playtesters",
        server: BASE,
        scenarios: scenarios.length,
        turns,
        historyFirstTurnHeadline: first.headline,
        consoleErrors,
        offOrigin,
      },
      null,
      2,
    )}\n`,
    { flag: "wx" },
  );
});
