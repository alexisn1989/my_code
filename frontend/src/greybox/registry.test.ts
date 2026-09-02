/**
 * Gate 4A0 — the route table.
 *
 * The frozen plan's §8.1 main-tab bar lists eight items, plus Title, Turn
 * Result, and Victory/Defeat as their own screens — eleven navigable screens
 * in total, plus Strategic map (Strategic Military Map Gate M0, §12/§15 step
 * 7) — twelve overall. Glossary is deliberately excluded from this list: §9
 * describes it as "a static reference panel, reachable from the persistent
 * chrome, not a modal that blocks the game," i.e. a chrome-level toggle
 * (`GreyboxApp.test.tsx` covers that), not a peer navigation destination.
 * This test pins the screen list exactly: adding, removing, or renaming one
 * without updating the plan is a failure, not a silent drift.
 */

import { describe, expect, it } from "vitest";

import type { ScreenId } from "./types";
import { INITIAL_SCREEN, SCREENS, screenById } from "./registry";

const EXPECTED_SCREEN_IDS: ScreenId[] = [
  "title",
  "dashboard",
  "government",
  "economy",
  "legislature",
  "constitution",
  "relationships",
  "decisions",
  "result",
  "history",
  "strategic-map",
  "terminal",
];

describe("greybox screen registry", () => {
  it("contains exactly the twelve planned navigation screens, in order", () => {
    expect(SCREENS.map((screen) => screen.id)).toEqual(EXPECTED_SCREEN_IDS);
  });

  it("has twelve entries", () => {
    expect(SCREENS).toHaveLength(12);
  });

  it("does not register glossary as a navigation screen", () => {
    expect(SCREENS.map((screen) => screen.id)).not.toContain("glossary");
  });

  it("gives every screen a unique id and a non-empty label and heading", () => {
    const ids = SCREENS.map((screen) => screen.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const screen of SCREENS) {
      expect(screen.label.length).toBeGreaterThan(0);
      expect(screen.heading.length).toBeGreaterThan(0);
    }
  });

  it("starts on the title screen", () => {
    expect(INITIAL_SCREEN).toBe("title");
    expect(SCREENS[0]?.id).toBe("title");
  });

  it("marks only title as outside the gameplay chrome", () => {
    const withoutChrome = SCREENS.filter((screen) => !screen.showsGameplayChrome).map(
      (screen) => screen.id,
    );
    expect(withoutChrome).toEqual(["title"]);
  });

  it("resolves every registered id and rejects an unknown one", () => {
    for (const id of EXPECTED_SCREEN_IDS) {
      expect(screenById(id).id).toBe(id);
    }
    expect(() => screenById("nope" as ScreenId)).toThrow(/unknown screen id/);
  });

  it("rejects glossary specifically, since it is chrome-level, not a registered screen", () => {
    expect(() => screenById("glossary" as ScreenId)).toThrow(/unknown screen id/);
  });
});
