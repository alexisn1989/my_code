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

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

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

if (found) {
  process.exit(1);
}

console.log(`check-bundle: OK -- no dev-raw-report sentinel in ${jsFiles.length} built JS file(s).`);
