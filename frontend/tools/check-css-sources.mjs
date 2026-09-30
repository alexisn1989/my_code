#!/usr/bin/env node
// Gate 4A3 Commit 6 -- keep Tailwind's candidate scan on SHIPPED source only.
//
// Tailwind v4 emits a utility for every word in its scanned files that happens to be a class name, and
// its automatic source detection scanned e2e specs, tools, JSON and test files as well as the app. Four
// commits shipped rules that no component uses because of it -- one of them 1.20 kB, from the English
// word "filter" in a spec comment -- and two of the dead rules were default-palette colours
// `check:palette` exists to forbid. `check:bundle` could not see any of it: it greps the shipped JS.
//
// The fix lives in src/styles/tokens.css: `@import "tailwindcss" source(none)` turns detection off,
// and explicit `@source` lines name what ships. This gate keeps it that way. It asserts:
//   1. the tailwindcss import carries `source(none)`;
//   2. at least one `@source` exists, and every non-negated one resolves inside src/ or is index.html;
//   3. test files are excluded by a `@source not` line.
// Node stdlib only, like the other tools here.

import { readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";

const root = join(import.meta.dirname, "..");
const cssPath = join(root, "src", "styles", "tokens.css");
// Remove CSS comments WITHOUT touching quoted strings. A recursive glob -- two stars, a slash, a
// star -- contains the characters of a comment opener and closer, so a naive regex strips the
// middle out of the @source pattern itself.
function stripComments(text) {
  let out = "";
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === '"' || ch === "'") {
      const end = text.indexOf(ch, i + 1);
      const stop = end === -1 ? text.length : end + 1;
      out += text.slice(i, stop);
      i = stop - 1;
    } else if (ch === "/" && text[i + 1] === "*") {
      const end = text.indexOf("*/", i + 2);
      i = end === -1 ? text.length : end + 1;
    } else {
      out += ch;
    }
  }
  return out;
}

const css = stripComments(readFileSync(cssPath, "utf8"));
const problems = [];

const imports = [...css.matchAll(/@import\s+"tailwindcss"([^;]*);/g)];
if (imports.length !== 1) {
  problems.push(`expected exactly one @import "tailwindcss", found ${imports.length}`);
} else if (!/\bsource\(\s*none\s*\)/.test(imports[0][1])) {
  problems.push('the tailwindcss import must carry source(none), or automatic detection scans everything');
}

const sources = [...css.matchAll(/@source\s+(not\s+)?"([^"]+)"\s*;/g)].map((m) => ({
  negated: Boolean(m[1]),
  pattern: m[2],
}));
const positive = sources.filter((s) => !s.negated);
if (positive.length === 0) problems.push("no @source line: the stylesheet would contain no utilities at all");

const srcDir = join(root, "src");
for (const { pattern } of positive) {
  const literalPrefix = pattern.split(/[*{]/)[0];
  const resolved = resolve(dirname(cssPath), literalPrefix);
  const rel = relative(root, resolved);
  const insideSrc = !relative(srcDir, resolved).startsWith("..");
  if (!(insideSrc || rel === "index.html")) {
    problems.push(`@source "${pattern}" reaches ${rel || "."}, which is neither under src/ nor index.html`);
  }
}

if (!sources.some((s) => s.negated && /\.test\./.test(s.pattern))) {
  problems.push('no @source not "...*.test.*" line: test files would be scanned');
}

if (problems.length > 0) {
  for (const problem of problems) console.error(`check-css-sources: ${problem}`);
  process.exit(1);
}
console.log(
  `check-css-sources: OK -- source(none), ${positive.length} shipped source pattern(s), ` +
    `${sources.length - positive.length} exclusion(s): ${sources.map((s) => (s.negated ? "not " : "") + s.pattern).join(", ")}`,
);
