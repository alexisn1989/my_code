/**
 * Gate 4A0 — the greybox must not compute anything, and must not reach anywhere.
 *
 * This is a deliberately MODEST guard, and it is described honestly: it reads
 * the greybox source files and checks a small set of specific, high-signal
 * things. It does NOT, and cannot, prove the semantic absence of client-side
 * simulation. The real Phase 4A guard is layered — generated contract types,
 * forbidden imports, contract tests proving displayed values are server-provided,
 * and review of the small `src/format/` directory — and arrives with the API in
 * Gate 4A1+. What this test does prove is that the greybox, today, calls no
 * network API, imports nothing from the backend, and does not hard-code the
 * engine's mechanics constants.
 */

import { describe, expect, it } from "vitest";

/**
 * Read the greybox's own sources as text. `import.meta.glob` is a Vite feature
 * already typed by `vite/client` (see tsconfig `types`), so this needs no
 * `@types/node` and adds no dependency.
 */
const RAW_SOURCES: Record<string, string> = import.meta.glob("./*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
});

function greyboxSources(): { name: string; source: string }[] {
  return Object.entries(RAW_SOURCES)
    .map(([path, source]) => ({ name: path.replace(/^\.\//, ""), source }))
    .filter((file) => !/\.test\.tsx?$/.test(file.name));
}

function sourceNamed(name: string): string {
  const found = greyboxSources().find((file) => file.name === name);
  if (!found) {
    throw new Error(`greybox source not found: ${name}`);
  }
  return found.source;
}

describe("the greybox performs no I/O", () => {
  it("covers every non-test source file in src/greybox", () => {
    const names = greyboxSources().map((file) => file.name).sort();
    expect(names).toEqual([
      "GreyboxApp.tsx",
      "TurnResultView.tsx",
      "components.tsx",
      "contract.ts",
      "fixture.ts",
      "registry.ts",
      "screens.tsx",
    ]);
  });

  it("never calls fetch, XMLHttpRequest, WebSocket, or EventSource", () => {
    for (const { name, source } of greyboxSources()) {
      expect(source, `${name} must not call fetch`).not.toMatch(/\bfetch\s*\(/);
      expect(source, `${name} must not use XMLHttpRequest`).not.toContain("XMLHttpRequest");
      expect(source, `${name} must not open a WebSocket`).not.toMatch(/new\s+WebSocket/);
      expect(source, `${name} must not open an EventSource`).not.toMatch(/new\s+EventSource/);
    }
  });

  it("imports nothing from the backend or from outside src/", () => {
    for (const { name, source } of greyboxSources()) {
      const imports = [...source.matchAll(/from\s+"([^"]+)"/g)].map((match) => match[1] ?? "");
      for (const specifier of imports) {
        expect(specifier, `${name} imports ${specifier}`).not.toMatch(/backend/);
        expect(specifier, `${name} imports ${specifier}`).not.toMatch(/\.\.\/\.\./);
        expect(specifier, `${name} imports ${specifier}`).not.toMatch(/^app\//);
      }
    }
  });
});

describe("the greybox does not duplicate engine mechanics", () => {
  /**
   * Route costs, the investment cap, the required-support threshold and the
   * polling-swing bound are engine constants. The greybox may DISPLAY them as
   * strings that arrived in the fixture; it must never declare one as a bare
   * numeric constant it could then compute with.
   */
  it("declares no engine constant as a numeric literal outside the fixture", () => {
    const forbidden = [
      /\bconst\s+\w*DECREE\w*\s*=\s*\d/i,
      /\bconst\s+\w*CAPITAL_COST\w*\s*=\s*\d/i,
      /\bconst\s+\w*INVESTMENT_CAP\w*\s*=\s*\d/i,
      /\bconst\s+\w*REQUIRED_\w*\s*=\s*\d/i,
      /\bconst\s+\w*SWING\w*\s*=\s*\d/i,
    ];
    for (const { name, source } of greyboxSources()) {
      if (name === "fixture.ts") {
        continue;
      }
      for (const pattern of forbidden) {
        expect(source, `${name} declares an engine constant`).not.toMatch(pattern);
      }
    }
  });

  it("keeps every displayed quantity in the fixture, not derived in a screen", () => {
    // The one arithmetic expression in the greybox is RatioBar's CSS width, which
    // scales an already-projected ratio field for visual purposes only and cannot
    // change the semantic value rendered beside it. It is asserted explicitly here
    // so that its presence stays a deliberate, reviewed exception rather than an
    // unnoticed precedent.
    const components = sourceNamed("components.tsx");
    expect(components).toContain("ratioBps / 100");
    expect(components).toContain("aria-valuetext={valueText}");

    for (const { name, source } of greyboxSources()) {
      if (name === "components.tsx" || name === "fixture.ts") {
        continue;
      }
      expect(source, `${name} must not multiply or divide a projected value`).not.toMatch(
        /\b\w+Bps\s*[*/]/,
      );
      expect(source, `${name} must not sum projected values`).not.toMatch(/\.reduce\s*\(/);
    }
  });
});
