/**
 * Gate 4A3 M-1: the seven places on the country map, and where each one leads.
 *
 * ONE table, read by the map's pins, the ordinary "Places" list and the tests, so a pin and its list
 * twin can never disagree about name or destination. Every destination is an existing screen, and
 * the screen's own navigation entry stays where it was: the map is a second way in, never the only
 * one. Economy and the Glossary have no place: there is nothing meaningful behind a landmark for
 * them.
 *
 * `plot` is where each institution's building stands on the capital's illustrated street plan, as
 * fractions (0-1) of the plan's width and height: one arrangement for wide maps and one for phones,
 * spaced so 44 px buildings never touch. These are positions in an illustration, not locations of
 * anything the game simulates.
 */

import type { ScreenId } from "../types";

export type PlaceId =
  | "parliament"
  | "palace"
  | "constitution"
  | "treasury"
  | "archive"
  | "embassies"
  | "garrison";

export interface Place {
  id: PlaceId;
  name: string;
  screen: ScreenId;
  /** The destination screen's navigation name, as the nav shows it. */
  opens: string;
  /** What the player goes there to do, in a few words. */
  purpose: string;
  /** The place's number, shown on its pin (phone layout) and in the Places list. */
  number: number;
  plot: { wide: readonly [number, number]; phone: readonly [number, number] };
}

export const PLACES: readonly Place[] = [
  { id: "parliament", name: "Parliament", screen: "legislature", opens: "Legislature", purpose: "Chambers, blocs and votes", number: 1, plot: { wide: [0.24, 0.30], phone: [0.18, 0.36] } },
  { id: "palace", name: "Palace", screen: "government", opens: "Government", purpose: "Your cabinet and appointments", number: 2, plot: { wide: [0.5, 0.12], phone: [0.5, 0.13] } },
  { id: "constitution", name: "Constitution hall", screen: "constitution", opens: "Constitution", purpose: "Your objective's three conditions", number: 3, plot: { wide: [0.76, 0.30], phone: [0.82, 0.36] } },
  { id: "treasury", name: "Treasury", screen: "decisions", opens: "Decisions", purpose: "Draft taxes and spending", number: 4, plot: { wide: [0.24, 0.56], phone: [0.18, 0.64] } },
  { id: "archive", name: "Archive", screen: "history", opens: "History", purpose: "Every turn so far", number: 5, plot: { wide: [0.76, 0.56], phone: [0.82, 0.64] } },
  { id: "embassies", name: "Embassies", screen: "relationships", opens: "Relationships", purpose: "Foreign assistance and party leaders", number: 6, plot: { wide: [0.3, 0.86], phone: [0.3, 0.89] } },
  { id: "garrison", name: "Garrison", screen: "strategic-map", opens: "Strategic map", purpose: "Formations and theaters", number: 7, plot: { wide: [0.72, 0.86], phone: [0.7, 0.89] } },
];

/** A place's accessible name, identical on its pin and on its list twin. */
export function placeAccessibleName(place: Place): string {
  return `${place.name}: opens ${place.opens}`;
}
