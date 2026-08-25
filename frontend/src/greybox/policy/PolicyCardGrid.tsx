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

function firstAvailableRoute(card: PolicyCard) {
  return card.routes.find((route) => route.available) ?? null;
}

function TabList({
  ariaLabel,
  tabs,
  activeId,
  onActivate,
}: {
  ariaLabel: string;
  tabs: { id: string; label: string; count: number; hasSelection: boolean }[];
  activeId: string;
  onActivate: (id: string) => void;
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
      const nextEl = document.getElementById(`policy-tab-${ariaLabel}-${next.id}`);
      nextEl?.focus();
    }
  }

  return (
    <div role="tablist" aria-label={ariaLabel} className="flex flex-wrap gap-2">
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          id={`policy-tab-${ariaLabel}-${tab.id}`}
          role="tab"
          type="button"
          aria-selected={tab.id === activeId}
          aria-controls={`policy-panel-${ariaLabel}-${tab.id}`}
          tabIndex={tab.id === activeId ? 0 : -1}
          onClick={() => onActivate(tab.id)}
          onKeyDown={(event) => handleKeyDown(event, index)}
          className="rounded border border-navy-800 px-3 py-1.5 text-sm aria-selected:border-gold-500 aria-selected:text-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          {tab.label} <span className="text-parchment-200/50">({tab.count})</span>
          {tab.hasSelection ? <span className="ml-1 text-gold-500">· 1 selected</span> : null}
        </button>
      ))}
    </div>
  );
}

export function PolicyCardGrid({
  cards,
  selectedCardId,
  onSelectCard,
  onClearSelection,
}: {
  cards: readonly PolicyCard[];
  selectedCardId: string | null;
  onSelectCard: (card: PolicyCard, route: NonNullable<ReturnType<typeof firstAvailableRoute>>) => void;
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

  function handleSelect(card: PolicyCard) {
    const route = firstAvailableRoute(card);
    if (route === null) {
      return; // an unavailable card's Select button is disabled; defensive only
    }
    onSelectCard(card, route);
  }

  const visibleCards = activeMajor.id === "restraint" ? activeMajor.cards : (effectiveFamily?.cards ?? []);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-gold-600 bg-navy-900 p-3">
        {selectedCard ? (
          <div className="text-sm">
            <p className="text-parchment-200/60">
              {selectedCard.category_label}
              {located?.family ? ` · ${effectiveFamily?.label ?? ""}` : ""}
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

      <div role="tablist" aria-label="Policy choice" className="flex flex-wrap gap-2">
        {majors.map((major) => (
          <button
            key={major.id}
            type="button"
            role="tab"
            aria-selected={major.id === openMajor}
            onClick={() => handleMajorChange(major.id)}
            className="rounded border border-navy-800 px-3 py-2 text-sm aria-selected:border-gold-500 aria-selected:text-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            {major.label} <span className="text-parchment-200/50">({major.cards.length})</span>
            {located?.major === major.id ? <span className="ml-1 text-gold-500">· 1 selected</span> : null}
          </button>
        ))}
      </div>

      {activeMajor.families.length > 0 ? (
        <TabList
          ariaLabel={activeMajor.label}
          tabs={activeMajor.families.map((family) => ({
            id: family.id,
            label: family.label,
            count: family.cards.length,
            hasSelection: located?.major === activeMajor.id && located.family === family.id,
          }))}
          activeId={effectiveFamily?.id ?? ""}
          onActivate={(id) => setOpenFamily(id as FamilyId)}
        />
      ) : null}

      <div
        role="tabpanel"
        id={
          activeMajor.families.length > 0
            ? `policy-panel-${activeMajor.label}-${effectiveFamily?.id ?? ""}`
            : undefined
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
                onSelect={() => handleSelect(card)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
