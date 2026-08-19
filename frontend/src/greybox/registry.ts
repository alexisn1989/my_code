/**
 * Gate 4A0 greybox — the screen registry.
 *
 * The frozen plan's screen inventory, expressed as data. There is deliberately
 * NO router: `react-router-dom` was removed in Phase 2A as unused, and Gate 4A0
 * may not add a dependency. Navigation is a `ScreenId` in component state, and
 * this table is what the shell renders from — so "the screen inventory as
 * routes" exists as a single testable list rather than as scattered JSX.
 *
 * `showsGameplayChrome: false` marks the screens that exist outside a running
 * campaign, where the persistent national header would be claiming a country
 * that is not loaded.
 *
 * ELEVEN entries, not twelve. The frozen plan's own §8.1 lists the main-tab bar
 * as eight items (Dashboard · Government · Economy · Legislature · Constitution
 * · Relationships · Decisions · History) and separately, in §9, describes
 * Glossary as "a static reference panel, reachable from the persistent chrome,
 * not a modal that blocks the game" — i.e. a chrome-level toggle, never a peer
 * navigation tab. `GlossaryScreen` therefore stays in `./screens` and is
 * rendered by `GreyboxApp`'s persistent header, not registered here.
 */

import type { ComponentType } from "react";

import type { ScreenId } from "./contract";
import {
  ConstitutionScreen,
  DashboardScreen,
  DecisionsScreen,
  EconomyScreen,
  GovernmentScreen,
  HistoryScreen,
  LegislatureScreen,
  RelationshipsScreen,
  ResultScreen,
  type ScreenProps,
  TerminalScreen,
  TitleScreen,
} from "./screens";

export interface ScreenDefinition {
  id: ScreenId;
  /** Navigation label, and the accessible name of its nav control. */
  label: string;
  /** The heading each screen is expected to render. */
  heading: string;
  component: ComponentType<ScreenProps>;
  showsGameplayChrome: boolean;
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
    component: GovernmentScreen,
    showsGameplayChrome: true,
  },
  {
    id: "economy",
    label: "Economy",
    heading: "Economy & budget",
    component: EconomyScreen,
    showsGameplayChrome: true,
  },
  {
    id: "legislature",
    label: "Legislature",
    heading: "Legislature",
    component: LegislatureScreen,
    showsGameplayChrome: true,
  },
  {
    id: "constitution",
    label: "Constitution",
    heading: "Constitution",
    component: ConstitutionScreen,
    showsGameplayChrome: true,
  },
  {
    id: "relationships",
    label: "Relationships",
    heading: "Relationships",
    component: RelationshipsScreen,
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
