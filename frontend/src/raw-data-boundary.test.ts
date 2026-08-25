/**
 * Gate 4A2 closeout, final acceptance pass item 17 -- the closeout plan
 * identified missing automated coverage for the raw-data boundary: no
 * screen renders a raw `GameState`/`TurnReport`/save-envelope JSON dump,
 * and the production entry point cannot import a dev-only raw-report
 * viewer. A prose search for "raw" or "dump" would be defeated by a
 * rename; `frontend/tools/check-bundle.mjs` already enforces the
 * SENTINEL-STRING form of this rule at the built-bundle level (wired into
 * CI's frontend job, after Build). This test enforces the SAME rule at the
 * SOURCE level, reading `DEV_RAW_REPORT_SENTINEL`'s real value out of that
 * same file's raw text (never duplicating the literal by hand, so the two
 * checks cannot drift apart) -- and, exactly like `format-boundary.test.ts`'s
 * own arithmetic guard, proves via a synthetic self-check that the
 * detection logic actually fires rather than trivially passing because
 * nothing has ever tried to violate it.
 *
 * `check-bundle.mjs` is a script, not a pure module -- it calls
 * `readdirSync`/`process.exit` at top level against `dist/assets`, so it is
 * read here as RAW TEXT via `import.meta.glob` (never `import`ed/executed;
 * importing it directly from a test would kill the vitest worker if
 * `dist/` has not been built yet).
 */

import { describe, expect, it } from "vitest";

const RAW_MODULES: Record<string, string> = import.meta.glob("./**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
});

const TOOLS_MODULES: Record<string, string> = import.meta.glob("../tools/*.mjs", {
  query: "?raw",
  import: "default",
  eager: true,
});

const CHECK_BUNDLE_SOURCE = TOOLS_MODULES["../tools/check-bundle.mjs"];
if (CHECK_BUNDLE_SOURCE === undefined) {
  throw new Error("tools/check-bundle.mjs not found");
}
const sentinelMatch = /DEV_RAW_REPORT_SENTINEL\s*=\s*"([^"]+)"/.exec(CHECK_BUNDLE_SOURCE);
if (sentinelMatch === null) {
  throw new Error("could not read DEV_RAW_REPORT_SENTINEL out of tools/check-bundle.mjs");
}
const DEV_RAW_REPORT_SENTINEL = sentinelMatch[1] as string;

interface SourceFile {
  /** Path relative to `src/`, e.g. `main.tsx` or `greybox/screens/DecisionsScreen.tsx`. */
  relPath: string;
  source: string;
}

function allSources(): SourceFile[] {
  return Object.keys(RAW_MODULES)
    .map((key) => key.replace(/^\.\//, ""))
    .filter((relPath) => !/\.test\.tsx?$/.test(relPath))
    .filter((relPath) => !relPath.endsWith("schema.d.ts"))
    .filter((relPath) => !relPath.endsWith("vite-env.d.ts"))
    .map((relPath) => ({ relPath, source: RAW_MODULES[`./${relPath}`] ?? "" }));
}

function importSpecifiers(source: string): string[] {
  return [...source.matchAll(/from\s+"([^"]+)"/g)].map((match) => match[1] ?? "");
}

/**
 * Resolves a relative import specifier against the importing file's own
 * directory, trying `.tsx` then `.ts`. This codebase has no barrel/index
 * redirection and no path aliases (every import in `src/` is a direct
 * relative specifier -- confirmed by inspection), so a plain extension
 * probe against the known file set is sufficient and never silently wrong:
 * an unresolvable specifier (a bare package import like `react`) is simply
 * not a local module, and is skipped rather than guessed at.
 */
function resolveImport(fromRelPath: string, specifier: string, knownPaths: Set<string>): string | null {
  if (!specifier.startsWith(".")) {
    return null;
  }
  const fromDir = fromRelPath.includes("/") ? fromRelPath.slice(0, fromRelPath.lastIndexOf("/")) : "";
  const combined = fromDir ? `${fromDir}/${specifier}` : specifier;
  const resolvedSegments: string[] = [];
  for (const segment of combined.split("/")) {
    if (segment === "." || segment === "") {
      continue;
    }
    if (segment === "..") {
      resolvedSegments.pop();
    } else {
      resolvedSegments.push(segment);
    }
  }
  const base = resolvedSegments.join("/");
  for (const candidate of [`${base}.tsx`, `${base}.ts`]) {
    if (knownPaths.has(candidate)) {
      return candidate;
    }
  }
  return null;
}

/** BFS from `entryRelPath` over the REAL import graph (never a hand-maintained
 * list), returning every file transitively reachable, the entry included. */
function reachableFrom(entryRelPath: string, sources: SourceFile[]): Set<string> {
  const byPath = new Map(sources.map((file) => [file.relPath, file]));
  const knownPaths = new Set(byPath.keys());
  const visited = new Set<string>();
  const queue = [entryRelPath];
  while (queue.length > 0) {
    const current = queue.shift() as string;
    if (visited.has(current)) {
      continue;
    }
    visited.add(current);
    const file = byPath.get(current);
    if (!file) {
      continue;
    }
    for (const specifier of importSpecifiers(file.source)) {
      const resolved = resolveImport(current, specifier, knownPaths);
      if (resolved !== null && !visited.has(resolved)) {
        queue.push(resolved);
      }
    }
  }
  return visited;
}

function sentinelViolations(reachable: Set<string>, sources: SourceFile[]): string[] {
  const byPath = new Map(sources.map((file) => [file.relPath, file]));
  return [...reachable].filter((relPath) => byPath.get(relPath)?.source.includes(DEV_RAW_REPORT_SENTINEL));
}

describe("the raw-data boundary (structural, sentinel-based, mirrors tools/check-bundle.mjs)", () => {
  it("covers a non-empty, expected set of source files including the production entry", () => {
    const relPaths = allSources().map((file) => file.relPath);
    expect(relPaths.length).toBeGreaterThan(10);
    expect(relPaths).toContain("main.tsx");
    expect(relPaths).toContain("greybox/screens/DecisionsScreen.tsx");
    expect(relPaths).toContain("greybox/TurnResultView.tsx");
    expect(relPaths).toContain("greybox/policy/PolicyCardGrid.tsx");
    expect(relPaths).toContain("greybox/policy/PolicyCardView.tsx");
    expect(relPaths).toContain("greybox/policy/ConsequencesPanel.tsx");
  });

  it("no screen or shared UI component renders a raw JSON dump (no JSON.stringify in the rendering layer)", () => {
    // Scoped to greybox/** -- the rendering layer -- exactly like
    // format-boundary.test.ts's own I/O-boundary check. api/client.ts's
    // JSON.stringify is legitimate outbound request-body serialization, not
    // a raw-state dump, and stays out of scope on purpose.
    const violations = allSources()
      .filter((file) => file.relPath.startsWith("greybox/"))
      .filter((file) => /JSON\.stringify/.test(file.source))
      .map((file) => file.relPath);
    expect(violations, `JSON.stringify found in the rendering layer: ${violations.join(", ")}`).toEqual([]);
  });

  it("the production entry's real, transitive import graph never reaches a dev-raw-report-viewer sentinel", () => {
    const sources = allSources();
    const reachable = reachableFrom("main.tsx", sources);
    const violations = sentinelViolations(reachable, sources);
    expect(
      violations,
      `production entry reaches a dev-raw-report-viewer sentinel via: ${violations.join(", ")}`,
    ).toEqual([]);
  });

  it("no source file anywhere declares the sentinel today (there is no dev-raw-report viewer in this codebase yet)", () => {
    const violations = allSources()
      .filter((file) => file.source.includes(DEV_RAW_REPORT_SENTINEL))
      .map((file) => file.relPath);
    expect(violations).toEqual([]);
  });

  it("confirms the reachability+sentinel guard actually fires on a synthetic violation (self-check)", () => {
    const syntheticSources: SourceFile[] = [
      { relPath: "main.tsx", source: 'import { Viewer } from "./dev/RawReportViewer";\n' },
      {
        relPath: "dev/RawReportViewer.tsx",
        source: `export const Viewer = () => React.createElement("div", { "data-testid": "${DEV_RAW_REPORT_SENTINEL}" });\n`,
      },
    ];
    const reachable = reachableFrom("main.tsx", syntheticSources);
    expect(reachable).toContain("dev/RawReportViewer.tsx");
    expect(sentinelViolations(reachable, syntheticSources)).toEqual(["dev/RawReportViewer.tsx"]);
  });

  it("confirms an UNREACHABLE dev-raw-report-viewer module is correctly excluded (this is an import-graph check, not a blanket ban)", () => {
    // A dev-only tool file that the production entry never imports is
    // legitimate and must not be flagged -- only reachability from main.tsx
    // makes a sentinel a real production-bundle risk.
    const syntheticSources: SourceFile[] = [
      { relPath: "main.tsx", source: 'import { App } from "./App";\n' },
      { relPath: "App.tsx", source: "export const App = () => null;\n" },
      {
        relPath: "dev/RawReportViewer.tsx",
        source: `export const Viewer = () => React.createElement("div", { "data-testid": "${DEV_RAW_REPORT_SENTINEL}" });\n`,
      },
    ];
    const reachable = reachableFrom("main.tsx", syntheticSources);
    expect(reachable).not.toContain("dev/RawReportViewer.tsx");
    expect(sentinelViolations(reachable, syntheticSources)).toEqual([]);
  });
});
