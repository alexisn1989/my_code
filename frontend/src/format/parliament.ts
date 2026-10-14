/**
 * Gate 4A3 M-2 — every sentence the Parliament screen shows, composed from projection fields only.
 *
 * Wording note: `check:copy` forbids "projected" in player-visible text, so a preview's tally reads
 * "supporting if resolved now". Recorded votes are always labelled with the turn they were held on.
 */

import { amendmentEnactedSentence, chamberLabel, formatAmount, formatBpsPercent, formatMoney, formatSignedPoints } from "./format";

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

// ---- Gate 4A3 M-3: the bloc panel ----------------------------------------------------------------

/** Why a bargain (or influence) cannot be staged for the current draft, or `null` when it can.
 * Moved here from `MeetingScreen` so Relationships and the bloc panel say it identically. */
export function bargainBlockedReason(
  policySlot: "budget" | "amendment" | null,
  route: "legislative" | "decree",
): string | null {
  if (policySlot === null) {
    return "Put a budget or an amendment in this turn's draft first — a bargain buys support for one exact proposal, so there has to be one.";
  }
  if (route === "decree") {
    return "This turn's proposal is being decreed, not put to the chamber. A bargain buys votes, and a decree holds none — change the route on the Decisions screen to bargain over it.";
  }
  return null;
}

/** Influence needs the same two things a bargain does: a proposal, put to the chamber. */
export function influenceBlockedReason(
  policySlot: "budget" | "amendment" | null,
  route: "legislative" | "decree",
): string | null {
  if (policySlot === null) {
    return "Put a budget or an amendment in this turn's draft first — influence moves a bloc's vote on one exact proposal.";
  }
  if (route === "decree") {
    return "This turn's proposal is being decreed, so no vote is held and influence would change nothing.";
  }
  return null;
}

export const CAMPAIGN_ENDED = "The campaign has ended.";

export function blocStanceLine(partyName: string, role: string): string {
  return `${partyName} · ${roleLabel(role)}`;
}

/** "Seats: Lower chamber 10, Upper chamber 6" from every chamber's row for one bloc. */
export function blocSeatsLine(rows: readonly { chamber: string; seats: number }[]): string {
  return `Seats: ${rows.map((r) => `${chamberLabel(r.chamber)} ${formatAmount(r.seats)}`).join(", ")}`;
}

export function relationshipLine(relationshipBps: number): string {
  return `${formatBpsPercent(relationshipBps)} with your government`;
}

function preferencePhrase(bps: number, rising: string, falling: string): string {
  if (bps > 0) return `Favours ${rising}`;
  if (bps < 0) return `Favours ${falling}`;
  return "No preference";
}

/** A bloc's tax preference in words. Positive favours rises (`legislative_voting.py`). */
export function taxPreferenceLine(bps: number): string {
  return `${preferencePhrase(bps, "rises", "cuts")} (preference ${formatBpsPercent(bps)})`;
}

/** A bloc's spending preference in words. Positive favours more spending. */
export function spendingPreferenceLine(bps: number): string {
  return `${preferencePhrase(bps, "more", "less")} (preference ${formatBpsPercent(bps)})`;
}

export function leaderTraitsLine(t: {
  loyalty_bps: number;
  independence_bps: number;
  ambition_bps: number;
  personal_trust_bps: number;
}): string {
  return `Loyalty ${formatBpsPercent(t.loyalty_bps)} · independence ${formatBpsPercent(t.independence_bps)} · ambition ${formatBpsPercent(t.ambition_bps)} · trust in you ${formatBpsPercent(t.personal_trust_bps)}`;
}

/** What the leader offers to endorse. With nothing drafted there is no budget to name, so the offer
 * is for "your proposal" (Gate 4A3 M-5, finding F2: it used to fall through to "your budget"). */
export function offerLine(slot: "budget" | "amendment" | null): string {
  if (slot === "amendment") return "Endorse your constitutional amendment.";
  if (slot === "budget") return "Endorse your budget.";
  return "Endorse your proposal.";
}

export const PRICE_FIXED = "The price is theirs and fixed; there is no haggling.";
export const REFUSES_LINE = "Will not deal at any price.";
export const OFFER_EFFECT_NOTE =
  "An endorsement makes their party's blocs support the proposal more. Preview after staging to see the support with it.";

export function noCounterpartLine(partyName: string): string {
  return `No leader of ${partyName} offers a bargain.`;
}

export function stageBargainLabel(price: number): string {
  return `Stage this bargain · ${formatAmount(price)}`;
}

export function replaceBargainLabel(name: string, price: number): string {
  return `Replace bargain with ${name} · ${formatAmount(price)}`;
}

export function keepBargainLabel(name: string): string {
  return `Keep ${name}'s bargain`;
}

export function replaceBargainSentence(oldName: string, oldPrice: number | null): string {
  const price = oldPrice === null ? "" : `, for ${formatAmount(oldPrice)}`;
  return `You already have a bargain staged: ${oldName}'s endorsement${price}. Only one bargain is allowed per turn, so staging this one replaces it. Your proposal, influence and investments stay as they are.`;
}

export function replacedAnnouncement(oldName: string, newName: string): string {
  return `Replaced your staged bargain with ${oldName} by ${newName}.`;
}

/** `blocCount` is the number of DISTINCT blocs of the party, across every chamber. */
export function stagedPartyWideLine(leaderName: string, blocCount: number, partyName: string): string {
  if (blocCount === 1) return `Staged: endorsement from ${leaderName}, which applies to ${partyName}'s one bloc.`;
  return `Staged: endorsement from ${leaderName}, which applies to all ${formatAmount(blocCount)} blocs of ${partyName}.`;
}

export const INFLUENCE_NOTE = "Capital that moves this bloc's vote on your current proposal, this turn only. Applies to this bloc in every chamber.";
export const INVESTMENT_NOTE =
  "Lasting: raises the relationship, which drifts back toward the bloc's usual stance each turn. The closer it is to its ceiling, the less the same capital adds.";
export const INVESTMENT_PREVIEW_NOTE = "Preview shows what it would add.";

export function investmentRangeLine(minimum: number, maximum: number): string {
  return `Range: ${formatAmount(minimum)}–${formatAmount(maximum)}.`;
}

export function influenceSummaryLine(capital: number, slot: "budget" | "amendment"): string {
  return `Influence on this vote: ${formatAmount(capital)} capital (on your ${slot === "amendment" ? "constitutional amendment" : "budget"}).`;
}

/** Distinct blocs of one party across every chamber (a bloc seated in two chambers counts once). */
export function distinctPartyBlocCount(rows: readonly { party_id: string; bloc_id: string }[], partyId: string): number {
  return new Set(rows.filter((r) => r.party_id === partyId).map((r) => r.bloc_id)).size;
}

/** A panel input's value as a draft amount: empty and 0 both mean "nothing". */
export function amountFromInput(raw: string): number | undefined {
  if (raw.trim() === "") return undefined;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) return undefined;
  return value;
}

export function withdrewAnnouncement(leaderName: string): string {
  return `Withdrew the bargain with ${leaderName}.`;
}

export function keptAnnouncement(leaderName: string): string {
  return `Kept your staged bargain with ${leaderName}.`;
}

export const NOTHING_STAGED_FOR_BLOC = "Nothing staged for this bloc.";
export const CHANGE_PROPOSAL_NOTE = "Rewrite what is being voted on. This replaces your draft; it is done in Decisions.";
export const BARGAIN_ACTION_NOTE = "Above: one bargain per turn, party-wide, at the leader's price.";
