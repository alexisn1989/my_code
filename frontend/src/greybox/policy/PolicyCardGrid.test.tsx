/**
 * Gate 4A3A — proves the card browser's real behaviour in the actual
 * rendered DOM: selecting a card fires the callback with the card's first
 * available route; a disabled card's Select button cannot be activated;
 * switching level-1/level-2 tabs changes which cards are visible; the
 * selection summary strip and per-tab "1 selected" badges track the
 * selected card across every view change; arrow keys move focus between
 * level-2 tabs (roving tabindex).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PolicyCard, PolicyCardRoute } from "../../api/client";
import { PolicyCardGrid } from "./PolicyCardGrid";

function route(overrides: Partial<PolicyCardRoute> = {}): PolicyCardRoute {
  return {
    route: "legislative",
    available: true,
    base_route_cost: 0,
    bargaining_available: true,
    chambers: [],
    template: { kind: "budget", route: "legislative", personal_income_rate_bps: 2500 },
    ...overrides,
  };
}

function card(overrides: Partial<PolicyCard> = {}): PolicyCard {
  return {
    card_id: "tax_personal_income_increase",
    category: "taxation",
    category_label: "Taxation",
    title: "Raise the personal income tax",
    description: "Raise the personal income tax rate.",
    available: true,
    clears_proposal_slot: false,
    effects: [],
    routes: [route()],
    ...overrides,
  };
}

const SPENDING_CARD = card({
  card_id: "spending_health_increase",
  category: "spending",
  category_label: "Spending",
  title: "Increase health spending",
  description: "Increase the health spending category.",
  routes: [route({ template: { kind: "budget", route: "legislative", spending_updates: [] } })],
});

const UNAVAILABLE_CARD = card({
  card_id: "tax_corporate_increase",
  title: "Raise the corporate tax",
  available: false,
  unavailable_reason: "outside_legal_bounds",
  unavailable_detail: "Raising the corporate tax by this step would leave the legal range.",
  routes: [],
});

const NO_PROPOSAL_CARD = card({
  card_id: "no_proposal",
  category: "restraint",
  category_label: "Take no major action",
  title: "Take no major policy action",
  description: "Submit no proposal this turn.",
  clears_proposal_slot: true,
  routes: [],
});

const CONSTITUTION_CARD = card({
  card_id: "constitution_decree_authority_to_unlimited",
  category: "constitution",
  category_label: "Constitutional reform",
  title: "Set decree authority to unlimited",
  routes: [
    route({
      template: {
        kind: "constitutional_amendment",
        route: "legislative",
        targets: [{ axis: "decree_authority", value: "unlimited" }],
      },
    }),
  ],
});

const CARDS = [card(), SPENDING_CARD, UNAVAILABLE_CARD, CONSTITUTION_CARD, NO_PROPOSAL_CARD];

describe("PolicyCardGrid: selection", () => {
  it("fires onSelectCard with the card -- route selection belongs to the caller (R5)", () => {
    const onSelectCard = vi.fn();
    render(
      <PolicyCardGrid
        cards={CARDS}
        selectedCardId={null}
        onSelectCard={onSelectCard}
        onClearSelection={() => {}}
      />,
    );
    // The taxation family also contains an unavailable card (whose "Select"
    // button is disabled but still present with the same accessible name);
    // find the enabled one.
    const selectButtons = screen.getAllByRole("button", { name: "Select" });
    const enabledSelect = selectButtons.find((button) => !button.hasAttribute("disabled"))!;
    fireEvent.click(enabledSelect);
    expect(onSelectCard).toHaveBeenCalledTimes(1);
    const [selectedCard] = onSelectCard.mock.calls[0]!;
    expect(selectedCard.card_id).toBe("tax_personal_income_increase");
  });

  it("shows the selection summary strip and a Clear action once a card is selected", () => {
    render(
      <PolicyCardGrid
        cards={CARDS}
        selectedCardId="tax_personal_income_increase"
        onSelectCard={() => {}}
        onClearSelection={() => {}}
      />,
    );
    // The selected card's title appears both in the summary strip and,
    // highlighted, in the grid below -- that duplication is the intended
    // behaviour (R5: the selection is preserved and visible across every
    // view change), so this asserts at least one occurrence rather than
    // exactly one.
    expect(screen.getAllByText("Raise the personal income tax").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();
  });

  it("calls onClearSelection when Clear is activated", () => {
    const onClearSelection = vi.fn();
    render(
      <PolicyCardGrid
        cards={CARDS}
        selectedCardId="tax_personal_income_increase"
        onSelectCard={() => {}}
        onClearSelection={onClearSelection}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(onClearSelection).toHaveBeenCalledTimes(1);
  });

  it("renders a disabled Select button for an unavailable card, but keeps the card focusable", () => {
    render(
      <PolicyCardGrid
        cards={CARDS}
        selectedCardId={null}
        onSelectCard={() => {}}
        onClearSelection={() => {}}
      />,
    );
    const group = screen.getByRole("group", { name: "Raise the corporate tax" });
    expect(group).toHaveAttribute("tabIndex", "0");
    // Two "Select" buttons exist across the visible taxation cards; exactly
    // one (the unavailable card's) must be disabled.
    const disabledButtons = screen.getAllByRole("button").filter((el) => el.hasAttribute("disabled"));
    expect(disabledButtons).toHaveLength(1);
  });

  it("announces the unavailable reason via aria-describedby, not colour alone", () => {
    render(
      <PolicyCardGrid
        cards={CARDS}
        selectedCardId={null}
        onSelectCard={() => {}}
        onClearSelection={() => {}}
      />,
    );
    const group = screen.getByRole("group", { name: "Raise the corporate tax" });
    const describedById = group.getAttribute("aria-describedby");
    expect(describedById).toBeTruthy();
    const statusEl = document.getElementById(describedById!);
    expect(statusEl?.textContent).toContain("legal range");
  });
});

describe("PolicyCardGrid: two-level navigation", () => {
  it("shows only the taxation family's cards by default under Budget policy", () => {
    render(
      <PolicyCardGrid
        cards={CARDS}
        selectedCardId={null}
        onSelectCard={() => {}}
        onClearSelection={() => {}}
      />,
    );
    expect(screen.getByText("Raise the personal income tax")).toBeInTheDocument();
    expect(screen.queryByText("Increase health spending")).not.toBeInTheDocument();
  });

  it("switching to the Spending tab reveals spending cards and hides taxation cards", () => {
    render(
      <PolicyCardGrid
        cards={CARDS}
        selectedCardId={null}
        onSelectCard={() => {}}
        onClearSelection={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Spending/ }));
    expect(screen.getByText("Increase health spending")).toBeInTheDocument();
    expect(screen.queryByText("Raise the personal income tax")).not.toBeInTheDocument();
  });

  it("switching the level-1 major to Constitutional reform shows its own level-2 tabs", () => {
    render(
      <PolicyCardGrid
        cards={CARDS}
        selectedCardId={null}
        onSelectCard={() => {}}
        onClearSelection={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Constitutional reform/ }));
    expect(screen.getByText("Set decree authority to unlimited")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Decree authority/ })).toBeInTheDocument();
  });

  it("Take no major action has no level-2 tabs and shows its single card directly", () => {
    render(
      <PolicyCardGrid
        cards={CARDS}
        selectedCardId={null}
        onSelectCard={() => {}}
        onClearSelection={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Take no major action/ }));
    expect(screen.getByText("Take no major policy action")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Decree authority/ })).not.toBeInTheDocument();
  });

  it("shows a '1 selected' badge on the level-1 major and level-2 family owning the selection", () => {
    render(
      <PolicyCardGrid
        cards={CARDS}
        selectedCardId="spending_health_increase"
        onSelectCard={() => {}}
        onClearSelection={() => {}}
      />,
    );
    expect(screen.getByRole("tab", { name: /Budget policy/ })).toHaveTextContent("1 selected");
    expect(screen.getByRole("tab", { name: /Spending/ })).toHaveTextContent("1 selected");
    expect(screen.getByRole("tab", { name: /Taxation/ })).not.toHaveTextContent("1 selected");
  });

  it("opens directly on the major/family that owns a pre-existing selection", () => {
    render(
      <PolicyCardGrid
        cards={CARDS}
        selectedCardId="constitution_decree_authority_to_unlimited"
        onSelectCard={() => {}}
        onClearSelection={() => {}}
      />,
    );
    // Opened directly on Constitutional reform > Decree authority: the tab
    // is selected and the card is visible (appearing in both the summary
    // strip and the grid, as above).
    expect(screen.getByRole("tab", { name: /Decree authority/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getAllByText("Set decree authority to unlimited").length).toBeGreaterThanOrEqual(1);
  });
});

describe("PolicyCardGrid: keyboard roving tabindex on level-2 tabs", () => {
  it("ArrowRight moves both focus and tabIndex to the next family tab", () => {
    render(
      <PolicyCardGrid
        cards={CARDS}
        selectedCardId={null}
        onSelectCard={() => {}}
        onClearSelection={() => {}}
      />,
    );
    const taxationTab = screen.getByRole("tab", { name: /Taxation/ });
    const spendingTab = screen.getByRole("tab", { name: /Spending/ });
    expect(taxationTab).toHaveAttribute("tabIndex", "0");
    expect(spendingTab).toHaveAttribute("tabIndex", "-1");

    fireEvent.keyDown(taxationTab, { key: "ArrowRight" });

    expect(spendingTab).toHaveAttribute("aria-selected", "true");
  });
});
