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
import { stagedCountText } from "../format/format";
import { useDraftStore } from "../state/draft";
import { stagedActions } from "../state/stagedActions";
import { SessionProvider, useSession } from "../state/SessionContext";
import { INITIAL_SCREEN, SCREENS, screenById, type ScreenDefinition } from "./registry";
import { GlossaryScreen, WIN_AND_LOSS_LINE, glossaryDefinition } from "./screens/GlossaryScreen";
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
          {/* Gate 4A3 UX-3 (U1): "Capital 500 / 1,000" meant nothing to a new player. The Glossary's
              own definition is the tooltip and the accessible description, quoted, not restated. */}
          <span
            data-testid="capital-meter"
            title={glossaryDefinition("Political capital")}
            aria-description={glossaryDefinition("Political capital")}
          >
            Capital {data.political_capital.display}
          </span>
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

/** Economy, Legislature and Constitution: the screens that show a summary card and nothing more. */
const SUMMARY_SCREENS: ReadonlySet<ScreenId> = new Set<ScreenId>(["economy", "legislature", "constitution"]);

type NavGroup =
  | { kind: "screen"; entry: ScreenDefinition }
  | { kind: "summaries"; entries: ScreenDefinition[] };

/** The registry in its own order, with the summary screens gathered at the position of the first. */
function navGroups(screens: readonly ScreenDefinition[]): NavGroup[] {
  const groups: NavGroup[] = [];
  const summaries: ScreenDefinition[] = [];
  for (const entry of screens) {
    if (SUMMARY_SCREENS.has(entry.id)) {
      if (summaries.length === 0) groups.push({ kind: "summaries", entries: summaries });
      summaries.push(entry);
    } else {
      groups.push({ kind: "screen", entry });
    }
  }
  return groups;
}

function GreyboxShell() {
  const [screenId, setScreenId] = useState<ScreenId>(INITIAL_SCREEN);
  const { revision } = useSession();
  const dismissedHelp = useDraftStore((state) => state.dismissedHelp);
  const dismissHelp = useDraftStore((state) => state.dismissHelp);
  const setHelpDismissed = useDraftStore((state) => state.setHelpDismissed);
  const glossaryOpen = useDraftStore((state) => state.glossaryOpen);
  const setGlossaryOpen = useDraftStore((state) => state.setGlossaryOpen);

  const screen = screenById(screenId);
  const ScreenComponent = screen.component;
  const stagedCount = useDraftStore((state) => stagedActions(state).length);

  function navItem(entry: ScreenDefinition) {
    const disabled = (entry.requiresActiveGame ?? false) && revision === null;
    // Gate 4A3 UX-4b: what is staged, counted by `stagedActions` -- the same list "This turn's
    // draft" and the resolve confirmation read. A description, not part of the name, so the control
    // is still called "Decisions" by every screen reader and every test.
    const stagedNote = entry.id === "decisions" && stagedCount > 0 ? stagedCountText(stagedCount) : null;
    return (
      <li key={entry.id}>
        <button
          type="button"
          aria-describedby={stagedNote === null ? undefined : "nav-staged-count"}
          aria-current={entry.id === screenId ? "page" : undefined}
          disabled={disabled}
          // Gate 4A3 UX-3: this said "…to view the strategic map." on Government and Relationships
          // too -- every screen that needs a campaign shared the Strategic map's sentence.
          title={disabled ? `Load or start a game to view the ${entry.label.toLowerCase()}.` : undefined}
          onClick={disabled ? undefined : () => setScreenId(entry.id)}
          className="w-full rounded border border-navy-800 px-3 py-2 text-left text-sm aria-[current=page]:border-gold-500 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
        >
          {entry.label}
        </button>
        {stagedNote === null ? null : (
          <span
            id="nav-staged-count"
            data-testid="staged-count"
            className="mt-1 block px-1 text-xs text-parchment-200/80"
          >
            · {stagedNote}
          </span>
        )}
      </li>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Gate 4A3 Commit 3, findings A2-A7 and A10-A15: THE SITE BANNER.
          The twelve landmark findings are A2-A7 and A10-A15. They are NOT a contiguous A2-A15 range:
          A8 is the `aria-valid-attr-value` tab defect and A9 is a `color-contrast` defect, both fixed
          separately, and sweeping them into the range would claim this one change fixed them.
          This bar was a plain `<div>`, so the product title and the connection line sat outside every
          landmark — one of the two nodes axe reported on all twelve surfaces. A top-level `<header>`
          is the `banner` landmark, which is what this bar actually is. `NationalHeader` below was
          converted from `<header>` to a named `<section>` in the same change, because two top-level
          `<header>` elements would be two banners and would trade one violation for another. */}
      {/* `flex-wrap` on the HEADER, added with the second control: at the 320px conformance width the
          title block plus two side-by-side controls need ~347px, so the page began scrolling
          horizontally -- caught by `verify:fixes`'s V1-V3 assertion on the very first run after the
          toggle was added. Wrapping the control group onto its own line is the fix; shrinking the
          controls instead would have made them narrower than their own labels. */}
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-navy-800 bg-navy-950 px-6 py-2">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl tracking-wide text-parchment-100">
            MANDATE
          </h1>
          <p className="text-xs text-parchment-200/60">
            Connected to the local MANDATE server.
          </p>
        </div>
        {/* Gate 4A3 Commit 4: the introduction was DISMISSIBLE AND NOTHING ELSE -- once closed it
            could not be recalled for the rest of the session, so the one place the game explains
            itself was a single-use resource. This toggle makes it recallable, and deliberately
            reuses the `aria-expanded` pattern the Glossary control beside it already uses, so the
            header has one convention rather than two. `aria-expanded` is the negation of the stored
            flag because the note being OPEN is that flag being false. */}
        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            aria-expanded={!dismissedHelp}
            onClick={() => setHelpDismissed(!dismissedHelp)}
            className="rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            How to govern
          </button>
          <button
            type="button"
            aria-expanded={glossaryOpen}
            onClick={() => setGlossaryOpen(!glossaryOpen)}
            className="rounded border border-navy-800 px-3 py-1 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
          >
            {glossaryOpen ? "Close glossary" : "Glossary"}
          </button>
        </div>
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
          {/* THIS SENTENCE WAS WRONG, not merely thin, and that is why Gate 4A3 Commit 4 replaces
              it rather than extending it. It read "build one decision", which teaches the wrong
              model of a turn: a turn combines a policy proposal with appointments, bargains,
              assistance requests, promises and movement orders. A player told they build ONE
              decision would not look for the rest.

              The one-budget-or-amendment limit is NOT stated here. It governs the policy proposal
              alone, and `DecisionsScreen`'s own panel is where it is stated -- putting it in a
              general introduction would imply the limit governs the whole turn, which is the same
              misstatement moved to a different screen. */}
          <p>
            Review your country, prepare your actions, preview their consequences, resolve the turn,
            and read what happened.
          </p>
          <p className="mt-2">
            Dashboard shows the country&apos;s condition. Government, Relationships and Strategic
            map are where you appoint people, deal with them, and move formations. Decisions is
            where you assemble the turn and resolve it, and Turn result and History are where you
            read what your choices did.
          </p>
          <p data-testid="win-and-loss" className="mt-2">
            {WIN_AND_LOSS_LINE}
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
            {/* Gate 4A3 UX-3 (U10): Economy, Legislature and Constitution have no full screen in this
                version; each shows the Dashboard's summary card for its topic. A visible
                "Summaries" caption says so before the player clicks. The registry's order is
                unchanged, and so is every control's accessible name. */}
            {navGroups(SCREENS).map((group) =>
              group.kind === "summaries" ? (
                <li key="summaries" className="flex w-full flex-col gap-2">
                  <span
                    id="nav-summaries"
                    className="px-1 pt-1 text-xs uppercase tracking-wide text-parchment-200/70"
                  >
                    Summaries
                  </span>
                  <ul aria-labelledby="nav-summaries" className="flex flex-wrap gap-2 lg:flex-col">
                    {group.entries.map(navItem)}
                  </ul>
                </li>
              ) : (
                navItem(group.entry)
              ),
            )}
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
