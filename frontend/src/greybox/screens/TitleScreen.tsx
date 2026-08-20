/**
 * Gate 4A2 — Title: real scenarios, real New Game, real Load. `pitch` (a
 * one-line hook) is deliberately dropped from Gate 4A0's mockup: the real
 * `ScenarioSummary` has no such field, and inventing one client-side would be
 * exactly the fabricated-copy problem this gate exists to avoid.
 */

import { useState } from "react";

import { useLoadGame, useNewGame, useSaves, useScenarios } from "../../api/queries";
import { useSession } from "../../state/SessionContext";
import { ErrorPanel } from "../../status/ErrorPanel";
import { LoadingPanel } from "../../status/StatusPanels";
import { DataTable, EmptyNote, Panel, ToneValue } from "../components";
import type { ScreenProps } from "../registry";

export function TitleScreen({ navigate }: ScreenProps) {
  const scenarios = useScenarios();
  const saves = useSaves();
  const newGame = useNewGame();
  const loadGame = useLoadGame();
  const { setRevision } = useSession();
  const [seedInput, setSeedInput] = useState("");

  function handleStart(scenarioId: string) {
    const seed = seedInput.trim() === "" ? undefined : Number(seedInput);
    newGame.mutate(
      { scenarioId, seed },
      {
        onSuccess: (dashboard) => {
          setRevision(dashboard.revision);
          navigate("dashboard");
        },
      },
    );
  }

  function handleLoad(saveId: string) {
    loadGame.mutate(
      { saveId },
      {
        onSuccess: (dashboard) => {
          setRevision(dashboard.revision);
          navigate("dashboard");
        },
        // On failure, this mutation writes nothing to the query cache (see
        // queries.ts), so the currently displayed game -- if any -- is left
        // exactly as it was. Only the error panel below changes.
      },
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="font-[family-name:var(--font-display)] text-2xl text-parchment-100">
        New campaign
      </h2>

      {newGame.isError ? <ErrorPanel error={newGame.error} /> : null}

      {scenarios.isPending ? <LoadingPanel label="Loading scenarios…" /> : null}
      {scenarios.isError ? <ErrorPanel error={scenarios.error} /> : null}
      {scenarios.isSuccess ? (
        scenarios.data.length === 0 ? (
          <EmptyNote>No scenarios are available.</EmptyNote>
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            {scenarios.data.map((scenario) => (
              <Panel key={scenario.scenario_id} title={scenario.display_name}>
                <dl className="flex flex-col gap-1 text-sm">
                  <div className="flex justify-between gap-4">
                    <dt className="text-parchment-200/70">Government</dt>
                    <dd>{scenario.government_form}</dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-parchment-200/70">Elections</dt>
                    <dd>{scenario.election_interval_label}</dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-parchment-200/70">Legitimacy</dt>
                    <dd className="tabular-nums">{scenario.starting_legitimacy_text}</dd>
                  </div>
                </dl>
                {scenario.is_showcase ? (
                  <p className="mt-2 text-xs text-gold-500">Recommended starting scenario</p>
                ) : null}
                <button
                  type="button"
                  disabled={newGame.isPending}
                  onClick={() => handleStart(scenario.scenario_id)}
                  className="mt-3 rounded border border-gold-600 px-3 py-1 text-sm disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                >
                  {newGame.isPending ? "Starting…" : `Start ${scenario.display_name}`}
                </button>
              </Panel>
            ))}
          </div>
        )
      ) : null}

      <Panel title="Optional seed (advanced)">
        <label className="flex flex-col gap-1 text-sm">
          <span>Seed override</span>
          <input
            type="number"
            value={seedInput}
            onChange={(event) => setSeedInput(event.target.value)}
            className="w-40 rounded border border-navy-800 bg-navy-950 px-2 py-1 text-parchment-100"
          />
        </label>
      </Panel>

      <Panel title="Load a saved campaign">
        {loadGame.isError ? <ErrorPanel error={loadGame.error} /> : null}
        {saves.isPending ? <LoadingPanel label="Loading saves…" /> : null}
        {saves.isError ? <ErrorPanel error={saves.error} /> : null}
        {saves.isSuccess ? (
          saves.data.length === 0 ? (
            <EmptyNote>No saved campaigns yet.</EmptyNote>
          ) : (
            <DataTable
              caption="Saved campaigns"
              columns={["Name", "Scenario", "Turn", "Status"]}
              rows={saves.data.map((save) => ({
                key: save.save_id,
                cells: [
                  save.loadable ? (
                    <button
                      key="load"
                      type="button"
                      disabled={loadGame.isPending}
                      onClick={() => handleLoad(save.save_id)}
                      className="underline disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                    >
                      {save.display_name}
                    </button>
                  ) : (
                    save.display_name
                  ),
                  save.scenario_id,
                  save.current_turn,
                  save.loadable ? (
                    (save.terminal_outcome_summary ?? "Playable")
                  ) : (
                    <ToneValue key="p" tone="negative">
                      {save.integrity_problem ?? "Not loadable"}
                    </ToneValue>
                  ),
                ],
              }))}
            />
          )
        ) : null}
      </Panel>
    </div>
  );
}
