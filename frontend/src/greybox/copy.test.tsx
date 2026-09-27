/**
 * Gate 4A3 Commit 4 — THE COPY PASS, ASSERTED AS RENDERED TEXT.
 *
 * WHY THIS IS A SEPARATE HALF. `tools/check-copy.mjs` reads SOURCE: JSX text nodes and a named set of
 * player-visible attributes and properties. That is a real check and it caught three sites this
 * commit's own survey had missed, but it cannot say a sentence reaches a player correctly — it never
 * renders anything. So the two halves prove different things and neither is allowed to claim the
 * other's ground:
 *
 *   check-copy    no FORBIDDEN word appears in player-visible source strings.
 *   this file     the NEW sentences render, as exact strings, at the locations that changed.
 *   verify:fixes  no forbidden word reaches the live DOM, in the audited states (text nodes AND the
 *                 same attribute list), which is the only check entitled to speak about a player.
 *
 * EXACT STRINGS, NOT PATTERNS, and the reason is on the record: `CabinetScreen.test.tsx` asserted
 * `/not available in this gate/i` and passed for two gates while the screen told a player about a
 * development milestone. A pattern proves a shape; only the exact sentence proves the wording, and
 * only the exact sentence fails on a half-applied edit.
 *
 * The other four locations are asserted in the suites that already have their harnesses:
 * `CabinetScreen.test.tsx`, `MeetingScreen.test.tsx` and `DecisionsScreen.test.tsx`.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UnavailableScreen } from "./screens/UnavailableScreen";

describe("UnavailableScreen speaks to a player, not about the build", () => {
  function renderIt(heading: string) {
    return render(<UnavailableScreen heading={heading} navigate={vi.fn()} />);
  }

  it("titles the panel in the game's terms", () => {
    renderIt("Economy & budget");
    expect(
      screen.getByRole("heading", { name: "Not in this version of the game" }),
    ).toBeInTheDocument();
  });

  it("leads with the half that is useful -- where the information does exist", () => {
    const { container } = renderIt("Economy & budget");
    // The previous body opened with what had NOT been built and buried the Dashboard pointer at the
    // front of a sentence about a "detailed breakdown screen". A player who can act on one of those
    // two facts should meet it first.
    const body = container.querySelector("p")?.textContent ?? "";
    expect(body).toBe(
      "The Dashboard already has a summary card for this topic. A full economy & budget screen " +
        "is not part of this version of the game.",
    );
    expect(body.indexOf("Dashboard")).toBeLessThan(body.indexOf("not part of"));
  });

  it("names the screen the player asked for, lower-cased into the sentence", () => {
    const { container } = renderIt("Legislature");
    expect(container.querySelector("p")?.textContent).toContain("A full legislature screen");
  });

  it("carries none of the build vocabulary it used to", () => {
    const { container } = renderIt("Constitution");
    const text = container.textContent ?? "";
    for (const word of ["gate", "projected", "projection", "slot", "preflight", "ruleset"]) {
      expect(text.toLowerCase()).not.toContain(word);
    }
  });
});
