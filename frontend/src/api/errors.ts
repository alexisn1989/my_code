/**
 * Structured API errors, keyed on the problem-JSON `type` the backend always
 * returns (`backend/app/api/errors.py`). Hand-written, not generated: FastAPI's
 * OpenAPI output only declares SUCCESS response models (`app.openapi()` has no
 * visibility into `problem_response()`'s raw `JSONResponse` bodies), so the
 * error envelope's shape is a stable, documented contract (frozen plan Sec
 * 14.2) rather than something `openapi-typescript` can generate.
 *
 * One class per error `type` the mandate calls out for distinct handling
 * (`stale_revision`, `resolution_in_progress`, `decision_rejected`), plus one
 * shared class for every other mapped `type`, plus a `NetworkError` for the
 * case where `fetch` itself never reached the server. Every caller can
 * `instanceof`-check the specific classes it cares about and fall through to
 * `ApiError` for the rest -- never a bare string comparison scattered through
 * component code.
 */

/** The one problem-JSON shape every backend failure uses. */
export interface ProblemBody {
  type: string;
  title: string;
  status: number;
  detail: string | null;
  fields: { path: string; message: string }[];
  extra: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly type: string;
  readonly status: number;
  readonly detail: string | null;
  readonly fields: { path: string; message: string }[];
  readonly extra: Record<string, unknown>;

  constructor(body: ProblemBody) {
    super(body.detail ?? body.title);
    this.name = "ApiError";
    this.type = body.type;
    this.status = body.status;
    this.detail = body.detail;
    this.fields = body.fields;
    this.extra = body.extra;
  }
}

/** `409 stale_revision` -- another tab/session advanced the game past the
 * revision this request was built against. `extra` carries `expected`/`actual`. */
export class StaleRevisionError extends ApiError {
  readonly expected: string;
  readonly actual: string;

  constructor(body: ProblemBody) {
    super(body);
    this.name = "StaleRevisionError";
    this.expected = String(body.extra["expected"] ?? "");
    this.actual = String(body.extra["actual"] ?? "");
  }
}

/** `409 resolution_in_progress` -- a mutation is already in flight for this
 * session. Never queue a retry automatically; let the caller decide. */
export class ResolutionInProgressError extends ApiError {
  constructor(body: ProblemBody) {
    super(body);
    this.name = "ResolutionInProgressError";
  }
}

/** `422 decision_rejected` -- the engine's own reject-not-normalize validators
 * refused the submitted decision set. `fields` names which part, when the
 * rejection is field-scoped (a schema violation) rather than set-scoped (a
 * semantic rule like mutual exclusion). */
export class DecisionRejectedError extends ApiError {
  constructor(body: ProblemBody) {
    super(body);
    this.name = "DecisionRejectedError";
  }
}

/** `404 no_active_session` -- no game is loaded in this process. */
export class NoActiveSessionError extends ApiError {
  constructor(body: ProblemBody) {
    super(body);
    this.name = "NoActiveSessionError";
  }
}

/** `409 game_concluded` -- a terminal outcome is already set; no further turn
 * may be resolved. `extra` carries `bucket`/`reason`/`turn`. */
export class GameConcludedError extends ApiError {
  constructor(body: ProblemBody) {
    super(body);
    this.name = "GameConcludedError";
  }
}

/** The request never reached the server at all -- `fetch` itself threw
 * (`mandate-gui` not running, network unreachable). Distinct from every
 * `ApiError` subclass, which all require an actual HTTP response. */
export class NetworkError extends Error {
  readonly cause: unknown;

  constructor(cause: unknown) {
    super("could not reach the local MANDATE server");
    this.name = "NetworkError";
    this.cause = cause;
  }
}

/** Builds the specific subclass for a `type`, falling back to the shared
 * `ApiError` for every mapped type that has no dedicated class above. */
export function apiErrorFromBody(body: ProblemBody): ApiError {
  switch (body.type) {
    case "stale_revision":
      return new StaleRevisionError(body);
    case "resolution_in_progress":
      return new ResolutionInProgressError(body);
    case "decision_rejected":
      return new DecisionRejectedError(body);
    case "no_active_session":
      return new NoActiveSessionError(body);
    case "game_concluded":
      return new GameConcludedError(body);
    default:
      return new ApiError(body);
  }
}

/** A response body that failed to parse as JSON, or parsed but does not match
 * the problem shape -- an unexpected server failure, not a modelled one. */
export function apiErrorFromUnknown(status: number, raw: unknown): ApiError {
  if (
    raw !== null &&
    typeof raw === "object" &&
    "type" in raw &&
    "title" in raw &&
    "status" in raw
  ) {
    return apiErrorFromBody(raw as ProblemBody);
  }
  return new ApiError({
    type: "internal_error",
    title: "Unexpected response",
    status,
    detail: "the server returned a response that did not match the expected error shape",
    fields: [],
    extra: {},
  });
}
