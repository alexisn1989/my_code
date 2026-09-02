/**
 * Strategic Military Map Gate M0 commit 7 — the accessible read-only
 * screen for `GET /api/game/map/strategic` (`useStrategicMap`,
 * `../../api/queries`). Still read-only, matching the frozen plan's §12:
 * selecting a theater queues nothing, matches no order, and implies no
 * movement -- there is no button, menu item, or form control anywhere on
 * this screen that mentions an order, a deployment, or a unit.
 *
 * The map is campaign-static content, not per-turn state, so it is keyed on
 * `useGameGeneration()` (bumped only when a game starts or loads) rather
 * than `revision` (which changes every turn and would cause a needless
 * refetch on every resolve).
 */

import { useEffect, useRef, useState } from "react";

import { useGameGeneration, useStrategicMap } from "../../api/queries";
import type { StrategicTheaterProjection } from "../../api/client";
import { useSession } from "../../state/SessionContext";
import { ErrorPanel } from "../../status/ErrorPanel";
import { LoadingPanel } from "../../status/StatusPanels";
import { EmptyNote, Panel } from "../components";
import type { ScreenProps } from "../registry";

const KIND_LABEL: Record<StrategicTheaterProjection["kind"], string> = {
  land: "Land",
  coastal: "Coastal",
};

function theaterListItemLabel(theater: StrategicTheaterProjection): string {
  return `${theater.display_name} — ${KIND_LABEL[theater.kind]}, ${theater.owner_display_name}${
    theater.is_capital ? ", capital" : ""
  }`;
}

export function StrategicMapScreen(_props: ScreenProps) {
  const { revision } = useSession();
  const generation = useGameGeneration();
  const map = useStrategicMap(generation.data, { enabled: revision !== null });
  const [selectedTheaterId, setSelectedTheaterId] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  // The loaded game changed (a new campaign started, or a different save
  // loaded) -- any previously selected theater id may no longer even exist
  // on the new map, so selection is cleared. Keyed on the SAME generation
  // value the query itself uses, so both invalidate together by
  // construction.
  useEffect(() => {
    setSelectedTheaterId(null);
  }, [generation.data]);

  if (map.isPending) {
    return <LoadingPanel label="Loading strategic map…" />;
  }
  if (map.isError) {
    return <ErrorPanel error={map.error} onRefresh={() => map.refetch()} />;
  }

  const data = map.data;
  const theatersById = new Map(data.theaters.map((theater) => [theater.theater_id, theater]));
  const selected = selectedTheaterId === null ? null : (theatersById.get(selectedTheaterId) ?? null);

  const outgoing = selected ? selected.outgoing_theater_ids.map((id) => theatersById.get(id)) : [];
  const incoming = selected ? selected.incoming_theater_ids.map((id) => theatersById.get(id)) : [];

  const announcement = selected
    ? `${selected.display_name}, ${selected.kind}, owned by ${selected.owner_display_name}, ${outgoing.length} routes out, ${incoming.length} routes in`
    : "";

  return (
    <div className="flex flex-col gap-6">
      <h2
        ref={headingRef}
        tabIndex={-1}
        className="font-[family-name:var(--font-display)] text-2xl text-parchment-100 focus:outline-none"
      >
        Strategic map
      </h2>

      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>

      <div className="flex flex-col gap-6 min-[900px]:flex-row">
        <div className="hidden min-[900px]:block min-[900px]:w-1/2 min-[900px]:shrink-0 rounded border border-navy-800 bg-navy-900 p-4 text-sm text-parchment-200/60">
          Map artwork is not part of this gate. The theater list beside it carries the complete,
          authoritative data.
        </div>

        <div className="flex flex-1 flex-col gap-6">
          <Panel title="Theaters">
            {data.theaters.length === 0 ? (
              <EmptyNote>This campaign has no theaters.</EmptyNote>
            ) : (
              <ul className="flex flex-col gap-2">
                {data.theaters.map((theater) => (
                  <li key={theater.theater_id}>
                    <button
                      type="button"
                      aria-pressed={selectedTheaterId === theater.theater_id}
                      onClick={() => setSelectedTheaterId(theater.theater_id)}
                      className="w-full rounded border border-navy-800 px-3 py-2 text-left text-sm aria-pressed:border-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                    >
                      {theaterListItemLabel(theater)}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          {selected ? (
            <Panel title={selected.display_name}>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-parchment-200/60">Kind</dt>
                <dd>{KIND_LABEL[selected.kind]}</dd>
                <dt className="text-parchment-200/60">Owner</dt>
                <dd>{selected.owner_display_name}</dd>
                <dt className="text-parchment-200/60">Capital</dt>
                <dd>{selected.is_capital ? "Yes" : "No"}</dd>
              </dl>

              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div>
                  <h4 className="mb-1 text-sm font-semibold text-parchment-100">Routes out</h4>
                  {outgoing.length === 0 ? (
                    <EmptyNote>No routes out.</EmptyNote>
                  ) : (
                    <ul className="text-sm">
                      {outgoing.map((theater, index) => (
                        // eslint-disable-next-line react/no-array-index-key -- ids may not resolve
                        <li key={theater?.theater_id ?? index}>
                          {theater?.display_name ?? selected.outgoing_theater_ids[index]}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div>
                  <h4 className="mb-1 text-sm font-semibold text-parchment-100">Routes in</h4>
                  {incoming.length === 0 ? (
                    <EmptyNote>No routes in.</EmptyNote>
                  ) : (
                    <ul className="text-sm">
                      {incoming.map((theater, index) => (
                        // eslint-disable-next-line react/no-array-index-key -- ids may not resolve
                        <li key={theater?.theater_id ?? index}>
                          {theater?.display_name ?? selected.incoming_theater_ids[index]}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </Panel>
          ) : (
            <Panel title="Theater detail">
              <EmptyNote>Select a theater to see its detail.</EmptyNote>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
