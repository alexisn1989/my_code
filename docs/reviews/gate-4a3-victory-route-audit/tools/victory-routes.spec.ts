/**
 * Victory routes, replayed THROUGH THE INTERFACE of the installed playtest build.
 *
 * For each shipped scenario, the engine-side search (`victory_search*.py`) found a legal route from a
 * new campaign to VICTORY and recorded every turn's decision set. This spec plays that route as a
 * player would -- reform cards / Customize policy, the Route radios, influence and relationship-
 * investment inputs, the Meeting screen's bargain -- and requires, every turn, that the decisions the
 * INTERFACE sends to `/api/game/resolve` equal the recorded ones. It then requires the campaign to end
 * in VICTORY, read back from the Victory / defeat screen.
 *
 * It also records what a player could SEE along the way: the Dashboard goal card, and whether any
 * screen states the campaign's progress toward victory.
 *
 *   MANDATE_URL=http://127.0.0.1:<port> ROUTES_DIR=<dir with search JSON> OUT_DIR=<dir> \
 *     npx playwright test --config=<this dir>/victory.config.ts
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const BASE = process.env.MANDATE_URL!;
const ROUTES = process.env.ROUTES_DIR!;
const OUT = process.env.OUT_DIR!;

type Decision = Record<string, any>;
type Turn = { turn: number; submitted: Decision[] };

const AXIS: Record<string, { role: "combobox" | "spinbutton"; name: RegExp }> = {
  decree_authority: { role: "combobox", name: /^Decree authority/ },
  executive_selection: { role: "combobox", name: /^Executive selection/ },
  executive_system: { role: "combobox", name: /^Executive system/ },
  national_election_interval_turns: { role: "spinbutton", name: /^Election interval/ },
};

async function api<T>(page: Page, url: string): Promise<T> {
  const response = await page.request.get(`${BASE}${url}`);
  expect(response.status()).toBe(200);
  return (await response.json()) as T;
}

async function visit(page: Page, name: string): Promise<void> {
  const entry = page.getByRole("navigation", { name: "Screens" }).getByRole("button", { name, exact: true });
  await entry.click();
  await expect(entry).toHaveAttribute("aria-current", "page");
}

async function openCustomize(page: Page): Promise<void> {
  const summary = page.locator("summary", { hasText: "Customize policy" });
  if ((await summary.locator("xpath=..").getAttribute("open")) === null) await summary.click();
}

function canonical(decisions: Decision[]): string {
  const norm = (d: Decision): Decision => {
    const out: Decision = { ...d };
    for (const key of ["influence", "investments"]) {
      if (Array.isArray(out[key])) out[key] = [...out[key]].sort((a, b) => `${a.party_id}/${a.bloc_id}`.localeCompare(`${b.party_id}/${b.bloc_id}`));
    }
    if (Array.isArray(out.targets)) out.targets = [...out.targets].sort((a, b) => a.axis.localeCompare(b.axis));
    if (out.kind === "constitutional_amendment" && out.route === undefined) out.route = "legislative";
    return out;
  };
  return JSON.stringify([...decisions].map(norm).sort((a, b) => a.kind.localeCompare(b.kind)));
}

for (const scenario of ["deficit_demo", "tiny_valid", "decree_state"] as const) {
  test(`victory route through the interface: ${scenario}`, async ({ page }) => {
    test.setTimeout(1_800_000);
    const file = scenario === "decree_state" ? "search-v2-decree_state.json" : `search-${scenario}.json`;
    const route = JSON.parse(readFileSync(path.join(ROUTES, file), "utf-8")) as { turns: Turn[]; outcome: any };
    expect(route.outcome?.bucket, "the engine-side route ends in victory").toBe("victory");
    const shots = path.join(OUT, `${scenario}-shots`);
    mkdirSync(shots, { recursive: true });
    const consoleErrors: string[] = [];
    page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`${BASE}/`);
    const scenarios = await api<{ scenario_id: string; display_name: string }[]>(page, "/api/scenarios");
    const display = scenarios.find((s) => s.scenario_id === scenario)!.display_name;
    await page.getByRole("button", { name: `Start ${display}` }).click();
    await visit(page, "Dashboard");
    const goalAtStart = await page.getByRole("heading", { name: "Your current priority" }).locator("xpath=ancestor::section[1]").innerText();
    await page.screenshot({ path: path.join(shots, "00-dashboard.png") });

    const log: Record<string, unknown>[] = [];
    let goalAfterReform: string | null = null;
    for (const turn of route.turns) {
      const options = await api<{ blocs: { party_id: string; bloc_id: string; bloc_name: string }[] }>(page, "/api/game/decision-options");
      const blocName = (p: string, b: string) => options.blocs.find((x) => x.party_id === p && x.bloc_id === b)!.bloc_name;
      await visit(page, "Decisions");
      const kinds = turn.submitted.map((d) => d.kind);
      for (const decision of turn.submitted) {
        if (decision.kind === "bloc_relationship_investment") {
          for (const row of decision.investments) {
            await page.getByLabel(`Relationship investment for ${blocName(row.party_id, row.bloc_id)}`).fill(String(row.political_capital));
          }
        } else if (decision.kind === "constitutional_amendment") {
          await openCustomize(page);
          const radio = page.getByRole("radiogroup", { name: "Policy proposal" }).getByRole("radio", { name: "Constitutional amendment" });
          if ((await radio.getAttribute("aria-checked")) !== "true") await radio.click();
          for (const target of decision.targets) {
            const control = AXIS[target.axis]!;
            const element = page.getByRole(control.role, { name: control.name });
            if (control.role === "combobox") await element.selectOption(String(target.value));
            else await element.fill(String(target.value));
          }
          await expect(page.getByRole("radiogroup", { name: "Route" }).getByRole("radio", { name: "Legislative vote" })).toHaveAttribute("aria-checked", "true");
          for (const row of decision.influence) {
            await page.getByLabel(`Influence capital for ${blocName(row.party_id, row.bloc_id)}`).fill(String(row.political_capital));
          }
        }
      }
      const bargain = turn.submitted.find((d) => d.kind === "legislative_bargain");
      if (bargain) {
        await visit(page, "Relationships");
        const meeting = page.getByTestId("meeting-panel");
        await meeting.locator(`[data-leader-option="${bargain.character_id}"]`).click();
        await page.getByTestId("confirm-meeting").click();
        await expect(page.getByTestId("staged-meeting-summary").locator(`[data-staged-bargain="${bargain.character_id}"]`)).toBeVisible();
        await visit(page, "Decisions");
      }
      if (kinds.includes("constitutional_amendment")) {
        const previewed = page.waitForResponse((r) => r.url().includes("/api/game/preview") && r.request().method() === "POST");
        await page.getByRole("button", { name: "Preview", exact: true }).click();
        const preview = await (await previewed).json();
        expect(preview.would_pass, "the interface's own preview says the reform passes").toBe(true);
        await page.screenshot({ path: path.join(shots, `${String(turn.turn).padStart(2, "0")}-reform-preview.png`), fullPage: false });
      }
      await page.getByRole("button", { name: "Resolve turn" }).click();
      const resolved = page.waitForResponse((r) => r.url().includes("/api/game/resolve") && r.request().method() === "POST", { timeout: 120_000 });
      await page.getByRole("button", { name: "Confirm and resolve" }).click();
      const response = await resolved;
      expect(response.status()).toBe(200);
      const sent = response.request().postDataJSON() as { decisions: Decision[] };
      expect(canonical(sent.decisions), `turn ${turn.turn}: the interface sent the recorded decisions`).toBe(canonical(turn.submitted));
      const body = await response.json();
      log.push({ turn: turn.turn, kinds, headline: body.turnResult.outcome_headline });
      if (kinds.includes("constitutional_amendment")) {
        await page.screenshot({ path: path.join(shots, `${String(turn.turn).padStart(2, "0")}-reform-result.png`) });
        await visit(page, "Dashboard");
        goalAfterReform = await page.getByRole("heading", { name: "Your current priority" }).locator("xpath=ancestor::section[1]").innerText();
        await page.screenshot({ path: path.join(shots, `${String(turn.turn).padStart(2, "0")}-dashboard-after-reform.png`) });
      }
      const dash = await api<{ terminal: any }>(page, "/api/game/state");
      if (dash.terminal !== null) break;
      const plan = page.getByRole("button", { name: /^Plan turn \d+$/ });
      if (await plan.count()) await plan.click();
    }

    const final = await api<{ terminal: { bucket: string; reason_label: string; headline: string; turn: number } | null }>(page, "/api/game/state");
    expect(final.terminal, "the campaign concluded").not.toBeNull();
    expect(final.terminal!.bucket).toBe("victory");
    await visit(page, "Victory / defeat");
    await expect(page.locator("main")).toContainText(final.terminal!.headline);
    await page.screenshot({ path: path.join(shots, "99-victory.png") });
    await visit(page, "Constitution");
    const constitutionScreen = await page.locator("main").innerText();
    await page.screenshot({ path: path.join(shots, "99-constitution.png") });
    expect(consoleErrors).toEqual([]);

    writeFileSync(path.join(OUT, `${scenario}.json`), `${JSON.stringify({
      scenario, terminal: final.terminal, turnsPlayed: log.length, log,
      goalCardAtStart: goalAtStart, goalCardAfterReform: goalAfterReform,
      constitutionScreenAtEnd: constitutionScreen.slice(0, 2000), consoleErrors,
    }, null, 2)}\n`);
  });
}
