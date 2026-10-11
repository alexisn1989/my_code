/**
 * Gate 4A3 M-2: the one piece of counting the preview store needs. The format boundary
 * (`format-boundary.test.ts`) confines arithmetic to `src/format/`, so the store's request ids and
 * epochs advance through this rather than with `+ 1` in `src/state/`.
 */
export function nextCount(count: number): number {
  return count + 1;
}
