/**
 * Phase 0/1 placeholder shell. There is no API to call yet (Phase 4) and no
 * gameplay screens yet (Phase 5) — this page says so rather than presenting
 * any UI element that looks functional but isn't (product spec §5.7,
 * "no placeholder feature claims").
 */
export function App() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="font-[family-name:var(--font-display)] text-4xl tracking-wide text-parchment-100">
        MANDATE
      </h1>
      <p className="max-w-md text-sm text-parchment-200/80">
        Frontend scaffold only — no gameplay screens exist yet. See{" "}
        <code>docs/roadmap.md</code> for current phase status.
      </p>
    </main>
  );
}
