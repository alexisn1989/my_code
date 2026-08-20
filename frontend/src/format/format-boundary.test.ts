/**
 * Gate 4A2 -- the structural successor to Gate 4A0's
 * `greybox/no-client-simulation.test.ts`.
 *
 * The frozen plan (S14.1/R9, T-format-boundary) calls for a custom ESLint
 * `no-restricted-syntax` rule confining display arithmetic to `src/format/`.
 * This frontend has no ESLint, and adding typescript-eslint would trip the
 * mandate's own "no dependency beyond openapi-typescript" stop condition. The
 * mandate also explicitly forbids reviving a brittle numeric-literal
 * deny-list -- which is exactly what Gate 4A0's version was (a regex hunting
 * specific constant names like `DECREE_COST`).
 *
 * This test enforces the SAME rule STRUCTURALLY instead: it parses every
 * non-test `.ts`/`.tsx` file under `src/` with the real TypeScript compiler
 * API and walks the real AST, failing on any arithmetic `BinaryExpression`
 * (+ - * / %, and their compound-assignment forms) or increment/decrement
 * expression found outside `src/format/**`. It does not care what a value is
 * named or what a constant's magic number is; it cares whether the file that
 * contains it is the one approved place for that shape of code -- a real
 * parse of real syntax, not a text pattern a differently-shaped expression
 * could slip past.
 *
 * Root `typescript` is pinned to a native/Go-ported 7.x release whose
 * CommonJS entry point no longer exports the Compiler API surface this test
 * needs (`createSourceFile`, `forEachChild`, `isBinaryExpression`, ...) --
 * the same incompatibility Gate 4A2's OpenAPI-type generation hit. That gate
 * was resolved by giving `openapi-typescript` its own isolated
 * `frontend/tools/openapi-gen/` package with a real `typescript@5`
 * devDependency, already installed and already committed. This test reuses
 * that same already-present install (a plain relative import, not a new
 * dependency, not a subprocess spawn -- vitest's worker sandbox in this
 * environment blocks subprocess spawning but not module imports).
 *
 * Reads every source file as raw text via `import.meta.glob`, the same
 * mechanism `schema.test.ts` and Gate 4A0's own test used, so this needs no
 * `node:fs`/`node:path` and no `@types/node` -- this project has never
 * needed Node type definitions, being browser-only, and this test does not
 * become the reason to add one.
 */

import { describe, expect, it } from "vitest";

// See docstring above: reuses the isolated openapi-typescript tool package's
// own TS5 install on purpose, since this project has no ESLint to suppress.
import ts from "../../tools/openapi-gen/node_modules/typescript/lib/typescript.js";

/** Every `.ts`/`.tsx` file under `src/`, read as raw text. */
const RAW_MODULES: Record<string, string> = import.meta.glob("../**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
});

interface SourceFile {
  /** Path relative to `src/`, e.g. `greybox/screens/DashboardScreen.tsx`. */
  relPath: string;
  source: string;
}

/**
 * `import.meta.glob("../**")` keys paths relative to THIS file's own
 * directory (`src/format/`): siblings come back as `./whatever.ts`, and
 * everything else as `../whatever.ts`. Normalize both back to a path
 * relative to `src/` itself, since `./` here always means `format/`.
 */
function toSrcRelativePath(globKey: string): string {
  if (globKey.startsWith("../")) {
    return globKey.slice(3);
  }
  if (globKey.startsWith("./")) {
    return `format/${globKey.slice(2)}`;
  }
  throw new Error(`unexpected glob key shape: ${globKey}`);
}

function allSources(): SourceFile[] {
  return Object.keys(RAW_MODULES)
    .map((path) => toSrcRelativePath(path))
    .filter((relPath) => !/\.test\.tsx?$/.test(relPath))
    .filter((relPath) => !relPath.endsWith("schema.d.ts")) // generated, never hand-edited
    .filter((relPath) => !relPath.endsWith("vite-env.d.ts"))
    .map((relPath) => ({
      relPath,
      source:
        RAW_MODULES[relPath.startsWith("format/") ? `./${relPath.slice("format/".length)}` : `../${relPath}`] ??
        "",
    }));
}

const ARITHMETIC_TOKENS = new Set<number>([
  ts.SyntaxKind.PlusToken,
  ts.SyntaxKind.MinusToken,
  ts.SyntaxKind.AsteriskToken,
  ts.SyntaxKind.SlashToken,
  ts.SyntaxKind.PercentToken,
  ts.SyntaxKind.PlusEqualsToken,
  ts.SyntaxKind.MinusEqualsToken,
  ts.SyntaxKind.AsteriskEqualsToken,
  ts.SyntaxKind.SlashEqualsToken,
  ts.SyntaxKind.PercentEqualsToken,
]);

interface Violation {
  relPath: string;
  line: number;
  text: string;
}

/** True for a path this rule does not police: the format boundary itself, and tests everywhere. */
function isExempt(relPath: string): boolean {
  return relPath.startsWith("format/") || /\.test\.tsx?$/.test(relPath);
}

function parse(file: SourceFile) {
  return ts.createSourceFile(
    file.relPath,
    file.source,
    ts.ScriptTarget.Latest,
    true,
    file.relPath.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
}

// Derived from the already-imported (isolated, TS5) `ts` module rather than
// `import("typescript").Node`, which would resolve through normal module
// resolution to the ROOT `typescript` package (the TS7 install whose
// CommonJS entry point does not export this Compiler API surface at all --
// see the file docstring).
type TsNode = Parameters<typeof ts.isBinaryExpression>[0];

function findArithmeticViolations(file: SourceFile): Violation[] {
  const sourceFile = parse(file);
  const violations: Violation[] = [];

  function visit(node: TsNode): void {
    if (ts.isBinaryExpression(node) && ARITHMETIC_TOKENS.has(node.operatorToken.kind)) {
      const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
      violations.push({ relPath: file.relPath, line: line + 1, text: node.getText(sourceFile) });
    }
    if (
      (ts.isPrefixUnaryExpression(node) || ts.isPostfixUnaryExpression(node)) &&
      (node.operator === ts.SyntaxKind.PlusPlusToken ||
        node.operator === ts.SyntaxKind.MinusMinusToken)
    ) {
      const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
      violations.push({ relPath: file.relPath, line: line + 1, text: node.getText(sourceFile) });
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return violations;
}

describe("the format arithmetic boundary (structural, AST-based)", () => {
  it("covers a non-empty, expected set of source files", () => {
    const relPaths = allSources()
      .map((file) => file.relPath)
      .sort();
    expect(relPaths.length).toBeGreaterThan(10);
    expect(relPaths).toContain("format/format.ts");
    expect(relPaths).toContain("greybox/components.tsx");
    expect(relPaths).toContain("greybox/screens/DecisionsScreen.tsx");
  });

  it("parses every file with the real TypeScript AST without a syntax error", () => {
    for (const file of allSources()) {
      const sourceFile = parse(file);
      const diagnostics = (sourceFile as unknown as { parseDiagnostics?: unknown[] })
        .parseDiagnostics;
      expect(diagnostics ?? [], `${file.relPath} failed to parse`).toHaveLength(0);
    }
  });

  it("declares no arithmetic binary or increment/decrement expression outside src/format/**", () => {
    const violations = allSources()
      .filter((file) => !isExempt(file.relPath))
      .flatMap((file) => findArithmeticViolations(file));

    if (violations.length > 0) {
      const report = violations
        .map((violation) => `  ${violation.relPath}:${violation.line}  ${violation.text}`)
        .join("\n");
      throw new Error(
        "Arithmetic found outside src/format/** -- move it into a named function there and " +
          `import the projected result instead:\n${report}`,
      );
    }
  });

  it("confirms the guard actually fires on a real arithmetic expression (self-check)", () => {
    const probe: SourceFile = { relPath: "greybox/__probe__.ts", source: "export const total = a + b;\n" };
    expect(findArithmeticViolations(probe)).toHaveLength(1);

    const probeIncrement: SourceFile = {
      relPath: "greybox/__probe2__.ts",
      source: "let count = 0;\ncount++;\n",
    };
    expect(findArithmeticViolations(probeIncrement)).toHaveLength(1);
  });

  it("confirms src/format/** itself is exempt, and does contain real arithmetic", () => {
    const formatFile = allSources().find((file) => file.relPath === "format/format.ts");
    if (!formatFile) {
      throw new Error("format/format.ts not found");
    }
    expect(isExempt(formatFile.relPath)).toBe(true);
    // format.ts is expected to contain arithmetic -- it's the approved boundary.
    // This asserts the exemption is real (the file is not accidentally empty of
    // the very thing it exists to contain) without policing it, by re-checking
    // it under a path this rule would NOT exempt.
    expect(
      findArithmeticViolations({ ...formatFile, relPath: "not-exempt/format.ts" }),
    ).not.toHaveLength(0);
  });
});

describe("the greybox performs no direct I/O outside the typed client", () => {
  const greyboxSources = allSources().filter((file) => file.relPath.startsWith("greybox/"));

  it("never calls fetch, XMLHttpRequest, WebSocket, or EventSource directly", () => {
    for (const { relPath, source } of greyboxSources) {
      expect(source, `${relPath} must not call fetch directly`).not.toMatch(/\bfetch\s*\(/);
      expect(source, `${relPath} must not use XMLHttpRequest`).not.toContain("XMLHttpRequest");
      expect(source, `${relPath} must not open a WebSocket`).not.toMatch(/new\s+WebSocket/);
      expect(source, `${relPath} must not open an EventSource`).not.toMatch(/new\s+EventSource/);
    }
  });

  it("imports nothing from the backend or from outside src/", () => {
    for (const { relPath, source } of greyboxSources) {
      const imports = [...source.matchAll(/from\s+"([^"]+)"/g)].map((match) => match[1] ?? "");
      for (const specifier of imports) {
        expect(specifier, `${relPath} imports ${specifier}`).not.toMatch(/backend/);
        expect(specifier, `${relPath} imports ${specifier}`).not.toMatch(/^app\//);
      }
    }
  });

  it("has no remaining runtime import of the deleted fixture or contract files", () => {
    const relPaths = new Set(allSources().map((file) => file.relPath));
    expect([...relPaths]).not.toContain("greybox/fixture.ts");
    expect([...relPaths]).not.toContain("greybox/contract.ts");
    for (const { relPath, source } of allSources()) {
      expect(source, `${relPath} still imports the deleted fixture`).not.toMatch(
        /from\s+"[^"]*\/fixture"/,
      );
      expect(source, `${relPath} still imports the deleted contract`).not.toMatch(
        /from\s+"[^"]*\/contract"/,
      );
    }
  });
});
