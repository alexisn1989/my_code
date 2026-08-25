/**
 * Gate 4A3A (R9) — one policy card, in the accessible structure the mandate
 * requires: a native `disabled` button is not focusable, so the CARD
 * CONTAINER carries reachability (`role="group" tabIndex={0}`), never the
 * button alone. Availability and reason are announced via `aria-describedby`
 * on focus; the unavailable ACTION is disabled while the card stays
 * reachable; selection is conveyed by the button's TEXT and `aria-pressed`,
 * never colour alone.
 *
 * Every raw numeric effect value is formatted through `src/format/**`
 * (`formatBpsPercent`/`formatAmount`) -- this component performs no
 * arithmetic of its own. Enum effects (`unit === "enum"`) render the
 * server-authored `current_label`/`proposed_label` strings verbatim; there is
 * no numeric formatting to apply to those.
 */

import type { PolicyCard, PolicyCardEffect } from "../../api/client";
import { formatAmount, formatBpsPercent } from "../../format/format";
import { DIRECTION_GLYPH, DIRECTION_LABEL } from "../components";

function formatEffectSide(effect: PolicyCardEffect, side: "current" | "proposed"): string {
  if (effect.unit === "enum") {
    const label = side === "current" ? effect.current_label : effect.proposed_label;
    return label ?? "—";
  }
  const raw = side === "current" ? effect.current_value : effect.proposed_value;
  if (raw === null || raw === undefined) {
    return "—";
  }
  return effect.unit === "bps" ? formatBpsPercent(raw) : formatAmount(raw);
}

function EffectChip({ effect }: { effect: PolicyCardEffect }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs text-parchment-200/80">
      <span>{effect.label}</span>
      <span className="flex items-center gap-1 tabular-nums">
        {formatEffectSide(effect, "current")}
        <span aria-hidden="true">{DIRECTION_GLYPH[effect.direction]}</span>
        <span className="sr-only">{DIRECTION_LABEL[effect.direction]}</span>
        {formatEffectSide(effect, "proposed")}
      </span>
    </div>
  );
}

export function PolicyCardView({
  card,
  selected,
  onSelect,
}: {
  card: PolicyCard;
  selected: boolean;
  onSelect: () => void;
}) {
  const statusId = `policy-card-status-${card.card_id}`;
  const statusText = card.available ? "Available" : (card.unavailable_detail ?? "Unavailable");

  return (
    <li className="list-none">
      <div
        role="group"
        tabIndex={0}
        aria-label={card.title}
        aria-describedby={statusId}
        className="flex h-full flex-col gap-2 rounded border border-navy-800 bg-navy-900 p-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500 aria-[pressed=true]:border-gold-500"
      >
        <span className="text-[10px] uppercase tracking-wide text-parchment-200/50">
          {card.category_label}
        </span>
        <h4 className="font-[family-name:var(--font-display)] text-sm text-parchment-100">
          {card.title}
        </h4>
        <p className="text-xs text-parchment-200/70">{card.description}</p>

        {card.effects.length > 0 ? (
          <div className="flex flex-col gap-1 border-t border-navy-800 pt-2">
            {card.effects.map((effect, index) => (
              // eslint-disable-next-line react/no-array-index-key -- effects have no stable id of their own
              <EffectChip key={index} effect={effect} />
            ))}
          </div>
        ) : null}

        <p id={statusId} className="mt-auto text-xs text-parchment-200/60">
          {statusText}
        </p>

        <button
          type="button"
          aria-pressed={selected}
          disabled={!card.available}
          onClick={onSelect}
          className="rounded border border-navy-800 px-3 py-1 text-sm disabled:opacity-40 aria-pressed:border-gold-500 aria-pressed:text-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          {selected ? "Selected" : "Select"}
        </button>
      </div>
    </li>
  );
}
