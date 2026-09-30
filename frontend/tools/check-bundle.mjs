#!/usr/bin/env node
// Gate 4A2 closeout -- mandate testing item 21: "production bundle contains
// no dev-only raw-report viewer." Node stdlib only, no new dependency, run
// as a build step (`npm run check:bundle`, after `npm run build`) rather
// than from inside vitest -- `dist/` sits outside `src/`, so
// `import.meta.glob` cannot reach it, and reading it from a vitest test
// would mean adding `@types/node` for `node:fs`, which the mandate's own
// stop conditions rule out as a new dependency.
//
// A prose phrase like "raw report" or "dev viewer" is not a safe thing to
// grep for: any comment or label containing those words would false-positive,
// and minification only makes that worse by discarding exactly the
// identifiers a naive check would key on. This checks against a SENTINEL
// STRING LITERAL instead -- `DEV_RAW_REPORT_SENTINEL` below. Any future
// dev-only raw-report/debug viewer component is required (by convention, and
// by this check) to render that exact literal as a `data-testid` attribute
// value, e.g. `<div data-testid={DEV_RAW_REPORT_SENTINEL}>`. String literals
// used as attribute values survive minification/mangling (only identifiers
// and unreferenced property names get renamed); this check fails the build
// if that literal shows up anywhere in the shipped JS, which is exactly the
// condition "no dev-only raw-report viewer reached production" describes.

//
// Gate 4A3 Commit 6 extends this, because it is the one check that reads the SHIPPED files:
//   * no sourcemap ships: no `*.map` file anywhere under dist/, and no `sourceMappingURL` comment in
//     any built .js or .css (the source-level config already has none; this is the artifact half);
//   * no `import.meta.env` survives into built JS -- frozen plan section 24's "verified, not assumed";
//   * dist/index.html references only same-origin paths: no `http:`, `https:` or protocol-relative
//     `//` in any src or href, so the page can make no request to a CDN or third party;
//   * THE BUNDLE BUDGET, section 5's one row written as a ceiling: the initial JS, gzipped at level 9,
//     must be at most 250 KiB. Its threshold equals its target, with no 2x headroom.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { gzipSync } from "node:zlib";

export const DEV_RAW_REPORT_SENTINEL = "dev-raw-report-viewer";

const distAssetsDir = join(import.meta.dirname, "..", "dist", "assets");

let entries;
try {
  entries = readdirSync(distAssetsDir);
} catch (error) {
  console.error(`check-bundle: could not read ${distAssetsDir} -- run \`npm run build\` first.`);
  console.error(String(error));
  process.exit(1);
}

const jsFiles = entries.filter((name) => name.endsWith(".js"));
if (jsFiles.length === 0) {
  console.error(`check-bundle: no .js files found in ${distAssetsDir} -- build looks incomplete.`);
  process.exit(1);
}

let found = false;
for (const name of jsFiles) {
  const contents = readFileSync(join(distAssetsDir, name), "utf8");
  if (contents.includes(DEV_RAW_REPORT_SENTINEL)) {
    console.error(`check-bundle: found the dev-raw-report sentinel in ${name} -- a dev-only viewer reached the production bundle.`);
    found = true;
  }
}

const distDir = join(distAssetsDir, "..");
const problems = [];

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

for (const path of walk(distDir)) {
  const rel = relative(distDir, path);
  if (rel.endsWith(".map")) problems.push(`a sourcemap ships: ${rel}`);
  if (rel.endsWith(".js") || rel.endsWith(".css")) {
    const text = readFileSync(path, "utf8");
    if (text.includes("sourceMappingURL")) problems.push(`a sourceMappingURL comment ships in ${rel}`);
    if (rel.endsWith(".js") && text.includes("import.meta.env")) {
      problems.push(`import.meta.env survives in ${rel}`);
    }
  }
}

const indexHtml = readFileSync(join(distDir, "index.html"), "utf8");
for (const match of indexHtml.matchAll(/\b(?:src|href)\s*=\s*["']([^"']*)["']/gi)) {
  const url = match[1];
  if (/^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(url)) problems.push(`index.html references a non-same-origin URL: ${url}`);
}

// The initial JS is what index.html loads as a module entry.
const BUNDLE_BUDGET_BYTES = 250 * 1024;
const moduleEntries = [...indexHtml.matchAll(/<script[^>]*type=["']module["'][^>]*src=["']\/?([^"']+)["']/gi)].map((m) => m[1]);
if (moduleEntries.length === 0) problems.push("index.html loads no module script -- cannot measure the bundle budget");
let initialGzip = 0;
for (const entry of moduleEntries) {
  initialGzip += gzipSync(readFileSync(join(distDir, entry)), { level: 9 }).length;
}
if (initialGzip > BUNDLE_BUDGET_BYTES) {
  problems.push(`initial JS is ${(initialGzip / 1024).toFixed(2)} KiB gzipped, over the 250 KiB budget`);
}

for (const problem of problems) console.error(`check-bundle: ${problem}`);
if (found || problems.length > 0) {
  process.exit(1);
}

console.log(
  `check-bundle: OK -- no dev-raw-report sentinel in ${jsFiles.length} built JS file(s); no sourcemap, ` +
    `no import.meta.env, index.html same-origin; initial JS ${(initialGzip / 1024).toFixed(2)} KiB gzip ` +
    `(level 9) of a 250 KiB budget, ${((BUNDLE_BUDGET_BYTES - initialGzip) / 1024).toFixed(2)} KiB headroom.`,
);
