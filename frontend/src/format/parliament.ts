/**
 * Gate 4A3 M-2 — every sentence the Parliament screen shows, composed from projection fields only.
 *
 * Wording note: `check:copy` forbids "projected" in player-visible text, so a preview's tally reads
 * "supporting if resolved now". Recorded votes are always labelled with the turn they were held on.
 */

import { amendmentEnactedSentence, chamberLabel, formatAmount, formatMoney, formatSignedPoints } from "./format";

/** The engine's `GovernmentRole` values (drift-guarded by `backend/tests/test_parliament_copy.py`). */
export const GOVERNMENT_ROLE_LABEL: Readonly<Record<string, string>> = {
  coalition: "In your coalition",
  confidence_and_supply: "Confidence and supply",
  opposition: "Opposition",
};

/** Display order of the roles in a chamber: the government's side first. */
export const GOVERNMENT_ROLE_ORDER: Readonly<Record<string, number>> = {
  coalition: 0,
  confidence_and_supply: 1,
  opposition: 2,
};

export function roleLabel(role: string): string {
  return GOVERNMENT_ROLE_LABEL[role] ?? "Unaligned";
}

export function parliamentIntro(countryName: string): string {
  return `The chambers of ${countryName}: who sits where, what your draft needs, and how the last vote went.`;
}

export function chamberTitle(chamber: string, totalSeats: number): string {
  return `${chamberLabel(chamber)} · ${formatAmount(totalSeats)} seats`;
}

export function budgetThreshold(seats: number): string {
  return `A budget needs ${formatAmount(seats)}`;
}

export function amendmentThreshold(seats: number): string {
  return `An amendment needs ${formatAmount(seats)}`;
}

export function noLegislatureSentence(countryName: string): string {
  return `No legislature sits in ${countryName}.`;
}

export type ParliamentDraftStatus = "current" | "not_previewed" | "changed" | "pending";

export function draftStatusText(status: ParliamentDraftStatus): string {
  switch (status) {
    case "current":
      return "Preview is current for this draft";
    case "pending":
      return "Previewing…";
    case "changed":
      return "Your draft has changed since the last preview — preview again to see expected support.";
    case "not_previewed":
      return "Not previewed yet";
  }
}

/** Why a chamber shows seats only (no supporting count). */
export type SeatsOnlyReason = "not_previewed" | "changed" | "decree" | "no_proposal" | "concluded" | "not_in_preview";

export function seatsOnlyText(reason: SeatsOnlyReason): string {
  switch (reason) {
    case "not_previewed":
      return "Seats by bloc. Preview your draft to see expected support.";
    case "changed":
      return "Seats by bloc. Your draft has changed since the last preview — preview again to see expected support.";
    case "decree":
      return "Seats by bloc. No vote is held on a decree.";
    case "no_proposal":
      return "Seats by bloc. No proposal is drafted.";
    case "concluded":
      return "Seats by bloc. The campaign has ended.";
    case "not_in_preview":
      return "Seats by bloc. This chamber does not vote on this proposal.";
  }
}

export const DECREE_DRAFT_SENTENCE = "No vote is held on a decree, so the legislature is bypassed.";
export const CONCLUDED_DRAFT_SENTENCE = "The campaign has ended.";
export const NO_PROPOSAL_SENTENCE = "No proposal drafted for this turn.";

export function currentTally(supporting: number): string {
  return `${formatAmount(supporting)} supporting if resolved now`;
}

export function neededText(required: number): string {
  return `${formatAmount(required)} needed`;
}

export function carryVerdict(carries: boolean): string {
  return carries ? "Would carry" : "Would not carry";
}

export const SUPPORT_COLUMN = "Supporting if resolved now";
export const LEGEND_SUPPORTING = "Supporting seat, if resolved now";
export const LEGEND_OTHER = "Other seat (not counted as support)";
export const LEGEND_SEATS = "Seat (colour = party; every bloc is named in the table)";

export function hemicycleLabel(
  chamber: string,
  totalSeats: number,
  tally: { supporting: number; required: number } | null,
): string {
  const name = chamberLabel(chamber);
  if (tally === null) return `${name}: ${formatAmount(totalSeats)} seats by bloc.`;
  return `${name}: ${formatAmount(tally.supporting)} of ${formatAmount(totalSeats)} seats supporting if resolved now; ${formatAmount(tally.required)} needed.`;
}

export function previewUpdatedAnnouncement(chambers: readonly { chamber: string; carries: boolean }[]): string {
  if (chambers.length === 0) return "Preview updated: no chamber votes on this draft.";
  return `Preview updated: ${chambers.map((c) => `${chamberLabel(c.chamber)} ${c.carries ? "would carry" : "would not carry"}`).join("; ")}.`;
}

/** The fallback for a chamber too large to draw at this width. */
export const BARS_NOTE = "Seats are shown as bars at this width; every bloc is listed in the table.";

// ---- The last recorded vote -------------------------------------------------------------------

export const NO_RECORDED_VOTE = "No recorded vote yet.";
export const AMENDMENT_BLOCS_NOT_RECORDED = "Per-bloc votes are not recorded for amendments.";

export function recordedVoteHeading(turn: number): string {
  return `Last recorded vote · turn ${formatAmount(turn)}`;
}

function directionPhrase(direction: string, rising: string, falling: string): string {
  if (direction === "increase") return rising;
  if (direction === "decrease") return falling;
  return "unchanged";
}

/** What the voted proposal proposed, from the stored report only. */
export function recordedProposalSentence(vote: {
  proposal_kind: string;
  outcome: string;
  budget?: {
    tax_direction: string;
    tax_delta_bps: number;
    spending_direction: string;
    opening_total_program_spending: number;
    proposed_total_program_spending: number;
  } | null;
  amendment_targets?: readonly { axis: string; opening_value: string; proposed_value: string }[];
}): string {
  const result = vote.outcome === "passed_legislative" ? "passed" : "failed";
  if (vote.proposal_kind === "budget" && vote.budget) {
    const b = vote.budget;
    const taxes =
      b.tax_direction === "unchanged"
        ? "taxes unchanged"
        : `taxes ${directionPhrase(b.tax_direction, "raised", "lowered")} (${formatSignedPoints(b.tax_delta_bps)})`;
    const spending =
      b.spending_direction === "unchanged"
        ? "spending unchanged"
        : `spending ${directionPhrase(b.spending_direction, "increased", "cut")} (${formatMoney(b.opening_total_program_spending)} → ${formatMoney(b.proposed_total_program_spending)})`;
    return `A budget, ${result}: ${taxes}; ${spending}.`;
  }
  const lines = (vote.amendment_targets ?? [])
    .map((t) => amendmentEnactedSentence({ axis: t.axis, opening_value: t.opening_value, closing_value: t.proposed_value }))
    .filter((line): line is string => line !== undefined);
  return lines.length === 0
    ? `A constitutional amendment, ${result}.`
    : `A constitutional amendment, ${result}: ${lines.join(" ")}`;
}

export function recordedChamberLine(chamber: {
  chamber: string;
  supporting_seats: number;
  required_seats: number;
  passed: boolean;
}): string {
  return `${chamberLabel(chamber.chamber)}: ${formatAmount(chamber.supporting_seats)} supporting; ${formatAmount(chamber.required_seats)} required — ${chamber.passed ? "carried" : "did not carry"}`;
}

/** Party colours, as palette tokens, assigned in order of first appearance (cycling past five). */
export const PARTY_COLOURS: readonly string[] = [
  "var(--color-gold-600)",
  "var(--color-success-400)",
  "var(--color-info-400)",
  "var(--color-warning-400)",
  "var(--color-danger-400)",
];

export function partyColours(partyIds: readonly string[]): Record<string, string> {
  const order = [...new Set(partyIds)];
  return Object.fromEntries(order.map((id, i) => [id, PARTY_COLOURS[i % PARTY_COLOURS.length]!]));
}

/** "Civic Union Reform Caucus" -> "Reform Caucus" for the arc label (the table keeps the full name). */
export function shortBlocName(blocName: string, partyName: string): string {
  const prefix = `${partyName} `;
  return blocName.startsWith(prefix) && blocName.length > prefix.length ? blocName.slice(prefix.length) : blocName;
}

/** Bloc rows in display order: the government's side first, then by name. */
export function orderBlocs<T extends { government_role: string; bloc_name: string }>(rows: readonly T[]): T[] {
  return [...rows].sort(
    (a, b) =>
      (GOVERNMENT_ROLE_ORDER[a.government_role] ?? 3) - (GOVERNMENT_ROLE_ORDER[b.government_role] ?? 3) ||
      a.bloc_name.localeCompare(b.bloc_name),
  );
}

export const UNAFFORDABLE_SENTENCE = "This draft is not affordable, so resolving it would be refused.";
