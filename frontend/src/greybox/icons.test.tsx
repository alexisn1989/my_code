/**
 * Gate 4A3 Commit 4 — THE ICON SET'S MEANING, not merely its presence.
 *
 * WHY THIS FILE IS SHAPED THE WAY IT IS. A non-empty screen-reader label is not evidence of a
 * correct one: a caution mark paired with the word "positive" would pass any non-emptiness check and
 * mislead every screen-reader user, while telling a sighted user the opposite of what the sentence
 * says. So every icon's expected MEANING is pinned as a table, and pinned AT ITS CONSUMER — because
 * it is the pairing at each call site that can go wrong, not the table in `icons.tsx`.
 *
 * WHAT THE PREVIOUS GLYPHS WERE NOT TESTED FOR, which is why this file exists at all. Before this
 * commit the never-colour-alone triple was covered only through the `sr-only` word; the glyph itself
 * was asserted nowhere. All 419 tests passed after the ten glyphs were replaced by ten SVGs — which
 * is itself the finding: the visible half of "never colour alone" was unguarded.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GlossaryScreen } from "./screens/GlossaryScreen";
import { DeltaText, ToneValue } from "./components";
import {
  DIRECTION_ICON,
  IconCapital,
  IconRouteOneWay,
  IconRouteTwoWay,
  TONE_ICON,
  type IconName,
} from "./icons";
import { PolicyCardView } from "./policy/PolicyCardView";
import type { Direction, Tone } from "./types";

/** Every icon this set exports, by the `data-icon` name a DOM assertion looks for. */
const ALL_ICONS: readonly { name: IconName; Component: () => React.ReactNode }[] = [
  ...(Object.entries(TONE_ICON) as [Tone, () => React.ReactNode][]).map(([tone, Component]) => ({
    name: tone as IconName,
    Component,
  })),
  ...(Object.entries(DIRECTION_ICON) as [Direction, () => React.ReactNode][]).map(
    ([direction, Component]) => ({ name: direction as IconName, Component }),
  ),
  { name: "route-one-way" as IconName, Component: IconRouteOneWay },
  { name: "route-two-way" as IconName, Component: IconRouteTwoWay },
  { name: "capital" as IconName, Component: IconCapital },
];

function renderIcon(Component: () => React.ReactNode): SVGElement {
  const { container } = render(<Component />);
  const svg = container.querySelector("svg");
  expect(svg).not.toBeNull();
  return svg as SVGElement;
}

describe("the icon set is stroke-only and structurally uniform", () => {
  it("exports exactly the ten icons the three groups need", () => {
    expect(ALL_ICONS.map((icon) => icon.name).sort()).toEqual(
      [
        "capital",
        "caution",
        "down",
        "negative",
        "neutral",
        "positive",
        "route-one-way",
        "route-two-way",
        "unchanged",
        "up",
      ].sort(),
    );
  });

  it.each(ALL_ICONS)("$name is stroke-only, 24px and never filled", ({ Component }) => {
    const svg = renderIcon(Component);
    // `fill="none"` and `stroke="currentColor"` together are what make the icon inherit the tone
    // token rather than carrying a colour of its own -- which is also what stops it slipping a
    // hard-coded colour past `check:palette`, since there is no colour here to check.
    expect(svg.getAttribute("fill")).toBe("none");
    expect(svg.getAttribute("stroke")).toBe("currentColor");
    expect(svg.getAttribute("stroke-width")).toBe("2");
    expect(svg.getAttribute("viewBox")).toBe("0 0 24 24");
    // No descendant may reintroduce a fill or a literal colour.
    for (const node of Array.from(svg.querySelectorAll("*"))) {
      expect(node.getAttribute("fill")).toBeNull();
      expect(node.getAttribute("stroke")).toBeNull();
    }
  });

  it.each(ALL_ICONS)("$name is hidden from assistive technology and carries no name", ({ Component }) => {
    const svg = renderIcon(Component);
    // The OPPOSITE of `Portrait`'s choice, and deliberately so: each icon sits beside an existing
    // `sr-only` word (or, in the map legend, a `<dt>`) that already names it. Labelling the icon too
    // would make a screen reader announce the meaning twice.
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    expect(svg.getAttribute("role")).toBeNull();
    expect(svg.getAttribute("aria-label")).toBeNull();
    expect(svg.getAttribute("aria-labelledby")).toBeNull();
  });

  it("gives every icon a distinct shape, so colour is never what distinguishes them", () => {
    const shapes = ALL_ICONS.map(({ Component }) => renderIcon(Component).innerHTML);
    expect(new Set(shapes).size).toBe(ALL_ICONS.length);
  });
});

/* ------------------------------------------------------------------------------------------------
 * MEANING, PINNED PER SYMBOL AND ASSERTED AT EACH CONSUMER.
 *
 * The expected word is written out here rather than read from `TONE_LABEL`/`DIRECTION_LABEL`. Reading
 * it from the same map the component renders would make the assertion circular: it would pass for any
 * pairing at all, including a caution mark labelled "positive", because both sides would move
 * together. A literal is what makes this a check rather than a restatement.
 * ---------------------------------------------------------------------------------------------- */

const TONE_MEANING: readonly { tone: Tone; icon: IconName; word: string }[] = [
  { tone: "positive", icon: "positive", word: "positive" },
  { tone: "negative", icon: "negative", word: "negative" },
  { tone: "caution", icon: "caution", word: "caution" },
  { tone: "neutral", icon: "neutral", word: "neutral" },
];

const DIRECTION_MEANING: readonly { direction: Direction; icon: IconName; word: string }[] = [
  { direction: "up", icon: "up", word: "up" },
  { direction: "down", icon: "down", word: "down" },
  { direction: "unchanged", icon: "unchanged", word: "unchanged" },
];

describe("ToneValue pairs each mark with the word that means the same thing", () => {
  it.each(TONE_MEANING)("$tone renders the $icon mark and the word \"$word\"", ({ tone, icon, word }) => {
    const { container } = render(<ToneValue tone={tone}>42</ToneValue>);
    expect(container.querySelector(`svg[data-icon="${icon}"]`)).not.toBeNull();
    expect(screen.getByText(word)).toHaveClass("sr-only");
    // And no OTHER icon: a component rendering two marks would satisfy a presence check while
    // showing a reader two contradictory meanings.
    expect(container.querySelectorAll("svg[data-icon]")).toHaveLength(1);
  });

  it("uses four different marks for the four tones", () => {
    const icons = TONE_MEANING.map(({ tone }) => {
      const { container } = render(<ToneValue tone={tone}>42</ToneValue>);
      return container.querySelector("svg[data-icon]")?.getAttribute("data-icon");
    });
    expect(new Set(icons).size).toBe(4);
  });
});

describe("DeltaText pairs each mark with the word that means the same thing", () => {
  it.each(DIRECTION_MEANING)(
    "$direction renders the $icon mark and the word \"$word\"",
    ({ direction, icon, word }) => {
      const { container } = render(<DeltaText deltaText="+3" direction={direction} />);
      expect(container.querySelector(`svg[data-icon="${icon}"]`)).not.toBeNull();
      expect(screen.getByText(word)).toHaveClass("sr-only");
      expect(container.querySelectorAll("svg[data-icon]")).toHaveLength(1);
    },
  );

  it("no longer shares a mark with the CAUTION tone, which `▲` used to do", () => {
    const { container: up } = render(<DeltaText deltaText="+3" direction="up" />);
    const { container: caution } = render(<ToneValue tone="caution">42</ToneValue>);
    const upIcon = up.querySelector("svg[data-icon]")?.getAttribute("data-icon");
    const cautionIcon = caution.querySelector("svg[data-icon]")?.getAttribute("data-icon");
    expect(upIcon).toBe("up");
    expect(cautionIcon).toBe("caution");
    expect(upIcon).not.toBe(cautionIcon);
  });

  it("no longer shares a mark between UNCHANGED and the NEUTRAL tone, which `■` used to do", () => {
    const { container: unchanged } = render(<DeltaText deltaText="0" direction="unchanged" />);
    const { container: neutral } = render(<ToneValue tone="neutral">42</ToneValue>);
    expect(unchanged.querySelector("svg[data-icon]")?.getAttribute("data-icon")).toBe("unchanged");
    expect(neutral.querySelector("svg[data-icon]")?.getAttribute("data-icon")).toBe("neutral");
  });
});

describe("a policy card's effect chips use the same direction marks", () => {
  const card = {
    card_id: "test-card",
    title: "Test card",
    summary: "A card.",
    slot_kind: "budget",
    effects: [
      {
        label: "Health spending",
        current_value: 100,
        proposed_value: 120,
        unit: "money",
        direction: "up" as Direction,
      },
      {
        label: "Tax rate",
        current_value: 1500,
        proposed_value: 1200,
        unit: "bps",
        direction: "down" as Direction,
      },
      {
        label: "Debt",
        current_value: 5,
        proposed_value: 5,
        unit: "money",
        direction: "unchanged" as Direction,
      },
    ],
  };

  it("renders one mark per effect, each matching its own direction and word", () => {
    // Cast at the boundary only: this is the generated `PolicyCard` shape, and the point of the test
    // is the direction/word pairing rather than the projection's full field list.
    const { container } = render(
      <PolicyCardView card={card as never} selected={false} onSelect={() => {}} />,
    );
    expect(container.querySelectorAll("svg[data-icon]")).toHaveLength(3);
    for (const { icon, word } of DIRECTION_MEANING) {
      expect(container.querySelector(`svg[data-icon="${icon}"]`)).not.toBeNull();
      expect(screen.getAllByText(word).some((node) => node.classList.contains("sr-only"))).toBe(true);
    }
  });
});

/* ------------------------------------------------------------------------------------------------
 * THE REPLACED CHARACTERS MUST NOT SURVIVE ANYWHERE.
 * ---------------------------------------------------------------------------------------------- */

/** The seven characters the icon set replaces. `▲` and `■` appear once each although each had TWO
 * jobs, which is the duplication the set removes. */
const REPLACED_GLYPHS = ["✓", "✗", "▲", "▼", "■", "→", "↔", "★"];

describe("no replaced glyph reaches the DOM", () => {
  it.each(TONE_MEANING)("ToneValue $tone renders none of them", ({ tone }) => {
    const { container } = render(<ToneValue tone={tone}>42</ToneValue>);
    for (const glyph of REPLACED_GLYPHS) {
      expect(container.textContent ?? "").not.toContain(glyph);
    }
  });

  it.each(DIRECTION_MEANING)("DeltaText $direction renders none of them", ({ direction }) => {
    const { container } = render(<DeltaText deltaText="+3" direction={direction} />);
    for (const glyph of REPLACED_GLYPHS) {
      expect(container.textContent ?? "").not.toContain(glyph);
    }
  });

  // A DOM scan rather than a source grep: a missed call site is what this is guarding, and a source
  // grep cannot tell a live call from a comment -- the false-positive class that made F4's premise
  // wrong in the first place.
  it("the Glossary, which renders prose rather than marks, contains none of them either", () => {
    const { container } = render(<GlossaryScreen />);
    for (const glyph of REPLACED_GLYPHS) {
      expect(container.textContent ?? "").not.toContain(glyph);
    }
  });
});
