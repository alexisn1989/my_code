/**
 * Gate 4A3 victory path — the Constitution screen: the objective, the checklist of the engine's
 * three conditions, and links into the existing reform cards.
 *
 * It replaces the "Not in this version of the game" placeholder. Every value is a server field:
 * the objective (`DashboardProjection.objective`, derived from the engine's own predicates and
 * transition marker) and the card catalogue (`DecisionOptionsProjection.policy_cards`, for whether
 * a linked card is available right now and, if not, the card's own reason).
 *
 * A link REPLACES whatever policy proposal is drafted, exactly as selecting that card in Decisions
 * does -- it goes through the same handler there (`requestCard`, consumed by `DecisionsScreen`).
 * Nothing is merged. A link the server withholds (one that would leave the constitution unable to
 * qualify) is shown as its reason, not as a button.
 */

import type { PolicyCard } from "../../api/client";
import { useDashboard, useDecisionOptions } from "../../api/queries";
import { metText, VICTORY_NOTE } from "../../format/format";
import { useDraftStore } from "../../state/draft";
import { useSession } from "../../state/SessionContext";
import { ErrorPanel } from "../../status/ErrorPanel";
import { LoadingPanel } from "../../status/StatusPanels";
import { ConcernSummaries } from "../ConcernCards";
import { Panel } from "../components";
import { ObjectiveSummary } from "../ObjectivePanels";
import type { ScreenProps } from "../registry";

const BUTTON =
  "rounded border px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500";

export function ConstitutionScreen({ navigate }: ScreenProps) {
  const { revision } = useSession();
  const dashboard = useDashboard(revision, { enabled: revision !== null });
  const options = useDecisionOptions(revision, { enabled: revision !== null });
  const requestCard = useDraftStore((state) => state.requestCard);

  const heading = (
    <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
      Constitution
    </h2>
  );

  // The concern card a Dashboard "Details" link points here for is shown in every state, so the
  // link lands on what it was linked for even while the rest loads (Gate 4A3 UX-3, U10).
  const summaries = <ConcernSummaries screen="constitution" />;

  if (dashboard.isPending || options.isPending) {
    return (
      <div className="flex flex-col gap-6">
        {heading}
        {summaries}
        <LoadingPanel label="Loading the constitution…" />
      </div>
    );
  }
  if (dashboard.isError || options.isError) {
    const error = dashboard.error ?? options.error;
    return (
      <div className="flex flex-col gap-6">
        {heading}
        {summaries}
        <ErrorPanel
          error={error}
          onRefresh={() => {
            void dashboard.refetch();
            void options.refetch();
          }}
        />
      </div>
    );
  }

  const objective = dashboard.data.objective;
  const cards = new Map<string, PolicyCard>(
    options.data.policy_cards.map((card) => [card.card_id, card]),
  );

  function draft(cardId: string) {
    requestCard(cardId);
    navigate("decisions");
  }

  const qualifying = objective.qualifying_card_id ? cards.get(objective.qualifying_card_id) : undefined;

  return (
    <div className="flex flex-col gap-6">
      {heading}
      {summaries}

      <Panel title="Your campaign objective">
        <div className="flex flex-col gap-3">
          <ObjectiveSummary objective={objective} />
          {objective.qualifying_card_id ? (
            qualifying?.available ? (
              <div>
                <button
                  type="button"
                  data-testid="draft-qualifying-reform"
                  onClick={() => draft(objective.qualifying_card_id!)}
                  className={`${BUTTON} border-gold-600`}
                >
                  Draft the qualifying reform
                </button>
                <p className="mt-1 text-xs text-parchment-200/70">{qualifying.title}</p>
              </div>
            ) : (
              <p data-testid="qualifying-unavailable" className="text-sm text-parchment-200/80">
                The qualifying reform can&apos;t be drafted now
                {qualifying?.unavailable_detail ? `: ${qualifying.unavailable_detail}` : "."}
              </p>
            )
          ) : null}
        </div>
      </Panel>

      <Panel title="Constitutional conditions">
        <ul data-testid="constitution-checklist" className="flex flex-col gap-3">
          {objective.conditions.map((condition) => {
            const card = condition.link_card_id ? cards.get(condition.link_card_id) : undefined;
            return (
              <li
                key={condition.id}
                data-condition={condition.id}
                data-met={condition.met}
                className="rounded border border-navy-800 p-3 text-sm"
              >
                <p className="text-parchment-100">{condition.label}</p>
                <p className="text-parchment-200/80">
                  Current: <span className="text-parchment-100">{condition.current_text}</span>
                </p>
                <p>
                  <span className="text-parchment-200/70">Status:</span>{" "}
                  <span data-testid="condition-status" className="text-parchment-100">
                    {metText(condition.met)}
                  </span>
                </p>
                {condition.link_card_id ? (
                  card?.available ? (
                    <button
                      type="button"
                      onClick={() => draft(condition.link_card_id!)}
                      aria-label={`Draft this change on its own: ${condition.label}`}
                      className={`${BUTTON} mt-2 border-navy-800`}
                    >
                      Draft this change on its own
                    </button>
                  ) : (
                    <p className="mt-2 text-parchment-200/80">
                      Not available now
                      {card?.unavailable_detail ? `: ${card.unavailable_detail}` : "."}
                    </p>
                  )
                ) : null}
                {condition.note ? (
                  <p data-testid="condition-note" className="mt-2 text-parchment-200/80">
                    {condition.note}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
        {objective.ordering_note ? (
          <p data-testid="ordering-note" className="mt-3 text-sm text-parchment-200/80">
            {objective.ordering_note}
          </p>
        ) : null}
        <p className="mt-2 text-sm text-parchment-200/80">{VICTORY_NOTE}</p>
      </Panel>
    </div>
  );
}
