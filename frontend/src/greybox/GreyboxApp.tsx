/**
 * Gate 4A2 — the application shell, now live. Holds the current `ScreenId`
 * and renders the persistent national header from the real dashboard query
 * (`useDashboard`, keyed by `SessionContext`'s `revision`), the navigation
 * list, the dismissible help note, and the persistent chrome-level glossary
 * toggle -- all backed by `useDraftStore`'s UI-preference fields, never a
 * second, parallel piece of state.
 *
 * Glossary stays chrome-level per the frozen plan's §9 (see `registry.ts`'s
 * own docstring for the full citation): a toggle in the top bar, reachable
 * from every screen including Title, that opens an inline, non-blocking
 * panel without navigating away.
 */

import { useState } from "react";

import { useDashboard } from "../api/queries";
import { useDraftStore } from "../state/draft";
import { SessionProvider, useSession } from "../state/SessionContext";
import { INITIAL_SCREEN, SCREENS, screenById } from "./registry";
import { GlossaryScreen } from "./screens/GlossaryScreen";
import type { ScreenId } from "./types";

function NationalHeader() {
  const { revision } = useSession();
  const dashboard = useDashboard(revision);

  if (!dashboard.data) {
    return (
      <section
        aria-label="National status"
        data-testid="national-header"
        className="border-b border-navy-800 bg-navy-900 px-6 py-3"
      >
        <p role="status" aria-live="polite" className="text-sm text-parchment-200/60">
          Loading…
        </p>
      </section>
    );
  }

  const data = dashboard.data;
  const concerns = [
    data.concerns.money,
    data.concerns.legitimacy,
    data.concerns.legislature,
    data.concerns.constitution,
    data.concerns.survival,
  ];

  return (
    // A NAMED `<section>` is a `region` landmark, so this strip's content is inside a landmark while
    // the site banner above stays unique. The accessible name matters: an unnamed `<section>` is not a
    // landmark at all, which would reintroduce the very finding this change closes.
    <section
      aria-label="National status"
      data-testid="national-header"
      className="border-b border-navy-800 bg-navy-900 px-6 py-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <span className="font-[family-name:var(--font-display)] text-xl text-parchment-100">
            {data.country_name}
          </span>
          <span className="ml-3 text-sm text-parchment-200/70">{data.government_form}</span>
        </div>
        <div className="flex flex-wrap gap-4 text-sm tabular-nums">
          <span>Turn {data.turn}</span>
          <span>Election: {data.next_election_label}</span>
          <span>Capital {data.political_capital.display}</span>
        </div>
      </div>
      <ul className="mt-2 flex flex-wrap gap-4 text-xs text-parchment-200/80">
        {concerns.map((concern) => (
          <li key={concern.label}>
            <span className="text-parchment-200/60">{concern.label}:</span> {concern.headline}
          </li>
        ))}
      </ul>
    </section>
  );
}

function GreyboxShell() {
  const [screenId, setScreenId] = useState<ScreenId>(INITIAL_SCREEN);
  const { revision } = useSession();
  const dismissedHelp = useDraftStore((state) => state.dismissedHelp);
  const dismissHelp = useDraftStore((state) => state.dismissHelp);
  const glossaryOpen = useDraftStore((state) => state.glossaryOpen);
  const setGlossaryOpen = useDraftStore((state) => state.setGlossaryOpen);

  const screen = screenById(screenId);
  const ScreenComponent = screen.component;

  return (
    <div className="min-h-screen">
      {/* Gate 4A3 Commit 3, findings A2-A15: THE SITE BANNER.
          This bar was a plain `<div>`, so the product title and the connection line sat outside every
          landmark — one of the two nodes axe reported on all twelve surfaces. A top-level `<header>`
          is the `banner` landmark, which is what this bar actually is. `NationalHeader` below was
          converted from `<header>` to a named `<section>` in the same change, because two top-level
          `<header>` elements would be two banners and would trade one violation for another. */}
      <header className="flex items-start justify-between gap-4 border-b border-navy-800 bg-navy-950 px-6 py-2">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl tracking-wide text-parchment-100">
            MANDATE
          </h1>
          <p className="text-xs text-parchment-200/60">
            Connected to the local MANDATE server.
          </p>
        </div>
        <button
          type="button"
          aria-expanded={glossaryOpen}
          onClick={() => setGlossaryOpen(!glossaryOpen)}
          className="shrink-0 rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          {glossaryOpen ? "Close glossary" : "Glossary"}
        </button>
      </header>

      {glossaryOpen ? (
        <div role="region" aria-label="Glossary" className="border-b border-navy-800 px-6 py-4">
          <GlossaryScreen />
        </div>
      ) : null}

      {screen.showsGameplayChrome ? <NationalHeader /> : null}

      {dismissedHelp ? null : (
        // The SECOND node axe reported outside a landmark on every surface, and the cause is subtle:
        // `<aside>` maps to the `complementary` landmark on its own, but `role="note"` OVERRODE that
        // mapping, and `note` is not a landmark — so an explicit role intended to describe the content
        // silently removed it from the landmark structure. Dropping the role restores
        // `complementary`; the `aria-label` stays, because a named landmark is what makes it
        // navigable rather than merely present.
        <aside
          aria-label="How to govern"
          className="mx-6 mt-4 rounded border border-navy-800 bg-navy-900 p-4 text-sm"
        >
          <p>
            Read your country&apos;s condition, build one decision, resolve the turn, then read why
            it turned out that way. Repeat until victory or defeat.
          </p>
          <button
            type="button"
            onClick={dismissHelp}
            className="mt-2 rounded border border-navy-800 px-3 py-1 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            Dismiss
          </button>
        </aside>
      )}

      <div className="flex flex-col gap-6 px-6 py-6 lg:flex-row">
        <nav aria-label="Screens" className="lg:w-56 lg:shrink-0">
          <ul className="flex flex-wrap gap-2 lg:flex-col">
            {SCREENS.map((entry) => {
              const disabled = (entry.requiresActiveGame ?? false) && revision === null;
              return (
                <li key={entry.id}>
                  <button
                    type="button"
                    aria-current={entry.id === screenId ? "page" : undefined}
                    disabled={disabled}
                    title={disabled ? "Load or start a game to view the strategic map." : undefined}
                    onClick={disabled ? undefined : () => setScreenId(entry.id)}
                    className="w-full rounded border border-navy-800 px-3 py-2 text-left text-sm aria-[current=page]:border-gold-500 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
                  >
                    {entry.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <main className="min-w-0 flex-1">
          <ScreenComponent navigate={setScreenId} />
        </main>
      </div>
    </div>
  );
}

export function GreyboxApp() {
  return (
    <SessionProvider>
      <GreyboxShell />
    </SessionProvider>
  );
}
