/**
 * Gate 4A2 — every mapped error `type` produces the specific class its
 * caller can `instanceof`-check, and everything else falls back to the
 * shared `ApiError` rather than throwing during error handling itself.
 */

import { describe, expect, it } from "vitest";

import {
  ApiError,
  DecisionRejectedError,
  GameConcludedError,
  NetworkError,
  NoActiveSessionError,
  ResolutionInProgressError,
  StaleRevisionError,
  apiErrorFromBody,
  apiErrorFromUnknown,
  type ProblemBody,
} from "./errors";

function problem(overrides: Partial<ProblemBody>): ProblemBody {
  return {
    type: "internal_error",
    title: "Something failed",
    status: 500,
    detail: null,
    fields: [],
    extra: {},
    ...overrides,
  };
}

describe("apiErrorFromBody: dedicated classes per mapped type", () => {
  it("stale_revision -> StaleRevisionError, carrying expected/actual", () => {
    const error = apiErrorFromBody(
      problem({
        type: "stale_revision",
        status: 409,
        extra: { expected: "2.2", actual: "1.1" },
      }),
    );
    expect(error).toBeInstanceOf(StaleRevisionError);
    expect(error).toBeInstanceOf(ApiError);
    if (error instanceof StaleRevisionError) {
      expect(error.expected).toBe("2.2");
      expect(error.actual).toBe("1.1");
    }
  });

  it("resolution_in_progress -> ResolutionInProgressError", () => {
    const error = apiErrorFromBody(problem({ type: "resolution_in_progress", status: 409 }));
    expect(error).toBeInstanceOf(ResolutionInProgressError);
  });

  it("decision_rejected -> DecisionRejectedError, carrying fields", () => {
    const error = apiErrorFromBody(
      problem({
        type: "decision_rejected",
        status: 422,
        fields: [{ path: "decisions[0].route", message: "invalid" }],
      }),
    );
    expect(error).toBeInstanceOf(DecisionRejectedError);
    if (error instanceof DecisionRejectedError) {
      expect(error.fields).toEqual([{ path: "decisions[0].route", message: "invalid" }]);
    }
  });

  it("no_active_session -> NoActiveSessionError", () => {
    const error = apiErrorFromBody(problem({ type: "no_active_session", status: 404 }));
    expect(error).toBeInstanceOf(NoActiveSessionError);
  });

  it("game_concluded -> GameConcludedError", () => {
    const error = apiErrorFromBody(problem({ type: "game_concluded", status: 409 }));
    expect(error).toBeInstanceOf(GameConcludedError);
  });

  it("an unmapped type falls back to the shared ApiError, not a crash", () => {
    const error = apiErrorFromBody(problem({ type: "save_incompatible", status: 409 }));
    expect(error).toBeInstanceOf(ApiError);
    expect(error).not.toBeInstanceOf(StaleRevisionError);
    expect(error.type).toBe("save_incompatible");
  });
});

describe("apiErrorFromUnknown: malformed or non-problem responses", () => {
  it("wraps a well-formed problem body", () => {
    const error = apiErrorFromUnknown(422, problem({ type: "decision_rejected", status: 422 }));
    expect(error).toBeInstanceOf(DecisionRejectedError);
  });

  it("does not throw on a response that is not a problem body at all", () => {
    const error = apiErrorFromUnknown(502, "<html>bad gateway</html>");
    expect(error).toBeInstanceOf(ApiError);
    expect(error.type).toBe("internal_error");
  });

  it("does not throw on null", () => {
    const error = apiErrorFromUnknown(500, null);
    expect(error).toBeInstanceOf(ApiError);
  });
});

describe("NetworkError", () => {
  it("is distinct from every ApiError subclass", () => {
    const error = new NetworkError(new TypeError("fetch failed"));
    expect(error).not.toBeInstanceOf(ApiError);
    expect(error.message).toContain("could not reach");
  });
});
