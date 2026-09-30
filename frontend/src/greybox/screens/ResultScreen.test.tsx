/**
 * Gate 4A3 Commit 5b: the concluding turn's live result states "this turn ended the campaign" ONCE.
 *
 * `TurnResultView` renders that panel with the headline, and `ResultScreen` used to wrap its
 * "Review the outcome" button in a second Panel with the identical title, so the page carried two
 * adjacent headings saying the same thing. The branch renders only on the turn that concludes a
 * campaign, which is why no earlier gate reached it; the T21 walkthrough did.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { liveTurnResultQueryKey } from "../../api/queries";
import { ResultScreen } from "./ResultScreen";

const BASE_RESULT = {
  revision: "11.11",
  turn: 11,
  outcome_headline: "The scheduled election was lost.",
  outcome_tone: "negative",
  drivers: [],
  ledger: [],
  unchanged: [],
  trace: [],
  terminal: null,
};

function renderWith(result: unknown) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(liveTurnResultQueryKey(), result);
  const navigate = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ResultScreen navigate={navigate} />
    </QueryClientProvider>,
  );
  return navigate;
}

describe("ResultScreen on the turn that concludes a campaign", () => {
  it("says the campaign ended exactly once, and still offers the outcome", () => {
    const navigate = renderWith({
      ...BASE_RESULT,
      terminal: {
        bucket: "defeat",
        reason_label: "Electoral defeat",
        turn: 11,
        headline: "Removed from office: electoral defeat, turn 11.",
      },
    });
    expect(screen.getAllByRole("heading", { name: "This turn ended the campaign" })).toHaveLength(1);
    const headings = screen.getAllByRole("heading").map((h) => h.textContent);
    expect(new Set(headings).size, `duplicate headings: ${headings.join(" | ")}`).toBe(headings.length);
    fireEvent.click(screen.getByRole("button", { name: "Review the outcome" }));
    expect(navigate).toHaveBeenCalledWith("terminal");
  });

  it("offers the ordinary next steps, and no terminal heading, on an ordinary turn", () => {
    renderWith(BASE_RESULT);
    expect(screen.queryByRole("heading", { name: "This turn ended the campaign" })).toBeNull();
    expect(screen.getByRole("button", { name: "Back to Dashboard" })).toBeInTheDocument();
  });
});

describe("TurnResultView drivers", () => {
  it("renders every driver when one reason repeats, without a duplicate-key warning", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    renderWith({
      ...BASE_RESULT,
      drivers: [
        { category: "politics", reason_id: "bloc_relationship_resolved", label: "First bloc moved.", params: {} },
        { category: "politics", reason_id: "bloc_relationship_resolved", label: "Second bloc moved.", params: {} },
      ],
    });
    const duplicateKeyWarnings = errors.mock.calls.filter((call) =>
      call.some((part) => String(part).includes("same key")),
    );
    errors.mockRestore();
    expect(duplicateKeyWarnings).toEqual([]);
    const list = screen.getByRole("heading", { name: "Why this happened" }).closest("section");
    expect(list?.querySelectorAll("li")).toHaveLength(2);
  });
});
