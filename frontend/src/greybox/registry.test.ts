/**
 * Gate 4A0 — the route table.
 *
 * The frozen plan names twelve screens. This test pins the list exactly: adding,
 * removing, or renaming one without updating the plan is a failure, not a
 * silent drift.
 */

import { describe, expect, it } from "vitest";

import type { ScreenId } from "./contract";
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
  "terminal",
  "glossary",
];

describe("greybox screen registry", () => {
  it("contains exactly the twelve planned screens, in order", () => {
    expect(SCREENS.map((screen) => screen.id)).toEqual(EXPECTED_SCREEN_IDS);
  });

  it("has twelve entries", () => {
    expect(SCREENS).toHaveLength(12);
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

  it("marks title and glossary as outside the gameplay chrome, and the rest inside", () => {
    const withoutChrome = SCREENS.filter((screen) => !screen.showsGameplayChrome).map(
      (screen) => screen.id,
    );
    expect(withoutChrome).toEqual(["title", "glossary"]);
  });

  it("resolves every id and rejects an unknown one", () => {
    for (const id of EXPECTED_SCREEN_IDS) {
      expect(screenById(id).id).toBe(id);
    }
    expect(() => screenById("nope" as ScreenId)).toThrow(/unknown screen id/);
  });
});
