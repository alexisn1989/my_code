#!/usr/bin/env node
/*
 * Gate 4A3 Commit 4 -- THE COPY BOUNDARY. No build vocabulary in player-visible text.
 *
 * WHY THIS EXISTS. Five player-visible strings spoke in the vocabulary of the build rather than of
 * the game: a panel titled "Not available in this gate" (a gate is a development milestone), two
 * notes saying content is "projected so far", and a sentence describing the policy proposal as a
 * "slot", which is a field name. Commit 4 reworded them. This check is what stops them coming back,
 * and what stops the next one being added.
 *
 * WHAT IT PROVES, STATED EXACTLY -- because the honest scope of a source scanner is narrower than it
 * looks, and overstating it is how F4's premise went wrong. F4 claimed "only 3 transition/animate
 * usages exist" from a text grep; all three turned out to be substring false positives inside
 * identifiers, and the application had no animation at all. So this check names its inspected set
 * rather than saying "the source":
 *
 *   1. JSX TEXT NODES -- the words between tags. This is most player-visible copy.
 *   2. A NAMED SET OF JSX ATTRIBUTES whose values are prose a player reads or hears:
 *      `title`, `aria-label`, `aria-description`, `aria-valuetext`, `alt`, `placeholder`, and the
 *      `label` / `caption` / `heading` / `summary` props this codebase uses for prose.
 *      `aria-live` and `aria-hidden` are deliberately NOT in that set: their values are ARIA
 *      keywords ("polite", "true"), not text, and matching them would be matching the wrong thing.
 *   3. A NAMED SET OF OBJECT-LITERAL PROPERTIES that reach the DOM as prose: `label` and `heading`
 *      (the navigation registry), `title` and `detail` (`api/errors.ts`), `caption`, and `term` /
 *      `definition` (the Glossary's own entries).
 *
 * WHAT IT CANNOT SEE, and therefore never claims: comments, identifiers, import paths, `data-*`
 * attributes, class names, type names, and every string composed at runtime. A comment explaining
 * that a word was removed is invisible here by construction -- the exact false positive that made
 * `check-palette.mjs`'s first draft fail on `Portrait.tsx`'s explanation of a deleted class.
 *
 * IT DOES NOT CLAIM ANYTHING ABOUT RENDERED TEXT. That is a different question with a different
 * answer: `verify:fixes` scans the live DOM's text nodes AND the same attribute list on every
 * audited screen, and that -- not this -- is what may say a word reached a player. A source check
 * saying so would be asserting coverage it does not have.
 *
 * WHOLE WORDS, ANCHORED. `\bgate\b` and never `gate`, so `aggregate`, `delegate`, `mitigate`,
 * `investigate`, `navigate` and `relegate` do not match. The first draft of the palette check was
 * caught by exactly this class of error in the other direction, and a copy check matching substrings
 * would fire on ordinary English constantly and be switched off within a week.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";

// Root `typescript` is a 7.x build whose CommonJS entry no longer exposes the Compiler API, so both
// boundary checks use the isolated tool package's TS5. See `check-palette.mjs`.
import ts from "./openapi-gen/node_modules/typescript/lib/typescript.js";

const SRC = join(process.cwd(), "src");

/** Vocabulary of the build, not of the game. Each is matched as a WHOLE WORD, case-insensitively. */
const FORBIDDEN = [
  "gate",
  "gates",
  "projected",
  "projection",
  "projections",
  "slot",
  "slots",
  "revision",
  "revisions",
  "preflight",
  "bps",
  "ruleset",
  "fixture",
  "fixtures",
  "digest",
];

/** JSX attributes whose value is prose a player reads or hears. NOT a prefix match on `aria-`:
 * `aria-live="polite"` and `aria-hidden="true"` carry keywords, not text. */
const PROSE_ATTRIBUTES = new Set([
  "title",
  "aria-label",
  "aria-description",
  "aria-valuetext",
  "alt",
  "placeholder",
  "label",
  "caption",
  "heading",
  "summary",
]);

/** Object-literal property names whose string values reach the DOM as prose. */
const PROSE_PROPERTIES = new Set([
  "label",
  "heading",
  "title",
  "caption",
  "detail",
  "term",
  "definition",
]);

/**
 * LEGITIMATE EXCEPTIONS, each named individually and each scoped as narrowly as the thing it
 * excuses. A widened rule is how an allowlist stops being one.
 *
 * "Revision" is a real player-facing concept: it has its own Glossary entry, and a definition that
 * explains it in the player's terms ("An opaque marker identifying the exact game state a screen was
 * drawn from"). So the allowance is THAT ONE ENTRY -- the object whose `term` is exactly "Revision",
 * in that one file. It is deliberately not the Glossary file, not the Glossary's definition list,
 * and not the word at large: a `revision` appearing in any OTHER entry, or anywhere else in that
 * file, still fails, because a legitimate definition must not become cover for a leak beside it.
 */
const EXCEPTIONS = [
  {
    word: "revision",
    file: "src/greybox/screens/GlossaryScreen.tsx",
    /** Scope: the one object literal whose `term` is this. Not the file, and not its whole list. */
    glossaryTerm: "Revision",
    reason:
      "a real player-facing concept with its own Glossary entry; the allowance is that single entry",
  },
  {
    word: "revision",
    file: "src/status/ErrorPanel.tsx",
    /** Scope: this EXACT sentence fragment, and no other string in the file. A wording change makes
     * the exception stale, which the unexercised-exception rule below then fails on. */
    text: "The game moved to revision",
    reason:
      "the stale-revision error is the situation the Glossary entry describes in so many words " +
      "(\"the interface echoes it back when resolving, so a stale decision is refused\"), so the " +
      "word is taught first and then used; rewording it would make that entry pointless",
  },
];

/** Does this exception cover this occurrence? Two scope kinds, both requiring the file and the word:
 * `glossaryTerm` covers one object-literal entry, `text` covers one exact prose string. Neither can
 * excuse a whole file, which is the property that keeps this an allowlist. */
function excuses(exception, { word, file, entry }) {
  if (exception.word.toLowerCase() !== word.toLowerCase() || exception.file !== file) return false;
  if (exception.glossaryTerm !== undefined) return exception.glossaryTerm === entry.glossaryTerm;
  if (exception.text !== undefined) return exception.text === entry.text;
  return false;
}

/** A stable key for "this exception was used", for the staleness check. */
function exceptionKey(exception) {
  return `${exception.file}:${exception.glossaryTerm ?? exception.text}:${exception.word}`;
}

/** Every application `.ts`/`.tsx` under `src/`. Test files are excluded because a test may
 * legitimately NAME a forbidden word while asserting its absence -- as several now do. */
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

/** The `term` value of the object literal a node sits inside, or `null`. This is what lets the
 * Glossary allowance be scoped to ONE entry rather than to the file: the walk asks which entry it is
 * standing in, and only "Revision" is excused. */
function enclosingGlossaryTerm(node) {
  for (let current = node.parent; current; current = current.parent) {
    if (!ts.isObjectLiteralExpression(current)) continue;
    for (const property of current.properties) {
      if (
        ts.isPropertyAssignment(property) &&
        (ts.isIdentifier(property.name) || ts.isStringLiteral(property.name)) &&
        property.name.text === "term" &&
        ts.isStringLiteralLike(property.initializer)
      ) {
        return property.initializer.text;
      }
    }
  }
  return null;
}

function attributeName(attribute) {
  const name = attribute.name;
  if (ts.isIdentifier(name)) return name.text;
  // A namespaced JSX name is how `aria-label` and `data-foo` are parsed in some positions.
  return name.getText ? name.getText() : String(name.escapedText ?? "");
}

/** Every prose string in one file, each tagged with where it came from so a failure can say. */
function proseStringsOf(file) {
  const source = readFileSync(file, "utf-8");
  const sourceFile = ts.createSourceFile(
    file,
    source,
    ts.ScriptTarget.Latest,
    /* setParentNodes */ true,
    file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const out = [];

  const push = (node, text, origin) => {
    const trimmed = text.replace(/\s+/g, " ").trim();
    if (trimmed === "") return;
    const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
    out.push({ text: trimmed, origin, line: line + 1, glossaryTerm: enclosingGlossaryTerm(node) });
  };

  const pushLiteralish = (node, origin) => {
    if (ts.isStringLiteralLike(node)) {
      push(node, node.text, origin);
      return;
    }
    if (ts.isTemplateExpression(node)) {
      push(node.head, node.head.text, origin);
      for (const span of node.templateSpans) push(span.literal, span.literal.text, origin);
    }
  };

  const visit = (node) => {
    // (1) JSX text nodes.
    if (ts.isJsxText(node)) {
      push(node, node.text, "jsx-text");
    }

    // (2) The named prose attributes only.
    if (ts.isJsxAttribute(node) && node.initializer) {
      const name = attributeName(node);
      if (PROSE_ATTRIBUTES.has(name)) {
        const value = ts.isJsxExpression(node.initializer)
          ? node.initializer.expression
          : node.initializer;
        if (value) pushLiteralish(value, `attribute ${name}`);
      }
    }

    // (3) The named prose object properties only.
    if (
      ts.isPropertyAssignment(node) &&
      (ts.isIdentifier(node.name) || ts.isStringLiteral(node.name)) &&
      PROSE_PROPERTIES.has(node.name.text)
    ) {
      pushLiteralish(node.initializer, `property ${node.name.text}`);
    }

    ts.forEachChild(node, visit);
  };
  ts.forEachChild(sourceFile, visit);
  return out;
}

const files = applicationSources();
const byFile = files.map((file) => ({
  file: relative(process.cwd(), file),
  prose: proseStringsOf(file),
}));

const failures = [];
const allProse = byFile.flatMap((entry) => entry.prose);

/* ------------------------------------------------------------------------------------------------
 * ANTI-VACUITY, FIRST. A boundary check whose walk matched almost nothing would pass for the wrong
 * reason -- an empty result read as a clean one, which is the exact defect Commit 1a was written to
 * correct. Three independent guards, each on a different way the walk could silently stop working.
 * ---------------------------------------------------------------------------------------------- */
if (byFile.length < 20) {
  failures.push(`only ${byFile.length} application sources parsed; the walk is not reaching src/`);
}
if (allProse.length < 200) {
  failures.push(
    `only ${allProse.length} prose strings found across ${byFile.length} files; the rules below ` +
      `would be close to vacuous, so this is treated as a broken walk rather than a clean result`,
  );
}
// The three inspected categories must each be non-empty, so a walk that quietly stopped seeing (say)
// attributes cannot pass on the strength of the other two.
for (const [category, predicate] of [
  ["jsx-text", (p) => p.origin === "jsx-text"],
  ["prose attributes", (p) => p.origin.startsWith("attribute ")],
  ["prose properties", (p) => p.origin.startsWith("property ")],
]) {
  const found = allProse.filter(predicate).length;
  if (found < 5) {
    failures.push(`only ${found} strings from ${category}; that category of the walk is not working`);
  }
}
// And the walk must NOT see comment prose. Every file touched by this commit explains in a comment
// which build word was removed, so if comments leaked in, the check would report its own rationale
// as a defect.
if (allProse.some((p) => p.text.includes("a gate is a development milestone"))) {
  failures.push("comment prose reached the walk; the check would report its own explanation as a defect");
}

/* ------------------------------------------------------------------------------------------------
 * THE RULE.
 * ---------------------------------------------------------------------------------------------- */
const used = new Set();
for (const { file, prose } of byFile) {
  for (const entry of prose) {
    for (const word of FORBIDDEN) {
      const pattern = new RegExp(`\\b${word}\\b`, "i");
      if (!pattern.test(entry.text)) continue;

      const exception = EXCEPTIONS.find((e) => excuses(e, { word, file, entry }));
      if (exception) {
        used.add(exceptionKey(exception));
        continue;
      }

      failures.push(
        `${file}:${entry.line} (${entry.origin}) says "${word}" in player-visible text: ` +
          `"${entry.text.slice(0, 110)}"`,
      );
    }
  }
}

/* Every declared exception must actually be exercised. An allowlist entry that matches nothing is
 * either stale or misspelled, and either way it is silently widening nothing while looking like a
 * considered decision -- so it fails rather than lingering. */
for (const exception of EXCEPTIONS) {
  const key = exceptionKey(exception);
  if (!used.has(key)) {
    failures.push(
      `declared exception ${key} matched nothing; it is stale or misspelled and must be removed ` +
        `or corrected rather than left as a decoration`,
    );
  }
}

if (failures.length > 0) {
  console.error("check-copy FAILED\n");
  for (const failure of failures) console.error(`  - ${failure}`);
  console.error(
    `\nThese words belong to the build, not to the game. Say the same true thing in the player's ` +
      `terms, or add a NARROWLY SCOPED exception to EXCEPTIONS with its reason.`,
  );
  process.exit(1);
}

// The allowlist is printed on success, deliberately: a growing list of exceptions should be visible
// in the gate's own output rather than buried in a file nobody opens.
console.log(
  `check-copy OK: ${allProse.length} player-visible strings across ${byFile.length} files, ` +
    `${FORBIDDEN.length} forbidden words, whole-word matched.`,
);
for (const exception of EXCEPTIONS) {
  console.log(
    `  allowed: "${exception.word}" in ${exception.file}, scoped to ` +
      `${exception.glossaryTerm !== undefined ? `entry "${exception.glossaryTerm}"` : `the string "${exception.text}"`}` +
      ` -- ${exception.reason}`,
  );
}
