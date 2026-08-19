/**
 * Gate 4A0 — greybox rendering, navigation, and the structural claims the frozen
 * plan makes about the interface.
 *
 * Deliberately NO full-page snapshots: every assertion targets a role, a label,
 * or a specific value, so a layout pass in Gate 4A5 does not produce a wall of
 * meaningless diffs.
 *
 * Interactions use `fireEvent` from `@testing-library/react`, which is already a
 * devDependency. `@testing-library/user-event` would read better for the
 * keyboard cases, but Gate 4A0 may not add a dependency — so the keyboard claim
 * is asserted the honest way instead: the controls are native `<button>`
 * elements, which is precisely what makes Enter and Space activate them without
 * any JavaScript of ours, and they are focusable in DOM order.
 */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GreyboxApp } from "./GreyboxApp";
import { SCREENS } from "./registry";

function goTo(label: string) {
  fireEvent.click(screen.getByRole("button", { name: label }));
}

describe("greybox shell", () => {
  it("renders the title screen first", () => {
    render(<GreyboxApp />);
    expect(screen.getByRole("heading", { name: "New campaign", level: 2 })).toBeInTheDocument();
  });

  it("renders exactly one h1 for the application", () => {
    render(<GreyboxApp />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("offers a navigation control for every registered screen", () => {
    render(<GreyboxApp />);
    const nav = screen.getByRole("navigation", { name: "Screens" });
    for (const entry of SCREENS) {
      expect(within(nav).getByRole("button", { name: entry.label })).toBeInTheDocument();
    }
  });

  it("renders every screen with its expected heading when navigated to", () => {
    render(<GreyboxApp />);
    for (const entry of SCREENS) {
      goTo(entry.label);
      expect(screen.getByRole("heading", { name: entry.heading, level: 2 })).toBeInTheDocument();
    }
  });

  it("marks the current screen with aria-current", () => {
    render(<GreyboxApp />);
    goTo("Legislature");
    const nav = screen.getByRole("navigation", { name: "Screens" });
    expect(within(nav).getByRole("button", { name: "Legislature" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("makes every navigation control a focusable native button, so Enter and Space activate it", () => {
    render(<GreyboxApp />);
    const nav = screen.getByRole("navigation", { name: "Screens" });
    for (const entry of SCREENS) {
      const control = within(nav).getByRole("button", { name: entry.label });
      expect(control.tagName).toBe("BUTTON");
      expect(control).not.toHaveAttribute("disabled");
      expect(control).not.toHaveAttribute("tabindex", "-1");
      control.focus();
      expect(control).toHaveFocus();
    }
  });

  it("keeps a visible focus ring on navigation controls", () => {
    render(<GreyboxApp />);
    const control = screen.getByRole("button", { name: "Constitution" });
    expect(control.className).toContain("focus-visible:ring");
  });

  it("shows the persistent national header on gameplay screens and not on the title screen", () => {
    render(<GreyboxApp />);
    expect(screen.queryByTestId("national-header")).not.toBeInTheDocument();

    goTo("Dashboard");
    const header = screen.getByTestId("national-header");
    expect(within(header).getByText("Valdoria")).toBeInTheDocument();
    expect(within(header).getByText("Hereditary monarchy")).toBeInTheDocument();
    expect(within(header).getByText("Capital 500 / 1,000")).toBeInTheDocument();

    goTo("Economy");
    expect(screen.getByTestId("national-header")).toBeInTheDocument();
  });

  it("carries all five player-facing concerns in the persistent header", () => {
    render(<GreyboxApp />);
    goTo("Dashboard");
    const header = screen.getByTestId("national-header");
    for (const concern of ["Money:", "Legitimacy:", "Legislature:", "Constitution:", "Survival:"]) {
      expect(within(header).getByText(concern)).toBeInTheDocument();
    }
  });

  it("shows a dismissible help note", () => {
    render(<GreyboxApp />);
    expect(screen.getByRole("note", { name: "How to govern" })).toBeInTheDocument();
    goTo("Dismiss");
    expect(screen.queryByRole("note", { name: "How to govern" })).not.toBeInTheDocument();
  });
});

describe("dashboard", () => {
  it("shows five concern cards and a goal card", () => {
    render(<GreyboxApp />);
    goTo("Dashboard");
    const cards = screen.getByTestId("concern-cards");
    expect(within(cards).getAllByRole("heading", { level: 3 })).toHaveLength(5);
    expect(
      screen.getByText("Your priority: put the constitutional amendment to a vote."),
    ).toBeInTheDocument();
  });

  it("labels the map as presentation-only and claims no province mechanics", () => {
    render(<GreyboxApp />);
    goTo("Dashboard");
    expect(screen.getByTestId("map-placeholder")).toHaveAccessibleName(/presentation only/i);
    expect(
      screen.getByText("This map shows national identity only. No province-level mechanics exist."),
    ).toBeInTheDocument();
  });
});

describe("decision workspace", () => {
  it("presents budget and amendment as one mutually exclusive slot", () => {
    render(<GreyboxApp />);
    goTo("Decisions");

    const group = screen.getByRole("radiogroup", { name: "Policy proposal" });
    const budget = within(group).getByRole("radio", { name: "Budget proposal" });
    const amendment = within(group).getByRole("radio", { name: "Constitutional amendment" });

    expect(amendment).toHaveAttribute("aria-checked", "true");
    expect(budget).toHaveAttribute("aria-checked", "false");

    fireEvent.click(budget);
    expect(budget).toHaveAttribute("aria-checked", "true");
    expect(amendment).toHaveAttribute("aria-checked", "false");
  });

  it("shows relationship investment as a separate, non-exclusive slot", () => {
    render(<GreyboxApp />);
    goTo("Decisions");
    expect(
      screen.getByRole("heading", { name: "Relationship investment (separate slot)", level: 3 }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Investment is not part of the policy slot/)).toBeInTheDocument();
  });

  it("displays affordability from projected values", () => {
    render(<GreyboxApp />);
    goTo("Decisions");
    const meter = screen.getByRole("meter", { name: "Political capital committed" });
    expect(meter).toHaveAttribute("aria-valuetext", "300 of 500 political capital committed");
    expect(screen.getByText("Affordable")).toBeInTheDocument();
  });

  it("offers no working Resolve action and says nothing was resolved", () => {
    render(<GreyboxApp />);
    goTo("Decisions");
    expect(screen.queryByRole("button", { name: /^resolve/i })).not.toBeInTheDocument();
    expect(screen.getByText(/no turn can be resolved/i)).toBeInTheDocument();
  });
});

describe("turn result and history share one component", () => {
  it("renders the same result component from the live screen and the history detail", () => {
    render(<GreyboxApp />);

    goTo("Turn result");
    expect(screen.getByTestId("turn-result-view")).toHaveAttribute("data-context", "live");
    expect(screen.getByText("Amendment passed, 67 of 100 seats (67 required).")).toBeInTheDocument();

    goTo("History");
    expect(screen.getByTestId("turn-result-view")).toHaveAttribute("data-context", "history");
  });

  it("discloses outcome, then drivers, then trace on demand", () => {
    render(<GreyboxApp />);
    goTo("Turn result");

    expect(screen.getByRole("heading", { name: "Turn 3 — outcome", level: 3 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Why this happened", level: 3 })).toBeInTheDocument();
    expect(screen.getByText("constitutional_amendment_resolved")).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Show exact values" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByText("ConstitutionalAmendmentReport.chamber.supporting_seats"),
    ).not.toBeInTheDocument();

    fireEvent.click(toggle);
    expect(
      screen.getByText("ConstitutionalAmendmentReport.chamber.supporting_seats"),
    ).toBeInTheDocument();
  });

  it("selects a historical turn and renders its own stored detail", () => {
    render(<GreyboxApp />);
    goTo("History");

    fireEvent.click(screen.getByRole("button", { name: /Turn 1 —/ }));
    expect(screen.getByText("Opposition — Main bloc improved to -53.85%.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Turn 2 —/ }));
    expect(screen.getByText("Opposition — Main bloc improved to -27.74%.")).toBeInTheDocument();
  });

  it("fails safely when a selected turn has no stored detail in the fixture", () => {
    render(<GreyboxApp />);
    goTo("History");

    // Turn 3 is listed in the timeline but deliberately absent from historyDetail,
    // so this exercises a genuinely missing optional payload rather than a mock.
    fireEvent.click(screen.getByRole("button", { name: /Turn 3 —/ }));
    expect(screen.getByText(/No stored detail for that turn/)).toBeInTheDocument();
    expect(screen.queryByTestId("turn-result-view")).not.toBeInTheDocument();
  });
});

describe("terminal screen", () => {
  it("shows both campaign outcomes and offers no Resolve action", () => {
    render(<GreyboxApp />);
    goTo("Victory / defeat");

    expect(screen.getByText("You lost the election with 48.22% (50% required).")).toBeInTheDocument();
    expect(
      screen.getByText("Peaceful liberalization completed — you won with 58.10%."),
    ).toBeInTheDocument();
    expect(screen.getByText(/No further turn can be resolved/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /resolve/i })).not.toBeInTheDocument();
  });

  it("routes back to a new campaign", () => {
    render(<GreyboxApp />);
    goTo("Victory / defeat");
    goTo("New campaign");
    expect(screen.getByRole("heading", { name: "New campaign", level: 2 })).toBeInTheDocument();
  });
});

describe("glossary is persistent chrome, not a navigation screen", () => {
  it("is not one of the registered navigation controls", () => {
    render(<GreyboxApp />);
    const nav = screen.getByRole("navigation", { name: "Screens" });
    expect(within(nav).queryByRole("button", { name: "Glossary" })).not.toBeInTheDocument();
  });

  it("opens as a non-blocking panel from the persistent top bar, without navigating away", () => {
    render(<GreyboxApp />);
    goTo("Legislature");
    expect(screen.getByRole("heading", { name: "Legislature", level: 2 })).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Glossary" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);

    expect(screen.getByRole("region", { name: "Glossary" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Glossary", level: 2 })).toBeInTheDocument();
    // The screen underneath is still present -- this is a panel, not a route change.
    expect(screen.getByRole("heading", { name: "Legislature", level: 2 })).toBeInTheDocument();
  });

  it("is reachable from the Title screen, before any campaign is loaded", () => {
    render(<GreyboxApp />);
    expect(screen.getByRole("heading", { name: "New campaign", level: 2 })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Glossary" }));
    expect(screen.getByRole("region", { name: "Glossary" })).toBeInTheDocument();
  });

  it("closes on a second toggle", () => {
    render(<GreyboxApp />);
    const toggle = screen.getByRole("button", { name: "Glossary" });
    fireEvent.click(toggle);
    expect(screen.getByRole("region", { name: "Glossary" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close glossary" }));
    expect(screen.queryByRole("region", { name: "Glossary" })).not.toBeInTheDocument();
  });
});

describe("title screen", () => {
  it("lists all three scenarios and marks the showcase", () => {
    render(<GreyboxApp />);
    expect(screen.getByRole("heading", { name: "The Decree State", level: 3 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Deficit Demo", level: 3 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tiny Valid", level: 3 })).toBeInTheDocument();
    expect(screen.getByText("Recommended starting scenario")).toBeInTheDocument();
  });

  it("shows an unloadable save with its specific integrity problem rather than hiding it", () => {
    render(<GreyboxApp />);
    expect(
      screen.getByText("entry 3: entry_hash does not match the recomputed digest"),
    ).toBeInTheDocument();
  });
});

describe("the greybox is static", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn(() => {
      throw new Error("the greybox must not perform network requests");
    }) as unknown as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("makes zero network calls while every screen is visited", () => {
    render(<GreyboxApp />);
    for (const entry of SCREENS) {
      goTo(entry.label);
    }
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
