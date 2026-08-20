/**
 * Gate 4A2 — the screen registry, now backed by live data instead of one
 * frozen fixture. `ScreenId` moved to `./types` (it is a UI-only concept,
 * not part of the generated API contract, so it does not belong under
 * `src/api/`).
 *
 * ELEVEN entries, not twelve, for the same reason Gate 4A0 established: the
 * frozen plan's own §8.1 lists the main-tab bar as eight items (Dashboard ·
 * Government · Economy · Legislature · Constitution · Relationships ·
 * Decisions · History) and separately, in §9, describes Glossary as
 * "a static reference panel, reachable from the persistent chrome, not a
 * modal that blocks the game" -- i.e. a chrome-level toggle, never a peer
 * navigation tab. `GlossaryScreen` stays outside this list and is rendered by
 * `GreyboxApp`'s persistent header.
 *
 * Five of the eleven (Government, Economy, Legislature, Constitution,
 * Relationships) render `UnavailableScreen`: the real API's `DashboardProjection`
 * gives only five SUMMARY concern cards, never the per-institution,
 * per-chamber, per-bloc, or per-budget-line breakdown these screens were
 * mocked up against in Gate 4A0. Building that breakdown client-side would be
 * exactly the invented-arithmetic/unprojected-value problem Gate 4A2 exists to
 * avoid; the honest state is "not available in this gate," not fabricated
 * detail. The playable loop -- Title, Dashboard, Decisions, Turn Result,
 * History, Terminal -- is fully live.
 */

import type { ComponentType } from "react";

import { DashboardScreen } from "./screens/DashboardScreen";
import { DecisionsScreen } from "./screens/DecisionsScreen";
import { HistoryScreen } from "./screens/HistoryScreen";
import { ResultScreen } from "./screens/ResultScreen";
import { TerminalScreen } from "./screens/TerminalScreen";
import { TitleScreen } from "./screens/TitleScreen";
import { UnavailableScreen } from "./screens/UnavailableScreen";
import type { ScreenId } from "./types";

export interface ScreenProps {
  navigate: (screen: ScreenId) => void;
}

export interface ScreenDefinition {
  id: ScreenId;
  /** Navigation label, and the accessible name of its nav control. */
  label: string;
  /** The heading each screen is expected to render. */
  heading: string;
  component: ComponentType<ScreenProps>;
  showsGameplayChrome: boolean;
}

function unavailable(heading: string): ComponentType<ScreenProps> {
  function Screen(props: ScreenProps) {
    return <UnavailableScreen heading={heading} {...props} />;
  }
  Screen.displayName = `Unavailable(${heading})`;
  return Screen;
}

export const SCREENS: readonly ScreenDefinition[] = [
  {
    id: "title",
    label: "Title",
    heading: "New campaign",
    component: TitleScreen,
    showsGameplayChrome: false,
  },
  {
    id: "dashboard",
    label: "Dashboard",
    heading: "National dashboard",
    component: DashboardScreen,
    showsGameplayChrome: true,
  },
  {
    id: "government",
    label: "Government",
    heading: "Government",
    component: unavailable("Government"),
    showsGameplayChrome: true,
  },
  {
    id: "economy",
    label: "Economy",
    heading: "Economy & budget",
    component: unavailable("Economy & budget"),
    showsGameplayChrome: true,
  },
  {
    id: "legislature",
    label: "Legislature",
    heading: "Legislature",
    component: unavailable("Legislature"),
    showsGameplayChrome: true,
  },
  {
    id: "constitution",
    label: "Constitution",
    heading: "Constitution",
    component: unavailable("Constitution"),
    showsGameplayChrome: true,
  },
  {
    id: "relationships",
    label: "Relationships",
    heading: "Relationships",
    component: unavailable("Relationships"),
    showsGameplayChrome: true,
  },
  {
    id: "decisions",
    label: "Decisions",
    heading: "Decision workspace",
    component: DecisionsScreen,
    showsGameplayChrome: true,
  },
  {
    id: "result",
    label: "Turn result",
    heading: "Turn result",
    component: ResultScreen,
    showsGameplayChrome: true,
  },
  {
    id: "history",
    label: "History",
    heading: "History",
    component: HistoryScreen,
    showsGameplayChrome: true,
  },
  {
    id: "terminal",
    label: "Victory / defeat",
    heading: "Victory / defeat",
    component: TerminalScreen,
    showsGameplayChrome: true,
  },
];

/** The screen shown on first render. */
export const INITIAL_SCREEN: ScreenId = "title";

export function screenById(id: ScreenId): ScreenDefinition {
  const found = SCREENS.find((screen) => screen.id === id);
  if (!found) {
    throw new Error(`unknown screen id: ${id}`);
  }
  return found;
}
