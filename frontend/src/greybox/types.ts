/**
 * UI-only types that are NOT part of the API contract -- screen identity and
 * the two tiny display enums components key their styling on. `Tone` and
 * `Direction` happen to have the same string values the generated schema
 * uses for `ConcernCard.tone`/`.direction` etc., but they are declared here,
 * not imported from `../api/schema`, because they describe a UI concern
 * (which class to apply), not a server contract.
 */

export type Tone = "positive" | "negative" | "caution" | "neutral";
export type Direction = "up" | "down" | "unchanged";

/** The eleven navigable screens (frozen plan Sec 8.1) plus the chrome-level
 * Glossary, which `registry.ts` deliberately does not list as a navigation
 * entry -- see that file's own docstring. */
export type ScreenId =
  | "title"
  | "dashboard"
  | "government"
  | "economy"
  | "legislature"
  | "constitution"
  | "relationships"
  | "decisions"
  | "result"
  | "history"
  | "terminal"
  | "glossary";
