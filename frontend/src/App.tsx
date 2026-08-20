/**
 * Phase 4A Gate 4A0 introduced this as an eleven-line placeholder saying no
 * gameplay screens existed; Gate 4A2 makes it live.
 *
 * The greybox now renders real projections from the local FastAPI process via
 * the generated contract (`src/api/schema.d.ts`) and React Query -- no
 * fixture, no client-side simulation arithmetic outside `src/format/`. It
 * imports no backend module directly; every value crosses the typed HTTP
 * client in `src/api/client.ts`.
 */
export { GreyboxApp as App } from "./greybox/GreyboxApp";
