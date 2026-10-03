/**
 * Gate 4A3 Commit 3 — GOVERNMENT'S OUTSTANDING STRESS COVERAGE, now paid.
 *
 * WHAT WAS OWED. Commit 1 claimed "0 stress findings" across four screens on the strength of one weak
 * assertion. Commit 1a corrected that per screen and recorded Government as `not-stress-applicable`
 * for a specific, honest reason: the stress fixture derives from `deficit_demo`, which opens with BOTH
 * cabinet posts VACANT, so there is no holder name on that screen for a 64-character name to stretch.
 * A seated case was explicitly left owed. This file is that case.
 *
 * WHY IT IS A SEPARATE FILE AND A SEPARATE ARTIFACT. `stress.spec.ts` and its
 * `gate-4a3-stress.json` are Commit 1a's evidence, and evidence is not edited to accommodate later
 * work: re-running that spec would rewrite the file the correction is recorded in. So this spec is
 * additive, runs its own server against its own fixture, and writes
 * `gate-4a3-stress-seated-cabinet.json` beside the original. Both remain readable, and a reader can
 * see which claim came from which run.
 *
 * WHAT MAKES THE RESULT NON-VACUOUS, which is the whole lesson of Commit 1a. A screen is only allowed
 * to report a stress result after the EXACT authored 64-character names are proven present in its DOM.
 * The names are read out of the fixture rather than retyped, both holders' names must be found, and
 * the run asserts the count of proofs equals the number of surfaces measured. "Nothing overflowed"
 * and "nothing was there to overflow" are different answers, and only the first is claimable here.
 */

import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { expect, test } from "@playwright/test";

const REVIEW_DIR = path.join(process.cwd(), "..", "docs", "reviews");
/** Gate 4A3 UX pass: the output names are parameters, defaulting to the committed ones, so a later
 * commit's re-run writes BESIDE the committed evidence (JSON and screenshots) instead of over it. */
const OUT_NAME = process.env.MANDATE_STRESS_SEATED_OUT ?? "gate-4a3-stress-seated-cabinet";
const SHOT_DIR = path.join(
  REVIEW_DIR,
  process.env.MANDATE_STRESS_SEATED_OUT === undefined ? "gate-4a3-baseline" : `${OUT_NAME}-shots`,
);
const FIXTURE = path.join(process.cwd(), "e2e", "fixtures", "stress_long_names_seated_cabinet.yaml");

/** The two posts this fixture seats, and the character each holds. Kept as data so the assertions can
 * name what they are looking for rather than hunting for "some long string". */
const SEATED = [
  { post: "chief_of_staff", characterId: "bela_ronsard" },
  { post: "foreign_minister", characterId: "clara_venn" },
] as const;

/** The stress viewports, matching the sibling spec so the two results are comparable. */
const VIEWPORTS = [
  { name: "stress-laptop-1440x900", width: 1440, height: 900 },
  { name: "stress-mobile-390x844", width: 390, height: 844 },
] as const;

/** Read an authored display name straight out of the fixture, by character id. Reading rather than
 * retyping is what makes this a check against the source of truth: a name changed in the fixture
 * changes what the assertion looks for, instead of silently disagreeing with it. */
function authoredName(characterId: string): string {
  const yaml = readFileSync(FIXTURE, "utf-8");
  const pattern = new RegExp(`^  ${characterId}:\\n(?:.*\\n)*?    display_name: "([^"]+)"`, "m");
  const match = pattern.exec(yaml);
  if (match === null) throw new Error(`no display_name for ${characterId} in the seated fixture`);
  return match[1]!;
}

function freePort(): number {
  const script =
    "const s=require('node:net').createServer();" +
    "s.listen(0,'127.0.0.1',()=>{const a=s.address();" +
    "process.stdout.write(String(typeof a==='object'&&a?a.port:0));s.close();});";
  return Number(execFileSync(process.execPath, ["-e", script], { encoding: "utf-8" }).trim());
}

let server: ChildProcess | null = null;
const findings: { id: string; screen: string; viewport: string; kind: string; detail: string }[] = [];
const coverage: string[] = [];
const proofs: string[] = [];

test.afterAll(() => {
  server?.kill("SIGINT");
});

test("Government under a SEATED cabinet with maximum-length holder names", async ({ page }) => {
  test.setTimeout(300_000);

  const names = SEATED.map((seat) => ({ ...seat, name: authoredName(seat.characterId) }));
  for (const seat of names) {
    expect(
      seat.name.length,
      `${seat.characterId}'s authored name must be exactly 64 characters to stress anything`,
    ).toBe(64);
  }

  const root = mkdtempSync(path.join(tmpdir(), "mandate-stress-seated-"));
  copyFileSync(FIXTURE, path.join(root, "stress_long_names_seated_cabinet.yaml"));

  const port = freePort();
  server = spawn(
    "uv",
    [
      "run", "mandate-gui",
      "--port", String(port),
      "--frontend-dist", path.join(process.cwd(), "dist"),
      "--scenario-root", root,
      "--save-root", path.join(root, "saves"),
    ],
    { cwd: path.join(process.cwd(), "..", "backend"), stdio: "ignore" },
  );

  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 60; i += 1) {
    const ok = await page.request.get(`${base}/api/scenarios`).then((r) => r.ok()).catch(() => false);
    if (ok) break;
    await page.waitForTimeout(500);
  }

  await page.goto(`${base}/`);
  const start = page.getByRole("button", { name: /^Start / }).first();
  await start.waitFor({ state: "visible", timeout: 30_000 });
  await start.click();
  await page.waitForResponse((r) => r.url().includes("/api/game/state") && r.status() === 200, {
    timeout: 30_000,
  });
  await page.waitForTimeout(400);

  // The seating is a claim about the SERVER, so it is checked against the server's own projection
  // before anything about the screen is measured. A fixture that failed to seat would otherwise
  // produce a "no overflow" result for a screen still showing two vacant posts.
  const options = await page.request.get(`${base}/api/game/decision-options`).then((r) => r.json());
  const posts = (options.cabinet_posts ?? []) as { post: string; holder_character_id: string | null }[];
  for (const seat of names) {
    const row = posts.find((p) => p.post === seat.post);
    expect(row, `the projection must describe the ${seat.post} post`).toBeDefined();
    expect(
      row?.holder_character_id,
      `${seat.post} must be SEATED by this fixture, or Government cannot be stressed`,
    ).toBe(seat.characterId);
  }
  coverage.push(
    `server projection confirms both posts seated: ${names.map((s) => `${s.post}=${s.characterId}`).join(", ")}`,
  );

  mkdirSync(SHOT_DIR, { recursive: true });
  let counter = 0;

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });

    const nav = page.getByRole("button", { name: "Government", exact: true }).first();
    expect(await nav.isVisible(), "the Government nav control must be reachable").toBe(true);
    expect(await nav.isDisabled(), "Government must be enabled with an active campaign").toBe(false);
    await nav.click();
    await page.waitForTimeout(350);

    // THE PROOF, before any result is recorded: both exact authored names present in `main`.
    const main = page.locator("main");
    const mainText = (await main.textContent()) ?? "";
    for (const seat of names) {
      expect(
        mainText.includes(seat.name),
        `Government at ${viewport.name} must render ${seat.characterId}'s exact authored ` +
          `64-character name before any stress result is claimed for it`,
      ).toBe(true);
    }
    const rendered = names.filter((seat) => mainText.includes(seat.name)).length;
    proofs.push(
      `Government at ${viewport.name}: ${rendered} exact authored 64-character holder name(s) rendered ` +
        `(${names.map((s) => s.name.slice(0, 18) + "...").join(", ")})`,
    );

    await page.screenshot({
      path: path.join(SHOT_DIR, `${viewport.name}__Government-seated.png`),
    });

    // Only NOW is overflow a meaningful measurement.
    const scrolls = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
    );
    if (scrolls) {
      counter += 1;
      findings.push({
        id: `G${counter}`,
        screen: "Government",
        viewport: viewport.name,
        kind: "horizontal-scroll",
        detail: "the page scrolls horizontally with maximum-length holder names",
      });
    }

    const overflowing = await page.evaluate(() => {
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
    for (const node of overflowing) {
      counter += 1;
      findings.push({
        id: `G${counter}`,
        screen: "Government",
        viewport: viewport.name,
        kind: "overflow",
        detail: `content wider than its box: ${node}`,
      });
    }

    if (!scrolls && overflowing.length === 0) {
      coverage.push(
        `Government at ${viewport.name}: no horizontal page scroll and no overflowing node, ` +
          `with both maximum-length holder names proven present`,
      );
    }
  }

  writeFileSync(
    path.join(REVIEW_DIR, `${OUT_NAME}.json`),
    JSON.stringify(
      {
        fixture: "frontend/e2e/fixtures/stress_long_names_seated_cabinet.yaml",
        seated: names.map((s) => ({ post: s.post, characterId: s.characterId, name: s.name })),
        viewports: VIEWPORTS.map((v) => v.name),
        findings,
        coverage,
        proofs,
      },
      null,
      2,
    ) + "\n",
    "utf-8",
  );

  // ANTI-VACUITY: one proof per surface measured, so a run that silently skipped a viewport cannot
  // pass as a clean result. This is the assertion Commit 1 lacked and Commit 1a added.
  expect(
    proofs.length,
    "every measured viewport must carry a rendered-name proof",
  ).toBe(VIEWPORTS.length);
});
