/**
 * Gate 4A0 greybox — the application shell.
 *
 * Holds the current `ScreenId`, renders the persistent national header on
 * gameplay screens, the navigation list, the dismissible help note, and the
 * selected screen. Everything it displays comes from one frozen fixture.
 *
 * This shell calls no API and computes no simulation value. It exists to answer
 * one question before Gate 4A1 writes any backend code: can the planned contract
 * express every screen without a client-side calculation?
 */

import { useState } from "react";

import type { ScreenId } from "./contract";
import { GREYBOX_FIXTURE } from "./fixture";
import { INITIAL_SCREEN, SCREENS, screenById } from "./registry";

function NationalHeader() {
  const { dashboard } = GREYBOX_FIXTURE;
  const concerns = [
    dashboard.concerns.money,
    dashboard.concerns.legitimacy,
    dashboard.concerns.legislature,
    dashboard.concerns.constitution,
    dashboard.concerns.survival,
  ];

  return (
    <header
      data-testid="national-header"
      className="border-b border-navy-800 bg-navy-900 px-6 py-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <span className="font-[family-name:var(--font-display)] text-xl text-parchment-100">
            {dashboard.countryName}
          </span>
          <span className="ml-3 text-sm text-parchment-200/70">{dashboard.governmentForm}</span>
        </div>
        <div className="flex flex-wrap gap-4 text-sm tabular-nums">
          <span>Turn {dashboard.turn}</span>
          <span>Election: {dashboard.nextElectionLabel}</span>
          <span>Capital {dashboard.politicalCapital.display}</span>
        </div>
      </div>
      <ul className="mt-2 flex flex-wrap gap-4 text-xs text-parchment-200/80">
        {concerns.map((concern) => (
          <li key={concern.label}>
            <span className="text-parchment-200/60">{concern.label}:</span> {concern.headline}
          </li>
        ))}
      </ul>
    </header>
  );
}

export function GreyboxApp() {
  const [screenId, setScreenId] = useState<ScreenId>(INITIAL_SCREEN);
  const [helpDismissed, setHelpDismissed] = useState(false);

  const screen = screenById(screenId);
  const ScreenComponent = screen.component;

  return (
    <div className="min-h-screen">
      <div className="border-b border-navy-800 bg-navy-950 px-6 py-2">
        <h1 className="font-[family-name:var(--font-display)] text-2xl tracking-wide text-parchment-100">
          MANDATE
        </h1>
        <p className="text-xs text-parchment-200/60">
          Greybox — static fixture data. No turn has been resolved and no API exists yet.
        </p>
      </div>

      {screen.showsGameplayChrome ? <NationalHeader /> : null}

      {helpDismissed ? null : (
        <aside
          role="note"
          aria-label="How to govern"
          className="mx-6 mt-4 rounded border border-navy-800 bg-navy-900 p-4 text-sm"
        >
          <p>
            Read your country&apos;s condition, build one decision, resolve the turn, then read why
            it turned out that way. Repeat until victory or defeat.
          </p>
          <button
            type="button"
            onClick={() => setHelpDismissed(true)}
            className="mt-2 rounded border border-navy-800 px-3 py-1 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Dismiss
          </button>
        </aside>
      )}

      <div className="flex flex-col gap-6 px-6 py-6 lg:flex-row">
        <nav aria-label="Screens" className="lg:w-56 lg:shrink-0">
          <ul className="flex flex-wrap gap-2 lg:flex-col">
            {SCREENS.map((entry) => (
              <li key={entry.id}>
                <button
                  type="button"
                  aria-current={entry.id === screenId ? "page" : undefined}
                  onClick={() => setScreenId(entry.id)}
                  className="w-full rounded border border-navy-800 px-3 py-2 text-left text-sm aria-[current=page]:border-gold-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                >
                  {entry.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <main className="min-w-0 flex-1">
          <ScreenComponent fixture={GREYBOX_FIXTURE} navigate={setScreenId} />
        </main>
      </div>
    </div>
  );
}
