/**
 * Gate 4A0 — optional and absent data must fail safely.
 *
 * The real API will legitimately omit things: a turn with no decisions has an
 * empty ledger, a `NO_PROPOSAL` turn has no chamber vote, a campaign in progress
 * has no terminal outcome, a save root can be empty. A greybox that only renders
 * the happy fixture would prove nothing about that, so every screen is rendered
 * a second time against a deliberately hollowed-out fixture.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { GreyboxFixture } from "./contract";
import { GREYBOX_FIXTURE } from "./fixture";
import { SCREENS } from "./registry";
import { GlossaryScreen } from "./screens";

/** The same shape, with every optional field absent and every list empty. */
const EMPTY_FIXTURE: GreyboxFixture = {
  ...GREYBOX_FIXTURE,
  scenarios: [],
  saves: [],
  dashboard: {
    ...GREYBOX_FIXTURE.dashboard,
    alerts: [],
    goal: { headline: "Nothing needs your attention.", detail: null },
    terminal: null,
    concerns: {
      money: { ...GREYBOX_FIXTURE.dashboard.concerns.money, deltaText: null },
      legitimacy: { ...GREYBOX_FIXTURE.dashboard.concerns.legitimacy, deltaText: null },
      legislature: { ...GREYBOX_FIXTURE.dashboard.concerns.legislature, deltaText: null },
      constitution: { ...GREYBOX_FIXTURE.dashboard.concerns.constitution, deltaText: null },
      survival: { ...GREYBOX_FIXTURE.dashboard.concerns.survival, deltaText: null },
    },
  },
  decisionOptions: {
    ...GREYBOX_FIXTURE.decisionOptions,
    policySlot: { selected: null, options: [] },
    relationshipInvestment: { perBlocMin: 1, perBlocMax: 200, blocs: [] },
  },
  turnResult: {
    ...GREYBOX_FIXTURE.turnResult,
    drivers: [],
    ledger: [],
    unchanged: [],
    trace: [],
    terminal: null,
  },
  history: [],
  historyDetail: {},
  legislature: {
    chambers: [
      {
        chamberId: "national_assembly",
        displayName: "National Assembly",
        totalSeats: 100,
        governmentSeats: 45,
        oppositionSeats: 55,
        // No vote occurred this turn — the honest representation is null, not zero.
        supportingSeats: null,
        requiredSeats: null,
      },
    ],
    blocs: [],
  },
  relationships: [],
  glossary: [],
  government: { ...GREYBOX_FIXTURE.government, riskRows: [], institutions: [] },
  economy: { ...GREYBOX_FIXTURE.economy, revenue: [], spending: [] },
  constitution: { ...GREYBOX_FIXTURE.constitution, axes: [] },
};

describe("every registered screen tolerates absent optional data", () => {
  for (const entry of SCREENS) {
    it(`renders ${entry.id} against an empty fixture without crashing`, () => {
      const Screen = entry.component;
      render(<Screen fixture={EMPTY_FIXTURE} navigate={() => {}} />);
      expect(screen.getByRole("heading", { name: entry.heading, level: 2 })).toBeInTheDocument();
    });
  }

  // Glossary is not in SCREENS (it is chrome-level, see registry.ts and
  // GreyboxApp.test.tsx), so its resilience is exercised directly here.
  it("renders glossary against an empty fixture without crashing", () => {
    render(<GlossaryScreen fixture={EMPTY_FIXTURE} navigate={() => {}} />);
    expect(screen.getByRole("heading", { name: "Glossary", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("No glossary entries.")).toBeInTheDocument();
  });

  it("says a chamber has no recorded vote rather than showing a zero tally", () => {
    const Screen = SCREENS.find((s) => s.id === "legislature")!.component;
    render(<Screen fixture={EMPTY_FIXTURE} navigate={() => {}} />);
    expect(screen.getByText("No vote recorded")).toBeInTheDocument();
  });

  it("states an empty timeline instead of rendering a blank result panel", () => {
    const Screen = SCREENS.find((s) => s.id === "history")!.component;
    render(<Screen fixture={EMPTY_FIXTURE} navigate={() => {}} />);
    expect(screen.getByText("No turns have been resolved yet.")).toBeInTheDocument();
  });

  it("states an empty save list on the title screen", () => {
    const Screen = SCREENS.find((s) => s.id === "title")!.component;
    render(<Screen fixture={EMPTY_FIXTURE} navigate={() => {}} />);
    expect(screen.getByText("No saved campaigns yet.")).toBeInTheDocument();
  });
});
