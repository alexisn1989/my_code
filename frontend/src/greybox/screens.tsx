/**
 * Gate 4A0 greybox — the twelve planned screens, rendered from the static
 * fixture only.
 *
 * Every screen:
 *   - reads fields from `GREYBOX_FIXTURE` and renders them as given;
 *   - performs NO simulation arithmetic of any kind;
 *   - tolerates optional or absent data rather than crashing;
 *   - has exactly one meaningful heading.
 *
 * There is no `fetch`, no backend import, and no network access anywhere in this
 * file or its siblings. Nothing here resolves a turn — the Decisions screen's
 * Resolve control is deliberately inert and says so.
 */

import { useState } from "react";

import { DataTable, EmptyNote, Panel, RatioBar, ToneValue } from "./components";
import type { GreyboxFixture, ScreenId, TerminalSummary } from "./contract";
import { TurnResultView } from "./TurnResultView";

export interface ScreenProps {
  fixture: GreyboxFixture;
  navigate: (screen: ScreenId) => void;
}

export function TitleScreen({ fixture, navigate }: ScreenProps) {
  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        New campaign
      </h2>

      <div className="grid gap-4 md:grid-cols-3">
        {fixture.scenarios.map((scenario) => (
          <Panel key={scenario.scenarioId} title={scenario.displayName}>
            <dl className="flex flex-col gap-1 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-parchment-200/70">Government</dt>
                <dd>{scenario.governmentForm}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-parchment-200/70">Elections</dt>
                <dd>{scenario.electionIntervalLabel}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-parchment-200/70">Legitimacy</dt>
                <dd className="tabular-nums">{scenario.startingLegitimacyText}</dd>
              </div>
            </dl>
            <p className="mt-3 text-sm text-parchment-200/80">{scenario.pitch}</p>
            {scenario.isShowcase ? (
              <p className="mt-2 text-xs text-gold-500">Recommended starting scenario</p>
            ) : null}
            <button
              type="button"
              onClick={() => navigate("dashboard")}
              className="mt-3 rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
            >
              Start {scenario.displayName}
            </button>
          </Panel>
        ))}
      </div>

      <Panel title="Load a saved campaign">
        {fixture.saves.length === 0 ? (
          <EmptyNote>No saved campaigns yet.</EmptyNote>
        ) : (
          <DataTable
            caption="Saved campaigns"
            columns={["Name", "Scenario", "Turn", "Status"]}
            rows={fixture.saves.map((save) => ({
              key: save.saveId,
              cells: [
                save.displayName,
                save.scenarioId,
                save.currentTurn,
                save.loadable ? (
                  (save.terminalOutcomeSummary ?? "Playable")
                ) : (
                  <ToneValue key="p" tone="negative">
                    {save.integrityProblem ?? "Not loadable"}
                  </ToneValue>
                ),
              ],
            }))}
          />
        )}
      </Panel>
    </div>
  );
}

export function DashboardScreen({ fixture, navigate }: ScreenProps) {
  const { dashboard } = fixture;
  const concerns = [
    dashboard.concerns.money,
    dashboard.concerns.legitimacy,
    dashboard.concerns.legislature,
    dashboard.concerns.constitution,
    dashboard.concerns.survival,
  ];

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        National dashboard
      </h2>

      <Panel title="Your current priority">
        <p>{dashboard.goal.headline}</p>
        {dashboard.goal.detail ? (
          <p className="mt-1 text-sm text-parchment-200/70">{dashboard.goal.detail}</p>
        ) : null}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <Panel title={dashboard.countryName}>
          <div
            data-testid="map-placeholder"
            role="img"
            aria-label={`Stylised outline of ${dashboard.countryName}. Presentation only.`}
            className="flex h-48 items-center justify-center rounded border border-dashed border-navy-800 bg-navy-950 text-parchment-200/40"
          >
            map placeholder
          </div>
          <p className="mt-2 text-xs text-parchment-200/60">{dashboard.map.note}</p>
          <p className="mt-1 text-xs text-parchment-200/60">
            Presentation only — tinted by {dashboard.map.tintMetricLabel}.
          </p>
        </Panel>

        <Panel title="Alerts">
          {dashboard.alerts.length === 0 ? (
            <EmptyNote>Nothing needs your attention this turn.</EmptyNote>
          ) : (
            <ul className="flex flex-col gap-3">
              {dashboard.alerts.map((alert) => (
                <li key={alert.id} className="text-sm">
                  <span className="uppercase tracking-wide text-xs text-parchment-200/60">
                    {alert.severity}
                  </span>
                  <p>{alert.headline}</p>
                  {alert.detail ? (
                    <p className="text-parchment-200/70">{alert.detail}</p>
                  ) : null}
                  {alert.screen ? (
                    <button
                      type="button"
                      onClick={() => navigate(alert.screen as ScreenId)}
                      className="mt-1 text-xs underline focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                    >
                      Open
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div data-testid="concern-cards" className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
        {concerns.map((concern) => (
          <Panel key={concern.label} title={concern.label}>
            <p className="text-xl tabular-nums">
              <ToneValue tone={concern.tone}>{concern.headline}</ToneValue>
            </p>
            {concern.deltaText ? (
              <p className="mt-1 text-xs text-parchment-200/70">{concern.deltaText}</p>
            ) : null}
            <button
              type="button"
              onClick={() => navigate(concern.detailScreen)}
              className="mt-2 text-xs underline focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
            >
              Details
            </button>
          </Panel>
        ))}
      </div>
    </div>
  );
}

export function GovernmentScreen({ fixture }: ScreenProps) {
  const { government } = fixture;
  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Government
      </h2>

      <Panel title="The executive">
        <dl className="flex flex-col gap-1 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-parchment-200/70">Office</dt>
            <dd>{government.executiveLabel}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-parchment-200/70">Selection</dt>
            <dd>{government.selectionLabel}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-parchment-200/70">Term limit</dt>
            <dd>{government.termLimitLabel}</dd>
          </div>
        </dl>
      </Panel>

      <Panel title="Survival">
        <p className="mb-3 text-sm">{government.survivalHeadline}</p>
        <DataTable
          caption="Survival risks"
          columns={["Risk", "Value"]}
          rows={government.riskRows.map((row) => ({
            key: row.label,
            cells: [row.label, <ToneValue key="v" tone={row.tone}>{row.valueText}</ToneValue>],
          }))}
        />
      </Panel>

      <Panel title="Institutions">
        <DataTable
          caption="Institutional standing"
          columns={["Institution", "Loyalty", "Power", "Competence", "Corruption"]}
          rows={government.institutions.map((row) => ({
            key: row.label,
            cells: [
              row.label,
              row.loyaltyText,
              row.powerText,
              row.competenceText,
              row.corruptionText,
            ],
          }))}
        />
      </Panel>
    </div>
  );
}

export function EconomyScreen({ fixture }: ScreenProps) {
  const { economy } = fixture;
  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Economy &amp; budget
      </h2>

      <Panel title="Treasury">
        <p className="text-2xl tabular-nums">{economy.treasuryText}</p>
        <p className="mt-1 text-sm">
          <ToneValue tone={economy.balanceDirection === "down" ? "negative" : "positive"}>
            Balance this turn: {economy.balanceText}
          </ToneValue>
        </p>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Revenue">
          <DataTable
            caption="Revenue by category"
            columns={["Category", "Amount"]}
            rows={economy.revenue.map((line) => ({
              key: line.label,
              cells: [line.label, line.valueText],
            }))}
          />
        </Panel>
        <Panel title="Spending">
          <DataTable
            caption="Spending by category"
            columns={["Category", "Amount"]}
            rows={economy.spending.map((line) => ({
              key: line.label,
              cells: [line.label, line.valueText],
            }))}
          />
        </Panel>
      </div>
    </div>
  );
}

export function LegislatureScreen({ fixture }: ScreenProps) {
  const { legislature } = fixture;
  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Legislature
      </h2>

      {legislature.chambers.map((chamber) => (
        <Panel key={chamber.chamberId} title={chamber.displayName}>
          <DataTable
            caption={`${chamber.displayName} composition`}
            columns={["Measure", "Seats"]}
            rows={[
              { key: "total", cells: ["Total seats", chamber.totalSeats] },
              { key: "gov", cells: ["Government", chamber.governmentSeats] },
              { key: "opp", cells: ["Opposition", chamber.oppositionSeats] },
              {
                key: "vote",
                cells: [
                  "Last vote: supporting of required",
                  chamber.supportingSeats === null || chamber.requiredSeats === null
                    ? "No vote recorded"
                    : `${chamber.supportingSeats} of ${chamber.requiredSeats} required`,
                ],
              },
            ]}
          />
        </Panel>
      ))}

      <Panel title="Blocs">
        <DataTable
          caption="Blocs by party"
          columns={["Bloc", "Seats", "Relationship", "Baseline", "Discipline"]}
          rows={legislature.blocs.map((bloc) => ({
            key: `${bloc.partyId}/${bloc.blocId}`,
            cells: [
              bloc.displayName,
              bloc.seats,
              bloc.relationshipText,
              bloc.baselineText,
              bloc.disciplineText,
            ],
          }))}
        />
      </Panel>
    </div>
  );
}

export function ConstitutionScreen({ fixture }: ScreenProps) {
  const { constitution } = fixture;
  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Constitution
      </h2>

      <Panel title="Amendment">
        <dl className="flex flex-col gap-1 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-parchment-200/70">Difficulty</dt>
            <dd>{constitution.amendmentDifficultyLabel}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-parchment-200/70">Threshold</dt>
            <dd>{constitution.thresholdText}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-parchment-200/70">Digest</dt>
            <dd>
              <code className="text-xs">{constitution.digestText}</code>
            </dd>
          </div>
        </dl>
      </Panel>

      <Panel title="Axes">
        <DataTable
          caption="Constitutional axes"
          columns={["Axis", "Current value", "Amendable"]}
          rows={constitution.axes.map((axis) => ({
            key: axis.axis,
            cells: [axis.axis, axis.currentLabel, axis.amendable ? "Yes" : "No"],
          }))}
        />
      </Panel>
    </div>
  );
}

export function RelationshipsScreen({ fixture }: ScreenProps) {
  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Relationships
      </h2>
      <Panel title="Current standing against authored baseline">
        {fixture.relationships.length === 0 ? (
          <EmptyNote>No seated blocs in this legislature.</EmptyNote>
        ) : (
          <DataTable
            caption="Bloc relationships"
            columns={["Bloc", "Current", "Baseline", "Seats"]}
            rows={fixture.relationships.map((bloc) => ({
              key: `${bloc.partyId}/${bloc.blocId}`,
              cells: [
                bloc.displayName,
                bloc.relationshipText,
                bloc.baselineText,
                bloc.seats,
              ],
            }))}
          />
        )}
      </Panel>
    </div>
  );
}

export function DecisionsScreen({ fixture }: ScreenProps) {
  const options = fixture.decisionOptions;
  const [selectedSlot, setSelectedSlot] = useState(options.policySlot.selected);

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Decision workspace
      </h2>

      <Panel title="Policy proposal (one per turn)">
        <p className="mb-3 text-sm text-parchment-200/70">
          A budget and a constitutional amendment occupy the same slot. Choosing one replaces the
          other.
        </p>
        <div role="radiogroup" aria-label="Policy proposal" className="flex gap-3">
          {options.policySlot.options.map((option) => (
            <button
              key={option.kind}
              type="button"
              role="radio"
              aria-checked={selectedSlot === option.kind}
              disabled={!option.available}
              onClick={() => setSelectedSlot(option.kind)}
              className="rounded border border-navy-800 px-3 py-2 text-sm aria-checked:border-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
            >
              {option.label}
            </button>
          ))}
        </div>

        {options.policySlot.options
          .filter((option) => option.kind === selectedSlot)
          .map((option) => (
            <div key={option.kind} className="mt-4">
              <h4 className="mb-2 text-sm text-parchment-200/70">Route</h4>
              <ul className="flex flex-col gap-1 text-sm">
                {option.routes
                  .filter((route) => route.available)
                  .map((route) => (
                    <li key={route.route}>
                      {route.route === "decree" ? "Decree" : "Legislative vote"} — {route.costText}
                    </li>
                  ))}
              </ul>
            </div>
          ))}
      </Panel>

      <Panel title="Relationship investment (separate slot)">
        <p className="mb-3 text-sm text-parchment-200/70">
          Investment is not part of the policy slot. It can be combined with either proposal, or made
          on its own.
        </p>
        {options.relationshipInvestment.blocs.length === 0 ? (
          <EmptyNote>No blocs are available to invest in.</EmptyNote>
        ) : (
          <DataTable
            caption="Blocs available for relationship investment"
            columns={["Bloc", "Current", "Baseline", "Per-turn range"]}
            rows={options.relationshipInvestment.blocs.map((bloc) => ({
              key: `${bloc.partyId}/${bloc.blocId}`,
              cells: [
                bloc.displayName,
                bloc.relationshipText,
                bloc.baselineText,
                `${options.relationshipInvestment.perBlocMin}–${options.relationshipInvestment.perBlocMax}`,
              ],
            }))}
          />
        )}
      </Panel>

      <Panel title="Affordability">
        <RatioBar
          label="Political capital committed"
          valueText={options.affordability.verdictText}
          ratioBps={options.affordability.committedRatioBps}
        />
        <p className="mt-2 text-sm">
          <ToneValue tone={options.affordability.affordable ? "positive" : "negative"}>
            {options.affordability.affordable ? "Affordable" : "Exceeds available capital"}
          </ToneValue>
        </p>
        <p className="mt-3 text-xs text-parchment-200/60">
          Greybox only — no turn can be resolved. This screen renders static fixture data and calls
          no API.
        </p>
      </Panel>
    </div>
  );
}

export function ResultScreen({ fixture }: ScreenProps) {
  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Turn result
      </h2>
      <TurnResultView result={fixture.turnResult} context="live" />
    </div>
  );
}

export function HistoryScreen({ fixture }: ScreenProps) {
  const turns = fixture.history.map((entry) => entry.turn);
  const [selectedTurn, setSelectedTurn] = useState<number | null>(turns[0] ?? null);
  const detail = selectedTurn === null ? undefined : fixture.historyDetail[selectedTurn];

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        History
      </h2>

      <Panel title="Timeline">
        {fixture.history.length === 0 ? (
          <EmptyNote>No turns have been resolved yet.</EmptyNote>
        ) : (
          <ul className="flex flex-col gap-2">
            {fixture.history.map((entry) => (
              <li key={entry.turn}>
                <button
                  type="button"
                  aria-pressed={selectedTurn === entry.turn}
                  onClick={() => setSelectedTurn(entry.turn)}
                  className="w-full rounded border border-navy-800 px-3 py-2 text-left text-sm aria-pressed:border-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                >
                  Turn {entry.turn} — {entry.outcomeLine}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {detail ? (
        <TurnResultView result={detail} context="history" />
      ) : (
        <Panel title="Turn detail">
          <EmptyNote>
            No stored detail for that turn in this fixture. Select another turn.
          </EmptyNote>
        </Panel>
      )}
    </div>
  );
}

function TerminalPanel({ outcome, title }: { outcome: TerminalSummary; title: string }) {
  return (
    <Panel title={title}>
      <p className="text-lg">
        <ToneValue tone={outcome.bucket === "victory" ? "positive" : "negative"}>
          {outcome.headline}
        </ToneValue>
      </p>
      <p className="mt-1 text-sm text-parchment-200/70">
        {outcome.bucket === "victory" ? "Victory" : "Defeat"} — {outcome.reasonLabel}, turn{" "}
        {outcome.turn}
      </p>
      <ul className="mt-3 flex list-disc flex-col gap-1 pl-5 text-sm">
        {outcome.retrospective.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </Panel>
  );
}

export function TerminalScreen({ fixture, navigate }: ScreenProps) {
  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Victory / defeat
      </h2>

      <TerminalPanel outcome={fixture.terminalOutcomes.seed77} title="At the authored seed (77)" />
      <TerminalPanel outcome={fixture.terminalOutcomes.seed0} title="At seed 0" />

      <Panel title="What you can do now">
        <p className="mb-3 text-sm text-parchment-200/70">
          The campaign is over. No further turn can be resolved.
        </p>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => navigate("title")}
            className="rounded border border-gold-600 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            New campaign
          </button>
          <button
            type="button"
            onClick={() => navigate("history")}
            className="rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Review history
          </button>
        </div>
      </Panel>
    </div>
  );
}

export function GlossaryScreen({ fixture }: ScreenProps) {
  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        Glossary
      </h2>
      <Panel title="Terms">
        {fixture.glossary.length === 0 ? (
          <EmptyNote>No glossary entries.</EmptyNote>
        ) : (
          <dl className="flex flex-col gap-3 text-sm">
            {fixture.glossary.map((entry) => (
              <div key={entry.term}>
                <dt className="text-parchment-100">{entry.term}</dt>
                <dd className="text-parchment-200/80">{entry.definition}</dd>
              </div>
            ))}
          </dl>
        )}
      </Panel>
    </div>
  );
}
