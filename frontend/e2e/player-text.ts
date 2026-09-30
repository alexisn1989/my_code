/**
 * What a player can read, gathered from the RENDERED page -- the in-browser half of the
 * no-raw-identifier rule that `check:copy` enforces over source.
 *
 * `document.body.textContent` alone is not enough, for two opposite reasons. It misses every
 * player-visible ATTRIBUTE (`aria-label`, `title`, `placeholder`, `alt`, `aria-description`), which
 * are exactly the strings a screen-reader user hears and a sighted user never sees; and it includes
 * text that is never rendered (`display:none` subtrees, `<script>`/`<style>` bodies). So the text
 * half reads `document.body.innerText` -- rendered text only, which still includes `.sr-only` text,
 * since that is read aloud -- and the named attributes are read separately.
 *
 * Finding T1 (Gate 4A3 Commit 5) is the reason this exists: the terminal screen rendered the engine
 * identifier `term_limit_exit`, and no source-level gate could see a string that only arrives at
 * runtime.
 */
import type { Page } from "@playwright/test";

const PLAYER_VISIBLE_ATTRIBUTES = ["aria-label", "aria-description", "title", "placeholder", "alt"];

export interface IdentifierLeak {
  identifier: string;
  where: "text" | "attribute";
  context: string;
}

export async function findIdentifierLeaks(
  page: Page,
  identifiers: readonly string[],
): Promise<IdentifierLeak[]> {
  return page.evaluate(
    ({ ids, attrs }) => {
      const leaks: { identifier: string; where: "text" | "attribute"; context: string }[] = [];
      const text = document.body.innerText;
      for (const id of ids) {
        const at = text.indexOf(id);
        if (at >= 0) {
          leaks.push({ identifier: id, where: "text", context: text.slice(Math.max(0, at - 40), at + 60) });
        }
      }
      for (const el of Array.from(document.body.querySelectorAll("*"))) {
        for (const attr of attrs) {
          const value = el.getAttribute(attr);
          if (value === null) continue;
          for (const id of ids) {
            if (value.includes(id)) {
              leaks.push({ identifier: id, where: "attribute", context: `${el.tagName}[${attr}="${value}"]` });
            }
          }
        }
      }
      return leaks;
    },
    { ids: [...identifiers], attrs: PLAYER_VISIBLE_ATTRIBUTES },
  );
}
