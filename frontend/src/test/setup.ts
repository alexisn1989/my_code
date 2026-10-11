import "@testing-library/jest-dom/vitest";

import { afterEach } from "vitest";

import { usePreviewStore } from "../state/previewStore";

// Gate 4A3 M-2: the shared preview is a module-level store, so one test's estimate must not be read
// by the next.
afterEach(() => {
  usePreviewStore.getState().reset();
});
