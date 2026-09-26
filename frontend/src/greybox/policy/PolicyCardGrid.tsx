/**
 * Gate 4A3A — the card browser: two-level progressive disclosure (never
 * 33-45 cards on one screen at once), a persistent selection summary strip,
 * and the accessible level-2 tablist (`role="tablist"`/`role="tab"` with
 * arrow-key roving tabindex, `aria-controls` on the panel, a result count on
 * every tab).
 *
 * Owns no draft state and calls no endpoint: `onSelectCard` is the only way
 * this component talks to the outside world, and it fires with the SAME
 * `(card, route)` pair whatever route the caller decides to apply (this
 * component always offers the card's first available route as the default;
 * DecisionsScreen owns what "first available" means for its call to
 * `applyCard`).
 */

import { useState } from "react";

import type { PolicyCard } from "../../api/client";
import { wrapIndex } from "../../format/format";
import { EmptyNote } from "../components";
import type { FamilyId, MajorChoiceId } from "./groupPolicyCards";
import { groupPolicyCards, locateCard } from "./groupPolicyCards";
import { PolicyCardView } from "./PolicyCardView";

/**
 * THE ONE CARD PANEL, and why it has a single fixed id (Gate 4A3 Commit 3, finding A8).
 *
 * This browser renders exactly ONE `role="tabpanel"` element, whose CONTENT swaps as tabs change.
 * So every tab -- level 1 and level 2 alike -- points its `aria-controls` at this one id, and that
 * reference always resolves. The alternative, an id per tab, cannot work here: only the active
 * panel exists in the DOM, so every inactive tab's `aria-controls` would dangle, which is the
 * defect A8 recorded in a different guise.
 *
 * Which tab the panel currently belongs to is carried by `aria-labelledby` instead, pointing at the
 * deepest active tab. That is the part that genuinely varies, and it varies over ids that exist.
 */
const CARD_PANEL_ID = "policy-card-panel";

/** A tab's DOM id, built from stable slug ids and never from a display label.
 *
 * A8, exactly: ids were built as `policy-tab-${ariaLabel}-${tab.id}` where `ariaLabel` is authored
 * prose such as "Budget policy". That produced `id="policy-tab-Budget policy-taxation"` -- an id
 * CONTAINING A SPACE -- and `aria-controls` is a space-separated IDREF LIST, so the browser read one
 * reference as two ("policy-panel-Budget" and "policy-taxation"), neither of which existed. axe
 * rated it critical. Slug ids (`budget`, `taxation`, `constitution`, ...) cannot contain spaces:
 * `MajorChoiceId` and `FamilyId` are closed unions of lowercase identifiers, and a test asserts the
 * generated ids match a no-whitespace pattern so a future label-derived id fails loudly.
 */
function tabDomId(level: "major" | "family", ...parts: string[]): string {
  return ["policy-tab", level, ...parts].join("-");
}

function TabList({
  ariaLabel,
  level,
  idScope,
  tabs,
  activeId,
  onActivate,
  buttonClassName,
}: {
  ariaLabel: string;
  /** Distinguishes the two tablists' id namespaces, so a family id can never collide with a major
   * id even if the two vocabularies ever overlap. */
  level: "major" | "family";
  /** Extra id segments that scope this list. Family tabs are scoped by their major, so the same
   * family id under two majors yields two distinct ids. */
  idScope: string[];
  tabs: { id: string; label: string; count: number; hasSelection: boolean }[];
  activeId: string;
  onActivate: (id: string) => void;
  buttonClassName: string;
}) {
  function handleKeyDown(event: React.KeyboardEvent, index: number) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") {
      return;
    }
    event.preventDefault();
    const delta = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex = wrapIndex(index, delta, tabs.length);
    const next = tabs[nextIndex];
    if (next) {
      onActivate(next.id);
      const nextEl = document.getElementById(tabDomId(level, ...idScope, next.id));
      nextEl?.focus();
    }
  }

  return (
    <div role="tablist" aria-label={ariaLabel} className="flex flex-wrap gap-2">
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          id={tabDomId(level, ...idScope, tab.id)}
          role="tab"
          type="button"
          aria-selected={tab.id === activeId}
          aria-controls={CARD_PANEL_ID}
          tabIndex={tab.id === activeId ? 0 : -1}
          onClick={() => onActivate(tab.id)}
          onKeyDown={(event) => handleKeyDown(event, index)}
          className={buttonClassName}
        >
          {tab.label} <span className="text-parchment-200/60">({tab.count})</span>
          {tab.hasSelection ? <span className="ml-1 text-gold-500">· 1 selected</span> : null}
        </button>
      ))}
    </div>
  );
}

/** Shared by both tablists so they stay visually and behaviourally identical apart from padding. */
const TAB_BASE =
  "rounded border border-navy-800 text-sm aria-selected:border-gold-500 aria-selected:text-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500";

export function PolicyCardGrid({
  cards,
  selectedCardId,
  onSelectCard,
  onClearSelection,
}: {
  cards: readonly PolicyCard[];
  selectedCardId: string | null;
  /** Fires with the CARD only -- which route to apply (preserving the
   * player's prior route choice where the new card still offers it, per R5)
   * is a decision `chooseCardRoute` makes, one level up in DecisionsScreen,
   * which is also the only place that knows what the prior route was. */
  onSelectCard: (card: PolicyCard) => void;
  onClearSelection: () => void;
}) {
  const majors = groupPolicyCards(cards);
  const located = selectedCardId ? locateCard(majors, selectedCardId) : null;

  const [openMajor, setOpenMajor] = useState<MajorChoiceId>(located?.major ?? "budget");
  const [openFamily, setOpenFamily] = useState<FamilyId | null>(located?.family ?? null);

  const selectedCard = selectedCardId
    ? cards.find((card) => card.card_id === selectedCardId)
    : undefined;

  const activeMajor = majors.find((major) => major.id === openMajor)!;
  const effectiveFamily =
    activeMajor.families.find((family) => family.id === openFamily) ?? activeMajor.families[0];

  function handleMajorChange(id: string) {
    const major = majors.find((candidate) => candidate.id === id);
    if (!major) return;
    setOpenMajor(major.id);
    setOpenFamily(major.families[0]?.id ?? null);
  }

  const visibleCards = activeMajor.id === "restraint" ? activeMajor.cards : (effectiveFamily?.cards ?? []);

  // The family the SELECTED card belongs to, not necessarily the family the
  // browser currently has open (the player may select a card and then
  // navigate elsewhere while it stays selected) -- and only shown when it
  // says something the category label alone did not (taxation/spending
  // family labels currently equal their category label; constitution's four
  // families do not).
  const selectedCardFamilyLabel = located?.family
    ? (majors.flatMap((major) => major.families).find((family) => family.id === located.family)
        ?.label ?? null)
    : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-gold-600 bg-navy-900 p-3">
        {selectedCard ? (
          <div className="text-sm">
            <p className="text-parchment-200/60">
              {selectedCard.category_label}
              {selectedCardFamilyLabel && selectedCardFamilyLabel !== selectedCard.category_label
                ? ` · ${selectedCardFamilyLabel}`
                : ""}
            </p>
            <p className="text-parchment-100">{selectedCard.title}</p>
          </div>
        ) : (
          <EmptyNote>No policy selected yet.</EmptyNote>
        )}
        {selectedCard ? (
          <button
            type="button"
            onClick={onClearSelection}
            className="rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Clear
          </button>
        ) : null}
      </div>

      {/* Level 1 now goes through the SAME `TabList` as level 2, which is the other half of the A8
          fix. Before, this list was hand-rolled: its tabs carried no `id`, no `aria-controls`, no
          roving tabindex and no arrow-key handling, so it was a `role="tablist"` whose tabs
          controlled nothing and could not be operated as a tablist. One component now guarantees
          both lists resolve their references and behave the same from the keyboard. */}
      <TabList
        ariaLabel="Policy choice"
        level="major"
        idScope={[]}
        tabs={majors.map((major) => ({
          id: major.id,
          label: major.label,
          count: major.cards.length,
          hasSelection: located?.major === major.id,
        }))}
        activeId={openMajor}
        onActivate={handleMajorChange}
        buttonClassName={`${TAB_BASE} px-3 py-2`}
      />

      {activeMajor.families.length > 0 ? (
        <TabList
          ariaLabel={activeMajor.label}
          level="family"
          idScope={[activeMajor.id]}
          tabs={activeMajor.families.map((family) => ({
            id: family.id,
            label: family.label,
            count: family.cards.length,
            hasSelection: located?.major === activeMajor.id && located.family === family.id,
          }))}
          activeId={effectiveFamily?.id ?? ""}
          onActivate={(id) => setOpenFamily(id as FamilyId)}
          buttonClassName={`${TAB_BASE} px-3 py-1.5`}
        />
      ) : null}

      {/* The panel id is UNCONDITIONAL now. It used to be omitted when a major had no families,
          which left the tabs of that major pointing `aria-controls` at nothing at all — the same
          dangling-reference class as A8 itself. `aria-labelledby` names the deepest active tab, which
          is the family tab when one exists and the major tab otherwise. */}
      <div
        role="tabpanel"
        id={CARD_PANEL_ID}
        aria-labelledby={
          activeMajor.families.length > 0 && effectiveFamily !== undefined
            ? tabDomId("family", activeMajor.id, effectiveFamily.id)
            : tabDomId("major", activeMajor.id)
        }
      >
        {visibleCards.length === 0 ? (
          <EmptyNote>No cards in this group.</EmptyNote>
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {visibleCards.map((card) => (
              <PolicyCardView
                key={card.card_id}
                card={card}
                selected={card.card_id === selectedCardId}
                onSelect={() => onSelectCard(card)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
