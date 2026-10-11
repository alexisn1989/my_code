/**
 * Gate 4A3 M-2 — the hook Decisions and Parliament use to read and run the shared preview.
 *
 * `run` sends the CURRENT draft and records the request in `usePreviewStore` under that draft's
 * signature; the view it returns is derived at render from the current draft, so an edit hides an
 * estimate (and its error, and its loading state) the moment it happens.
 */

import { api, type PreviewProjection } from "../api/client";
import { buildDecisions, previewRequestSignature } from "./buildDecisionSet";
import { useDraftStore } from "./draft";
import { previewView, usePreviewStore, type PreviewToken, type PreviewView } from "./previewStore";
import { useSession } from "./SessionContext";

export interface DraftPreview extends PreviewView {
  /** Sends the current draft; returns the request's token, or null with no campaign. */
  run: () => PreviewToken | null;
}

export function useDraftPreview(): DraftPreview {
  const draft = useDraftStore();
  const { revision, campaignId } = useSession();
  const store = usePreviewStore();
  const signature = previewRequestSignature(draft, revision, campaignId);
  const view = previewView(store, signature);

  function run(): PreviewToken | null {
    if (revision === null || campaignId === null) return null;
    const token = usePreviewStore.getState().begin(signature);
    api.preview(revision, campaignId, buildDecisions(draft)).then(
      (data: PreviewProjection) => {
        usePreviewStore.getState().accept(token, data);
      },
      (error: unknown) => {
        usePreviewStore.getState().fail(token, error instanceof Error ? error : new Error(String(error)));
      },
    );
    return token;
  }

  return { ...view, run };
}
