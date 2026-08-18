/**
 * Phase 4A Gate 4A0. This was an eleven-line placeholder saying no gameplay
 * screens existed; it now renders the navigable greybox.
 *
 * The greybox is STATIC: it renders one frozen fixture, calls no API, imports no
 * backend module, and performs no simulation arithmetic. It exists to validate
 * the planned API contract (docs/contracts/phase4a-api-contract.yaml) before any
 * of it is implemented. Gate 4A2 onward replaces the fixture with real
 * projections from the local FastAPI process.
 */
export { GreyboxApp as App } from "./greybox/GreyboxApp";
