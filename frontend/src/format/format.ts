/**
 * `src/format/` -- the ONLY place display arithmetic may occur (frozen plan
 * Sec 14.1 / R9, T-format-boundary). Every function here converts an
 * ALREADY-COMPUTED server value into a display string or a purely visual
 * ratio; nothing here decides a game outcome, sums a vote, or derives a cost
 * the server has not already returned as a number.
 *
 * Guarded structurally by `src/format/format-boundary.test.ts`, which walks
 * every other source file's real TypeScript AST and fails on an arithmetic
 * `BinaryExpression` outside this directory and test files.
 */

/** `12345` (bps) -> "123.45%". Mirrors the backend's own
 * `format_bps_percent` (backend/app/api/projections.py) so a raw bps field
 * the backend did not pre-format (e.g. a decision-options bound) displays
 * identically to one it did. */
export function formatBpsPercent(valueBps: number): string {
  const whole = Math.trunc(valueBps / 100);
  const fraction = Math.abs(valueBps % 100)
    .toString()
    .padStart(2, "0");
  return `${whole}.${fraction}%`;
}

/** A ratio already expressed in basis points (0..10_000) -> a CSS width
 * percentage. Used for bar width ONLY, exactly like the greybox's existing
 * `RatioBar` -- the authoritative text next to the bar always comes from its
 * own separate, already-formatted field. */
export function ratioBpsToWidthPercent(ratioBps: number): string {
  return `${ratioBps / 100}%`;
}

/** Thousands-grouped, no invented currency symbol (the engine has none
 * either -- `StrictMoney` is a bare non-negative integer). */
export function formatAmount(amount: number): string {
  return amount.toLocaleString("en-US");
}

/** "500 / 1,000" -- the same shape `CapitalSummary.display` already uses
 * server-side, applied to fields the server returns as bare numbers instead
 * (e.g. a `ChamberPreview`'s `supporting_seats`/`total_seats`, or a
 * decision-options relationship-investment range). */
export function formatFraction(current: number, of: number): string {
  return `${formatAmount(current)} / ${formatAmount(of)}`;
}

/** A committed-vs-opening capital pair -> "120 of 500 committed". Composes
 * two already-server-provided integers into one sentence; performs no
 * simulation logic (affordability itself is still the server's `affordable`
 * boolean, never re-derived here). */
export function formatCommitted(committed: number, opening: number): string {
  return `${formatAmount(committed)} of ${formatAmount(opening)} committed`;
}
