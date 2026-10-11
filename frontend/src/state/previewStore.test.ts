/**
 * Gate 4A3 M-2: the shared preview store's rules, checked directly.
 *
 * - only the latest request of the current epoch may write (out-of-order, lifecycle);
 * - result, error and loading state each belong to the signature they were requested for;
 * - the latest attempt for a draft decides what is shown (the retry-display rule).
 */

import { describe, expect, it } from "vitest";

import type { PreviewProjection } from "../api/client";
import { previewView, usePreviewStore } from "./previewStore";

const A = "sig-A";
const B = "sig-B";
const DATA_A = { route: "legislative", chambers: [], tag: "A" } as unknown as PreviewProjection;
const DATA_B = { route: "legislative", chambers: [], tag: "B" } as unknown as PreviewProjection;

const store = () => usePreviewStore.getState();
const view = (signature: string) => previewView(store(), signature);

describe("only the latest request of the current epoch writes", () => {
  it("keeps B when an older A lands after it", () => {
    const a = store().begin(A);
    const b = store().begin(B);
    expect(store().accept(b, DATA_B)).toBe(true);
    expect(store().accept(a, DATA_A)).toBe(false);
    expect(view(B).current).toBe(DATA_B);
    // ...and B is current only while the draft is B's.
    expect(view(A).current).toBeNull();
    expect(view(A).stale).toBe(true);
  });

  it("drops a response requested before invalidate, whatever its timing", () => {
    const a = store().begin(A);
    store().invalidate();
    expect(store().accept(a, DATA_A)).toBe(false);
    expect(store().fail(a, new Error("late"))).toBe(false);
    expect(view(A)).toMatchObject({ current: null, stale: false, pendingForDraft: false, errorForDraft: null });
  });

  it("invalidate clears an accepted result", () => {
    const a = store().begin(A);
    store().accept(a, DATA_A);
    store().invalidate();
    expect(view(A).current).toBeNull();
  });
});

describe("result, error and loading belong to their signature", () => {
  it("shows no loading and no error against a different draft", () => {
    const a = store().begin(A);
    expect(view(A).pendingForDraft).toBe(true);
    expect(view(B).pendingForDraft).toBe(false);
    store().fail(a, new Error("boom"));
    expect(view(A).errorForDraft?.message).toBe("boom");
    expect(view(B).errorForDraft).toBeNull();
  });

  it("an undo shows the same result again", () => {
    const a = store().begin(A);
    store().accept(a, DATA_A);
    expect(view(B).current).toBeNull();
    expect(view(A).current).toBe(DATA_A);
  });
});

describe("the retry-display rule: the latest attempt for a draft decides", () => {
  it("(a) a retry hides the old error at once, and its success shows with no error", () => {
    const first = store().begin(A);
    store().fail(first, new Error("first failed"));
    expect(view(A).errorForDraft).not.toBeNull();
    const retry = store().begin(A);
    expect(view(A)).toMatchObject({ errorForDraft: null, pendingForDraft: true });
    store().accept(retry, DATA_A);
    expect(view(A)).toMatchObject({ current: DATA_A, errorForDraft: null, pendingForDraft: false });
  });

  it("(b) a failed retry hides the older result for the same draft", () => {
    const first = store().begin(A);
    store().accept(first, DATA_A);
    const retry = store().begin(A);
    // While the retry is pending, the earlier result for the same request stays visible.
    expect(view(A).current).toBe(DATA_A);
    store().fail(retry, new Error("retry failed"));
    expect(view(A).current).toBeNull();
    expect(view(A).errorForDraft?.message).toBe("retry failed");
  });

  it("(c) a failure for an edited-away draft never shows against the new one", () => {
    const first = store().begin(A);
    store().fail(first, new Error("A failed"));
    const next = store().begin(B);
    expect(view(B).errorForDraft).toBeNull();
    store().accept(next, DATA_B);
    expect(view(B)).toMatchObject({ current: DATA_B, errorForDraft: null });
  });
});
