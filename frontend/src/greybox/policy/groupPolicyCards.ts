/**
 * Gate 4A3A — pure grouping logic for the two-level progressive-disclosure
 * card browser (never 33-45 cards on one screen at once).
 *
 * Level 1 is always exactly three major choices: Budget policy,
 * Constitutional reform, Take no major action. Level 2 is a family within
 * whichever major is open -- Taxation/Spending under Budget policy;
 * Government form/Decree authority/Term limits/Election schedule under
 * Constitutional reform. Take no major action is itself the single
 * `restraint` card and has no level 2.
 *
 * `PolicyCard.category` only distinguishes "taxation" | "spending" |
 * "constitution" | "restraint" -- constitution's four families are not a
 * server field, so this module derives them from each card's own stable
 * `card_id` prefix (`constitution_decree_authority_`,
 * `constitution_government_form_`, `constitution_term_limit_`,
 * `constitution_election_interval_` -- exactly the prefixes
 * `policy_cards.py`'s four constitutional generators emit). Purely a display
 * grouping; it invents no legality and computes no consequence.
 */

import type { PolicyCard } from "../../api/client";

export type MajorChoiceId = "budget" | "constitution" | "restraint";

export type FamilyId =
  | "taxation"
  | "spending"
  | "decree_authority"
  | "government_form"
  | "term_limit"
  | "election_interval";

export interface PolicyCardFamily {
  id: FamilyId;
  label: string;
  cards: PolicyCard[];
}

export interface PolicyCardMajorChoice {
  id: MajorChoiceId;
  label: string;
  /** Empty for `restraint`, which has no level 2 -- it IS the single card. */
  families: PolicyCardFamily[];
  /** All cards under this major, across every family -- used for the
   * level-1 result count and for locating which major/family owns the
   * currently selected card. */
  cards: PolicyCard[];
}

const FAMILY_LABELS: Record<FamilyId, string> = {
  taxation: "Taxation",
  spending: "Spending",
  decree_authority: "Decree authority",
  government_form: "Government form",
  term_limit: "Term limits",
  election_interval: "Election schedule",
};

const MAJOR_LABELS: Record<MajorChoiceId, string> = {
  budget: "Budget policy",
  constitution: "Constitutional reform",
  restraint: "Take no major action",
};

/** Order both level-1 majors and level-2 families are presented in. */
const FAMILY_ORDER: readonly FamilyId[] = [
  "taxation",
  "spending",
  "decree_authority",
  "government_form",
  "term_limit",
  "election_interval",
];

function familyOf(card: PolicyCard): FamilyId | null {
  if (card.category === "taxation") return "taxation";
  if (card.category === "spending") return "spending";
  if (card.category === "restraint") return null;
  if (card.card_id.startsWith("constitution_decree_authority_")) return "decree_authority";
  if (card.card_id.startsWith("constitution_government_form_")) return "government_form";
  if (card.card_id.startsWith("constitution_term_limit_")) return "term_limit";
  if (card.card_id.startsWith("constitution_election_interval_")) return "election_interval";
  throw new Error(`unrecognized constitutional policy card family: ${card.card_id}`);
}

function majorOf(family: FamilyId): "budget" | "constitution" {
  return family === "taxation" || family === "spending" ? "budget" : "constitution";
}

/** Groups a flat catalog into the two-level structure, preserving each
 * card's relative order within its family. Cards are never dropped: every
 * card returned by the server appears in exactly one family (or, for the
 * restraint card, directly under its major with no family). */
export function groupPolicyCards(cards: readonly PolicyCard[]): PolicyCardMajorChoice[] {
  const familyBuckets = new Map<FamilyId, PolicyCard[]>();
  const restraintCards: PolicyCard[] = [];

  for (const card of cards) {
    const family = familyOf(card);
    if (family === null) {
      restraintCards.push(card);
      continue;
    }
    const bucket = familyBuckets.get(family);
    if (bucket) {
      bucket.push(card);
    } else {
      familyBuckets.set(family, [card]);
    }
  }

  const budgetFamilies: PolicyCardFamily[] = [];
  const constitutionFamilies: PolicyCardFamily[] = [];
  for (const family of FAMILY_ORDER) {
    const bucketCards = familyBuckets.get(family);
    if (bucketCards === undefined) {
      continue;
    }
    const entry: PolicyCardFamily = { id: family, label: FAMILY_LABELS[family], cards: bucketCards };
    (majorOf(family) === "budget" ? budgetFamilies : constitutionFamilies).push(entry);
  }

  return [
    {
      id: "budget",
      label: MAJOR_LABELS.budget,
      families: budgetFamilies,
      cards: budgetFamilies.flatMap((family) => family.cards),
    },
    {
      id: "constitution",
      label: MAJOR_LABELS.constitution,
      families: constitutionFamilies,
      cards: constitutionFamilies.flatMap((family) => family.cards),
    },
    {
      id: "restraint",
      label: MAJOR_LABELS.restraint,
      families: [],
      cards: restraintCards,
    },
  ];
}

/** Locates which major/family a given card id belongs to, for keeping the
 * browser's open major/family in sync with a card selected some other way
 * (e.g. restored from a previous session, or selected before a switch). */
export function locateCard(
  majors: readonly PolicyCardMajorChoice[],
  cardId: string,
): { major: MajorChoiceId; family: FamilyId | null } | null {
  for (const major of majors) {
    if (major.id === "restraint") {
      if (major.cards.some((card) => card.card_id === cardId)) {
        return { major: major.id, family: null };
      }
      continue;
    }
    for (const family of major.families) {
      if (family.cards.some((card) => card.card_id === cardId)) {
        return { major: major.id, family: family.id };
      }
    }
  }
  return null;
}
