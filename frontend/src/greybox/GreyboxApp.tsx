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

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { useDashboard } from "../api/queries";
import { revealScrollLeft, scrollRoom, scrollStep } from "../format/countryMap";
import { stagedCountText } from "../format/format";
import { useDraftStore } from "../state/draft";
import { stagedActions } from "../state/stagedActions";
import { SessionProvider, useSession } from "../state/SessionContext";
import {
  INITIAL_SCREEN,
  SCREENS,
  screenById,
  type NavigateOptions,
  type ScreenDefinition,
} from "./registry";
import { GlossaryScreen, glossaryDefinition } from "./screens/GlossaryScreen";
import type { ScreenId } from "./types";

function NationalHeader({ screenId }: { screenId: ScreenId }) {
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
        {/* Gate 4A3 M-1: the status bar. Turn, treasury, capital, legitimacy and the next election,
            each with a small icon; the texts are the same server figures the header always showed. */}
        <div data-testid="status-bar" className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm tabular-nums sm:flex sm:flex-wrap sm:gap-x-4">
          <StatusItem icon="turn">
            <span>Turn {data.turn}</span>
          </StatusItem>
          <StatusItem icon="treasury">
            <span>
              <span className="sr-only sm:not-sr-only">Treasury </span>
              {data.concerns.money.headline}
            </span>
          </StatusItem>
          {/* Gate 4A3 UX-3 (U1): "Capital 500 / 1,000" meant nothing to a new player. The Glossary's
              own definition is the tooltip and the accessible description, quoted, not restated. */}
          <StatusItem icon="capital">
            <span
              data-testid="capital-meter"
              title={glossaryDefinition("Political capital")}
              aria-description={glossaryDefinition("Political capital")}
            >
              Capital {data.political_capital.display}
            </span>
          </StatusItem>
          <StatusItem icon="legitimacy">
            <span>
              <span className="sr-only sm:not-sr-only">Legitimacy </span>
              {data.concerns.legitimacy.headline}
            </span>
          </StatusItem>
          <StatusItem icon="election">
            <span>Election: {data.next_election_label}</span>
          </StatusItem>
        </div>
      </div>
      {/* Gate 4A3 victory path: on the Dashboard this one-line summary repeats the five concern
          cards on the same screen (and its wrapped rows pushed the campaign objective below a phone's
          first screen). Gate 4A3 M-1: with the status bar now carrying treasury and legitimacy, it is
          hidden on the Dashboard at every width; every other screen keeps it. The text stays in the
          DOM. */}
      <ul
        className={`mt-2 ${screenId === "dashboard" ? "hidden" : "flex"} flex-wrap gap-4 text-xs text-parchment-200/80`}
      >
        {concerns.map((concern) => (
          <li key={concern.label}>
            <span className="text-parchment-200/60">{concern.label}:</span> {concern.headline}
          </li>
        ))}
      </ul>
    </section>
  );
}

type StatusIconId = "turn" | "treasury" | "capital" | "legitimacy" | "election";

/** Gate 4A3 M-1: the status bar's small gold icons (original drawings; decorative). */
const STATUS_ICON: Record<StatusIconId, string> = {
  turn: "M5 2h10M5 18h10M6 2c0 5 8 5 8 8s-8 3-8 8M14 2c0 5-8 5-8 8",
  treasury: "M3 6c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3zM3 6v8c0 1.7 3.1 3 7 3s7-1.3 7-3V6M3 10c0 1.7 3.1 3 7 3s7-1.3 7-3",
  capital: "M10 3a7 7 0 1 0 0 14a7 7 0 1 0 0-14zM10 6l1.2 2.6 2.8.3-2.1 1.9.6 2.8L10 12.2 7.5 13.6l.6-2.8L6 8.9l2.8-.3z",
  legitimacy: "M10 17c-4-2-6-6-6-11M10 17c4-2 6-6 6-11M5 8 3 7M4.6 11H2.5M6.5 14l-1.8 1M15 8l2-1M15.4 11h2.1M13.5 14l1.8 1",
  election: "M3 8h14v9H3zM7 8V3h6v5M8 11h4",
};

function StatusItem({ icon, children }: { icon: StatusIconId; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false" className="h-4 w-4 shrink-0">
        <path d={STATUS_ICON[icon]} fill="none" stroke="var(--color-gold-500)" strokeWidth={1.4} strokeLinecap="round" />
      </svg>
      {children}
    </span>
  );
}

/** Economy: the screen that shows a summary card and nothing more. (Constitution left this group in
 * the Gate 4A3 victory path, and Legislature in M-2: both are full screens now.) */
const SUMMARY_SCREENS: ReadonlySet<ScreenId> = new Set<ScreenId>(["economy"]);

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

/** Gate 4A3 M-1: move focus to the main heading of the screen just opened. A screen may render a
 * loading panel first, so this waits (briefly) for the heading to appear. */
function focusMainHeading(main: HTMLElement | null): void {
  if (main === null) return;
  const tryFocus = (): boolean => {
    const heading = main.querySelector<HTMLElement>("h2");
    if (heading === null) return false;
    if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
    heading.focus();
    return true;
  };
  if (tryFocus()) return;
  const observer = new MutationObserver(() => {
    if (tryFocus()) observer.disconnect();
  });
  observer.observe(main, { childList: true, subtree: true });
  window.setTimeout(() => observer.disconnect(), 5000);
}

function GreyboxShell() {
  const [screenId, setScreenId] = useState<ScreenId>(INITIAL_SCREEN);
  const mainRef = useRef<HTMLElement | null>(null);
  const focusPending = useRef(false);
  const navigate = useCallback((id: ScreenId, options?: NavigateOptions) => {
    focusPending.current = options?.focusHeading === true;
    setScreenId(id);
  }, []);
  // Gate 4A3 M-1: the phone nav row's scroll affordances.
  const navRowRef = useRef<HTMLUListElement | null>(null);
  const [navRoom, setNavRoom] = useState({ left: false, right: false });
  const updateNavRoom = useCallback(() => {
    const row = navRowRef.current;
    if (row === null) return;
    const next = scrollRoom(row.scrollLeft, row.clientWidth, row.scrollWidth);
    setNavRoom((prev) => (prev.left === next.left && prev.right === next.right ? prev : next));
  }, []);
  const scrollNav = useCallback((direction: "left" | "right") => {
    const row = navRowRef.current;
    if (row === null) return;
    const step = scrollStep(row.clientWidth);
    row.scrollBy({ left: direction === "left" ? -step : step, behavior: "smooth" });
  }, []);
  useEffect(() => {
    const row = navRowRef.current;
    if (row === null) return;
    updateNavRoom();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(updateNavRoom);
    observer.observe(row);
    return () => observer.disconnect();
  }, [updateNavRoom]);
  useEffect(() => {
    // Keep the current screen's button in view in the phone row. The row's own scrollLeft is set, not
    // `scrollIntoView`: in Chromium that also moves the Tab starting point to the button, so the next
    // Tab after loading skipped the header and the introduction (Commit 4's traversal test).
    const row = navRowRef.current;
    const current = row?.querySelector<HTMLElement>('[aria-current="page"]');
    if (row !== null && row !== undefined && current !== null && current !== undefined) {
      const item = current.getBoundingClientRect();
      row.scrollLeft = revealScrollLeft(row.scrollLeft, row.clientWidth, row.getBoundingClientRect().left, item.left, item.right);
    }
    updateNavRoom();
  }, [screenId, updateNavRoom]);

  useEffect(() => {
    if (!focusPending.current) return;
    focusPending.current = false;
    focusMainHeading(mainRef.current);
  }, [screenId]);
  const { revision } = useSession();
  const dismissedHelp = useDraftStore((state) => state.dismissedHelp);
  const dismissHelp = useDraftStore((state) => state.dismissHelp);
  const setHelpDismissed = useDraftStore((state) => state.setHelpDismissed);
  const glossaryOpen = useDraftStore((state) => state.glossaryOpen);
  const setGlossaryOpen = useDraftStore((state) => state.setGlossaryOpen);

  const screen = screenById(screenId);
  const ScreenComponent = screen.component;
  const stagedCount = useDraftStore((state) => stagedActions(state).length);

  // Gate 4A3 UX-4c (U12), as ruled: on a phone the introduction was about 420 px tall at 390 px wide,
  // and with the nav beneath it the Dashboard's priority card began near y = 1,500. So when the app
  // FIRST LOADS below the `lg` breakpoint, the note starts closed. The header's "How to govern"
  // toggle reopens it, the choice is not persisted (testers may share a browser), and the priority
  // card itself carries the stakes line. Decided once, at mount: resizing later never re-closes a
  // note the player opened. Without `matchMedia` (jsdom) the screen is treated as wide.
  useLayoutEffect(() => {
    if (typeof window.matchMedia === "function" && !window.matchMedia("(min-width: 1024px)").matches) {
      setHelpDismissed(true);
    }
    // Mount only, by design: see above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function navItem(entry: ScreenDefinition) {
    const disabled = (entry.requiresActiveGame ?? false) && revision === null;
    // Gate 4A3 UX-4b: what is staged, counted by `stagedActions` -- the same list "This turn's
    // draft" and the resolve confirmation read. A description, not part of the name, so the control
    // is still called "Decisions" by every screen reader and every test.
    const stagedNote = entry.id === "decisions" && stagedCount > 0 ? stagedCountText(stagedCount) : null;
    return (
      <li key={entry.id} className="shrink-0">
        <button
          type="button"
          // A stable hook for measuring one nav control on its own (Gate 4A3 UX-4c, @ux4c).
          data-nav-screen={entry.id}
          aria-describedby={stagedNote === null ? undefined : "nav-staged-count"}
          aria-current={entry.id === screenId ? "page" : undefined}
          disabled={disabled}
          // Gate 4A3 UX-3: this said "…to view the strategic map." on Government and Relationships
          // too -- every screen that needs a campaign shared the Strategic map's sentence.
          title={disabled ? `Load or start a game to view the ${entry.label.toLowerCase()}.` : undefined}
          onClick={disabled ? undefined : () => setScreenId(entry.id)}
          // Gate 4A3 UX-4c (U12): in the one-row phone nav, Chrome scrolls a focused control into
          // view only when it is wholly hidden, so Tab could land on a button half off the edge.
          // "nearest" moves nothing that is already fully visible.
          onFocus={(event) => event.currentTarget.scrollIntoView?.({ block: "nearest", inline: "nearest" })}
          className="w-full whitespace-nowrap rounded border border-navy-800 px-3 py-2 text-left text-sm aria-[current=page]:border-gold-500 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500"
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

      {screen.showsGameplayChrome ? <NationalHeader screenId={screen.id} /> : null}

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
          {/* Gate 4A3 M-1: shortened. The map now shows where each kind of work is done, and the
              win-and-loss stakes are stated once, in the Dashboard's objective card (and in the
              Glossary), not repeated here. */}
          <p className="mt-2">
            On the Dashboard, each building in the capital opens the place where that work is done;
            Decisions is where you assemble the turn and resolve it.
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
          {/* Gate 4A3 UX-4c (U12): on a phone the nav is ONE horizontally scrollable row instead of
              six wrapped rows, so the screen's content starts high. Every button stays rendered,
              visible and reachable by Tab, which the browser specs rely on to navigate.
              Gate 4A3 M-1: players should not have to guess that more destinations exist. From `md`
              the buttons wrap, so all of them show; below `md` arrow buttons beside the row show whenever
              there is more to scroll to. (No fade is drawn over the row: it would sit on button text.) The arrows are a pointer aid only (hidden
              from assistive technology and out of the Tab order): keyboard users already reach every
              button by Tab, which scrolls it into view. */}
          <div className="flex items-center gap-1 md:block">
            {navRoom.left ? (
              <button
                type="button"
                aria-hidden="true"
                tabIndex={-1}
                data-nav-scroll="left"
                onClick={() => scrollNav("left")}
                className="grid h-11 w-11 shrink-0 place-items-center rounded border border-gold-600 bg-navy-900 text-lg text-parchment-100 md:hidden"
              >
                ‹
              </button>
            ) : null}
            <div className="relative min-w-0 flex-1">
          <ul
            ref={navRowRef}
            onScroll={updateNavRoom}
            data-testid="nav-row"
            className="flex gap-2 overflow-x-auto pb-1 md:flex-wrap md:overflow-visible lg:flex-col lg:pb-0"
          >
            {/* Gate 4A3 UX-3 (U10): Economy, Legislature and Constitution have no full screen in this
                version; each shows the Dashboard's summary card for its topic. A visible
                "Summaries" caption says so before the player clicks. The registry's order is
                unchanged, and so is every control's accessible name. */}
            {navGroups(SCREENS).map((group) =>
              group.kind === "summaries" ? (
                <li key="summaries" className="flex shrink-0 items-center gap-2 lg:w-full lg:flex-col lg:items-stretch">
                  <span
                    id="nav-summaries"
                    className="px-1 pt-1 text-xs uppercase tracking-wide text-parchment-200/70"
                  >
                    Summaries
                  </span>
                  <ul aria-labelledby="nav-summaries" className="flex gap-2 lg:flex-col">
                    {group.entries.map(navItem)}
                  </ul>
                </li>
              ) : (
                navItem(group.entry)
              ),
            )}
          </ul>
            </div>
            {navRoom.right ? (
              <button
                type="button"
                aria-hidden="true"
                tabIndex={-1}
                data-nav-scroll="right"
                onClick={() => scrollNav("right")}
                className="grid h-11 w-11 shrink-0 place-items-center rounded border border-gold-600 bg-navy-900 text-lg text-parchment-100 md:hidden"
              >
                ›
              </button>
            ) : null}
          </div>
        </nav>

        <main ref={mainRef} className="min-w-0 flex-1">
          <ScreenComponent navigate={navigate} />
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
