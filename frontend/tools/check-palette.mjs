#!/usr/bin/env node
/*
 * Gate 4A3 Commit 3 -- THE PALETTE BOUNDARY, and the contrast measurements that justify it.
 *
 * The frozen plan's F3 fix asks for "a boundary test asserting no component names a raw
 * default-palette colour". This is that check, plus two more rules the Commit 2 findings earned:
 *
 *   1. NO DEFAULT-PALETTE COLOUR. `text-emerald-300`, `bg-red-950` and friends come from Tailwind's
 *      stock palette, not MANDATE's. Nine such sites existed before this commit.
 *   2. NO TEXT ALPHA BELOW 60%. This is findings A1 and A9 expressed as a rule. Measured against the
 *      three navy backgrounds text actually sits on, `parchment-200` composited at 40% gives
 *      3.02-3.10:1 and at 50% gives 3.96-4.22:1 -- both under the 4.5:1 AA bar for normal text. At
 *      60% it is 5.06-5.57:1 and passes everywhere. So 60 is a MEASURED floor, not a taste: axe
 *      independently reported 3.09:1 for the 40% site and 4.16:1 for a 50% site, matching to two
 *      decimals.
 *   3. EVERY COLOUR TOKEN REFERENCED MUST EXIST. `bg-parchment-900/40` sat in `Portrait.tsx` and
 *      emitted nothing at all, because `parchment-900` is not a defined token -- a class that looks
 *      like a colour and silently is not. A token typo is invisible without this check.
 *
 * Rule 3 is deliberately about DEFINED-NESS, not contrast; rule 2 is deliberately about TEXT only. A
 * background or border alpha is a different question from text legibility, and conflating them would
 * either wave through unreadable text or forbid legitimate surface tints.
 *
 * WHY THIS IS A NODE GATE AND NOT A VITEST FILE -- measured, not assumed. `tokens.css` is the source
 * of truth for which tokens exist, and a vitest file CANNOT READ IT: Vite's CSS plugin empties `.css`
 * in the test transform, so both `import tokens from "./tokens.css?raw"` and the `import.meta.glob`
 * equivalent return an empty string (verified both ways). `tools/check-bundle.mjs` already records
 * the same conclusion for `dist/` -- file-content checks live in Node scripts here, partly so
 * `node:fs` never forces `@types/node` into a browser-only project.
 *
 * WHY IT PARSES INSTEAD OF GREPPING, which the first draft learned the hard way. A text scan over raw
 * source also matches PROSE: the first version failed because `Portrait.tsx` carries a comment
 * explaining which dead class was removed, and a regex cannot tell an explanation from a class name.
 * So this walks the real AST with the TypeScript compiler API and inspects only STRING LITERALS --
 * where class names actually live -- exactly as `src/format/format-boundary.test.ts` does for
 * arithmetic, reusing that same already-installed TS5 rather than adding a dependency.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";

// See the docstring: root `typescript` is a 7.x build whose CommonJS entry no longer exposes the
// Compiler API, so both boundary checks use the isolated tool package's TS5.
import ts from "./openapi-gen/node_modules/typescript/lib/typescript.js";

const SRC = join(process.cwd(), "src");
const TOKENS_CSS = join(SRC, "styles", "tokens.css");

/** Tailwind's stock palette families. MANDATE's own families are deliberately absent. */
const DEFAULT_PALETTE_FAMILIES = [
  "slate", "gray", "grey", "zinc", "neutral", "stone", "red", "orange", "amber", "yellow",
  "lime", "green", "emerald", "teal", "cyan", "sky", "blue", "indigo", "violet", "purple",
  "fuchsia", "pink", "rose",
];

const COLOUR_PROPERTIES =
  "(?:text|bg|border|ring|from|via|to|fill|stroke|divide|outline|shadow|accent|caret|decoration)";

/** Every application `.ts`/`.tsx` under `src/`. Test files may legitimately NAME a forbidden colour
 * while asserting its absence, so the rules apply to the application's own source. */
function applicationSources(dir = SRC, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      applicationSources(full, out);
    } else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Every string-literal value in a file, which is where a Tailwind class can actually take effect.
 *
 * Covers plain strings and all template-literal spans, because `className={`${BASE} px-3`}` is a
 * normal way to build a class list here (`PolicyCardGrid` does exactly that). Comments are invisible
 * to this walk by construction -- they are trivia, not nodes carrying text.
 */
function stringLiteralsOf(file) {
  const source = readFileSync(file, "utf-8");
  const sourceFile = ts.createSourceFile(
    file,
    source,
    ts.ScriptTarget.Latest,
    false,
    file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const out = [];
  const visit = (node) => {
    if (
      ts.isStringLiteral(node) ||
      ts.isNoSubstitutionTemplateLiteral(node) ||
      ts.isTemplateHead(node) ||
      ts.isTemplateMiddle(node) ||
      ts.isTemplateTail(node) ||
      ts.isJsxText(node)
    ) {
      out.push(node.text);
    }
    ts.forEachChild(node, visit);
  };
  ts.forEachChild(sourceFile, visit);
  return out;
}

const files = applicationSources();
const literalsByFile = files.map((file) => ({
  file: relative(process.cwd(), file),
  literals: stringLiteralsOf(file),
}));

const failures = [];

/** ANTI-VACUITY, first. A boundary check whose scan matched nothing would pass for the wrong reason,
 * which is the exact shape of defect Commit 1a was written to correct. */
const allLiterals = literalsByFile.flatMap((entry) => entry.literals);
if (literalsByFile.length < 20) {
  failures.push(`only ${literalsByFile.length} application sources parsed; the scan is not reaching src/`);
}
const parchmentTextClasses = allLiterals.filter((l) => l.includes("text-parchment-")).length;
if (parchmentTextClasses < 10) {
  failures.push(
    `found only ${parchmentTextClasses} parchment text classes; the rules below would be vacuous`,
  );
}
// And the walk must NOT see comment prose. `Portrait.tsx` explains a removed `bg-parchment-900/40`
// class in a comment, which is precisely the false positive that made the first draft fail.
if (allLiterals.some((l) => l.includes("used to be on the"))) {
  failures.push("comment prose reached the string-literal walk; rules would report explanations as defects");
}

/** Scan every application string literal. `describe` returns the failure text, or `null` when the
 * match is legitimate -- which rule 3 needs, since it matches every MANDATE token and only the
 * undefined ones are defects. */
function scan(pattern, describe) {
  for (const { file, literals } of literalsByFile) {
    for (const literal of literals) {
      for (const match of literal.matchAll(pattern)) {
        const problem = describe(match);
        if (problem !== null) failures.push(`${file}: ${problem}`);
      }
    }
  }
}

const tokensCss = readFileSync(TOKENS_CSS, "utf-8");
const defined = new Set([...tokensCss.matchAll(/--color-([a-z0-9-]+):/g)].map((m) => m[1]));
if (defined.size < 6) {
  failures.push(`tokens.css defines only ${defined.size} colour tokens; expected the MANDATE palette`);
}

/*
 * RULES 1 AND 3, in ONE pass over every colour utility -- and the two must be one pass, which the
 * first draft got wrong in an instructive way.
 *
 * Rule 1 was written as "flag any utility naming a Tailwind default family", which false-positived on
 * `accent-red-600`: `accent` is itself a Tailwind colour property, so the pattern read MANDATE's own
 * `accent-red` family as the property `accent` plus the stock family `red`. Checking DEFINED-NESS
 * FIRST removes that whole class of confusion -- a defined token is correct whatever its name looks
 * like -- and only then asks why an undefined one is undefined.
 *
 * (That false positive also exposed a wrong claim in tokens.css: `accent-red-600` and `charcoal-700`
 * are consumed as `var(--color-...)` SVG fills by the strategic map, not unused as an earlier comment
 * asserted. The check earned its place before guarding a single regression.)
 */
scan(
  // The `(?<!--color-)` guard keeps CSS custom-property references out of the Tailwind-utility scan.
  // `var(--color-accent-red-600)` (a real SVG fill on the strategic map) otherwise reads as the
  // property `accent` plus the stock family `red` -- the second false positive this rule produced, and
  // the reason the two syntaxes are now handled separately rather than by one pattern hoping to cover
  // both. Token references get their own rule immediately below, checked against the same source.
  new RegExp(`(?<!--color-)\\b${COLOUR_PROPERTIES}-([a-z][a-z-]*-[0-9]{2,3})(?:\\/[0-9]{1,3})?\\b`, "g"),
  (m) => {
    const token = m[1];
    if (defined.has(token)) return null;
    const family = token.replace(/-[0-9]+$/, "");
    if (DEFAULT_PALETTE_FAMILIES.includes(family)) {
      return `${m[0]} uses Tailwind's stock palette; add a MANDATE token with its measured contrast`;
    }
    return `${m[0]} names no --color-${token} in tokens.css, so Tailwind emits NO rule for it`;
  },
);

// RULE 3b -- `var(--color-X)` references are checked against the SAME source of truth. The strategic
// map paints its theatres this way rather than with utility classes, so without this rule a typo there
// would be exactly as invisible as `bg-parchment-900` was in `Portrait.tsx`.
scan(/var\(\s*--color-([a-z0-9-]+)\s*\)/g, (m) =>
  defined.has(m[1]) ? null : `var(--color-${m[1]}) names no token in tokens.css`,
);

// RULE 2 -- no text alpha below the measured 60% floor. A floor on the ALPHA rather than a contrast
// computation, because the alpha is what a component author types and so what the rule must be about.
scan(
  /\btext-parchment-[0-9]{3}\/([0-9]|[1-5][0-9])\b/g,
  (m) =>
    `${m[0]} is below the measured 4.5:1 floor (40% = 3.10:1, 50% = 4.16:1, 60% = 5.45:1 on navy-900); use /60 or higher`,
);

// RULE 4 -- the art bible's three status hues exist, plus the readable red. §13 requires one green,
// one amber and one neutral-blue; `danger` is the fourth, needed because `accent-red-600` measures
// 1.92:1 as text and cannot carry the negative tone.
for (const token of ["success-400", "warning-400", "info-400", "danger-400"]) {
  if (!tokensCss.includes(`--color-${token}:`)) {
    failures.push(`tokens.css must define --color-${token}`);
  }
}

// RULE 5 -- the measurements travel WITH the values. A colour without its measured ratio invites the
// next person to nudge it by eye, and then the evidence lives only in a commit message.
if (!/[0-9]+\.[0-9]+:1/.test(tokensCss) || !tokensCss.includes("navy-900")) {
  failures.push("tokens.css must record measured contrast ratios beside the tokens they justify");
}

if (failures.length > 0) {
  console.error("check-palette: FAILED");
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}

console.log(
  `check-palette: OK -- ${literalsByFile.length} source file(s), ${defined.size} colour token(s) defined, ` +
    `no default-palette colour, no sub-60 text alpha, every referenced token defined.`,
);
