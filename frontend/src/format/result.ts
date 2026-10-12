/**
 * Gate 4A3 M-4 — the turn result, restructured: a proposal card, then people and reactions, then
 * what else happened, then the bookkeeping collapsed (the approved M-V `result` mockup).
 *
 * Everything here reads only the turn result the server built for THAT turn -- `recorded_vote`,
 * `no_vote_reason` and the stored drivers -- so the live result and History, which render the same
 * projection through the same component, cannot disagree. Nothing reads today's options or state.
 *
 * THE INVARIANT: every driver appears exactly once. `partitionDrivers` decides where each one goes,
 * keeps its ORIGINAL index (the anchor its Trace link points at), and reports any bloc reaction it
 * could not attach rather than letting it disappear.
 */

import { chamberLabel, formatAmount, formatBpsPercent, formatSignedPoints, isRoutineDriver, outcomeFirst } from "./format";
import { partyColours } from "./parliament";

export interface DriverLike {
  reason_id: string;
  params?: Record<string, string | number>;
  label: string;
}

/** One driver with the position the server recorded it at -- the identity its anchor uses. */
export interface IndexedDriver {
  driver: DriverLike;
  index: number;
  reason_id: string;
}

/** A bloc's net move this turn, with the reactions that made it up. */
export interface BlocGroup {
  key: string;
  partyId: string;
  blocId: string;
  total: IndexedDriver;
  components: IndexedDriver[];
}

export interface DriverPartition {
  card: IndexedDriver[];
  people: IndexedDriver[];
  blocs: BlocGroup[];
  other: IndexedDriver[];
  routine: IndexedDriver[];
  /** Bloc reactions with no matching bloc row. They are ALSO in `other`, so they stay visible; this
   * list is the report that they could not be grouped. */
  unmatched: IndexedDriver[];
}

/** What the proposal did: the vote and the enacted changes. */
export const CARD_REASONS: ReadonlySet<string> = new Set([
  "legislative_vote_resolved",
  "budget_blocked_by_legislature",
  "tax_rate_changed",
  "spending_category_changed",
  "constitutional_amendment_enacted",
]);

/** People who acted on the player's proposals: leaders, ministers, counterparts, promisees. */
export const PEOPLE_REASONS: ReadonlySet<string> = new Set([
  "legislative_bargain_accepted",
  "legislative_bargain_refused_will_not_deal",
  "cabinet_appointed",
  "cabinet_replaced",
  "cabinet_dismissed",
  "foreign_assistance_granted",
  "foreign_assistance_counterpart_is_hostile",
  "foreign_assistance_pool_exhausted",
  "promise_made",
  "promise_fulfilled",
  "promise_breached",
  "promise_released",
  "promise_expired",
]);

export const BLOC_TOTAL_REASON = "bloc_relationship_resolved";

/** The parts of a bloc's move that are attached under its row. (`relationship_decay_resolved` is a
 * routine step and stays there.) */
export const BLOC_COMPONENT_REASONS: ReadonlySet<string> = new Set([
  "enacted_policy_relationship_reaction",
  "decree_bypass_relationship_reaction",
]);

function blocPair(params: Record<string, string | number> | undefined): { partyId: string; blocId: string } | null {
  if (params === undefined) return null;
  const partyId = params["party_id"];
  const blocId = params["bloc_id"];
  return typeof partyId === "string" && typeof blocId === "string" ? { partyId, blocId } : null;
}

/** The match key is the PAIR: two parties may both have a bloc called `main`. */
export function blocKey(partyId: string, blocId: string): string {
  return JSON.stringify([partyId, blocId]);
}

export function partitionDrivers(drivers: readonly DriverLike[]): DriverPartition {
  const rows: IndexedDriver[] = drivers.map((driver, index) => ({ driver, index, reason_id: driver.reason_id }));
  const card: IndexedDriver[] = [];
  const people: IndexedDriver[] = [];
  const blocs: BlocGroup[] = [];
  const other: IndexedDriver[] = [];
  const routine: IndexedDriver[] = [];
  const unmatched: IndexedDriver[] = [];
  const components: IndexedDriver[] = [];
  const byKey = new Map<string, BlocGroup>();

  for (const row of rows) {
    const reason = row.reason_id;
    if (isRoutineDriver(row.driver)) {
      routine.push(row);
    } else if (CARD_REASONS.has(reason)) {
      card.push(row);
    } else if (PEOPLE_REASONS.has(reason)) {
      people.push(row);
    } else if (reason === BLOC_TOTAL_REASON && blocPair(row.driver.params) !== null) {
      const pair = blocPair(row.driver.params)!;
      const key = blocKey(pair.partyId, pair.blocId);
      const group: BlocGroup = { key, partyId: pair.partyId, blocId: pair.blocId, total: row, components: [] };
      blocs.push(group);
      // The FIRST row for a pair receives its components; a duplicate would still be shown.
      if (!byKey.has(key)) byKey.set(key, group);
    } else if (BLOC_COMPONENT_REASONS.has(reason)) {
      components.push(row);
    } else {
      other.push(row);
    }
  }

  // Components are recorded BEFORE their bloc's total, so they are attached in a second pass, in
  // server order.
  for (const row of components) {
    const pair = blocPair(row.driver.params);
    const group = pair === null ? undefined : byKey.get(blocKey(pair.partyId, pair.blocId));
    if (group === undefined) {
      unmatched.push(row);
      other.push(row);
    } else {
      group.components.push(row);
    }
  }

  const byIndex = (a: IndexedDriver, b: IndexedDriver) => a.index - b.index;
  return {
    card: outcomeFirst(card),
    people,
    blocs,
    other: outcomeFirst([...other].sort(byIndex)),
    routine,
    unmatched,
  };
}

// ---- The proposal card ------------------------------------------------------------------------

export type VerdictKind = "enacted" | "not_carried" | "decree" | "no_proposal";

/** The verdict in words, from the stored fields only -- never colour alone. */
export function resultVerdict(
  recordedVote: { outcome: string } | null | undefined,
  noVoteReason: string | null | undefined,
): { kind: VerdictKind; word: string } | null {
  if (recordedVote) {
    return recordedVote.outcome === "passed_legislative"
      ? { kind: "enacted", word: "Enacted" }
      : { kind: "not_carried", word: "Did not carry" };
  }
  if (noVoteReason === "enacted_by_decree") return { kind: "decree", word: "Enacted by decree" };
  if (noVoteReason === "no_proposal") return { kind: "no_proposal", word: "No proposal" };
  return null;
}

export const YOUR_PROPOSAL = "Your proposal";

/** The card's "Your proposal" line when no chamber vote was held. A decree has none: its verdict
 * ("Enacted by decree") and its own driver ("Enacted by decree — no vote was held.") already say it,
 * and what was decreed is told by the enacted-change lines, so a third sentence would only repeat. */
export function noVoteLine(noVoteReason: string | null | undefined): string | null {
  return noVoteReason === "no_proposal" ? "No proposal was put to a vote this turn." : null;
}

export function recordedHemicycleLabel(chamber: {
  chamber: string;
  supporting_seats: number;
  total_seats: number;
  required_seats: number;
}): string {
  return `${chamberLabel(chamber.chamber)}: ${formatAmount(chamber.supporting_seats)} recorded supporting of ${formatAmount(chamber.total_seats)} seats; ${formatAmount(chamber.required_seats)} needed`;
}

export const RECORDED_SEATS_LEGEND = "Filled: recorded supporting seat. Hollow: other seat. Colour shows the party; the bloc table names every bloc.";
export const VOTES_BY_BLOC = "Votes by bloc (recorded)";

export function recordedBlocSupport(row: { supporting_seats: number; seats: number }): string {
  return `${formatAmount(row.supporting_seats)} of ${formatAmount(row.seats)}`;
}

/** ONE palette per recorded vote, from the union of party ids across every chamber (chambers in
 * stored order, then rows in stored order), so a party has the same colour in every chamber however
 * the chambers differ in membership or order. A function of the vote alone: History and live agree. */
export function voteColours(vote: {
  chambers: readonly { blocs?: readonly { party_id: string }[] }[];
}): Record<string, string> {
  return partyColours(vote.chambers.flatMap((c) => (c.blocs ?? []).map((b) => b.party_id)));
}

// ---- People and reactions -----------------------------------------------------------------------

export const PEOPLE_HEADING = "People and reactions";
export const BLOCS_HEADING = "How the blocs took it";
export const OTHER_HEADING = "What else happened";
export const NO_PEOPLE = "No one acted on your proposals this turn.";
export const NO_BLOC_MOVES = "No bloc's relationship changed.";
export const NOTHING_ELSE = "Nothing else was recorded this turn.";

/** Whose face goes beside a people entry: the incoming holder, the person dismissed, the
 * counterpart -- using the portrait the server attached from THAT turn's state, or none. */
export function personOf(
  params: Record<string, string | number> | undefined,
): { portraitRef: string | null; name: string } | null {
  if (params === undefined) return null;
  const pick = (refKey: string, nameKey: string) => {
    const name = params[nameKey];
    if (typeof name !== "string") return null;
    const ref = params[refKey];
    return { portraitRef: typeof ref === "string" ? ref : null, name };
  };
  return (
    pick("character_portrait_ref", "character_display_name") ??
    pick("outgoing_character_portrait_ref", "outgoing_character_display_name") ??
    pick("counterpart_portrait_ref", "counterpart_display_name")
  );
}

/** A bloc's net move, in words and a mark: never colour alone. */
export function blocMove(params: Record<string, string | number> | undefined): {
  name: string;
  direction: "closer" | "cooler" | "unchanged";
  mark: string;
  words: string;
  span: string;
} | null {
  if (params === undefined) return null;
  const name = params["bloc_display_name"];
  const change = params["applied_total_change_bps"];
  const opening = params["opening_relationship_bps"];
  const closing = params["closing_relationship_bps"];
  if (typeof name !== "string" || typeof change !== "number" || typeof opening !== "number" || typeof closing !== "number") {
    return null;
  }
  const direction = change > 0 ? "closer" : change < 0 ? "cooler" : "unchanged";
  const mark = direction === "closer" ? "▲" : direction === "cooler" ? "▼" : "•";
  const word = direction === "unchanged" ? "no change" : direction;
  return {
    name,
    direction,
    mark,
    words: direction === "unchanged" ? word : `${word} ${formatSignedPoints(change)}`,
    span: `relationship ${formatBpsPercent(opening)} → ${formatBpsPercent(closing)}`,
  };
}

// ---- The collapsed sections ---------------------------------------------------------------------

export function routineSummary(count: number): string {
  return `Routine steps this turn (${formatAmount(count)})`;
}

export function committedSummary(count: number): string {
  return `What your decision committed (${formatAmount(count)})`;
}

export const UNCHANGED_SUMMARY = "What did not change";
