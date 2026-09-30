import type { Config } from "tailwindcss";

// Tailwind v4's primary configuration surface is CSS (`@theme` in
// src/styles/tokens.css), not this file — see that file for the actual
// MANDATE color tokens (product spec §27). This file exists ONLY for editor/
// tooling integrations that still expect a `tailwind.config.ts`: the build
// never loads it (there is no `@config`), so the `content` globs below do not
// decide what is scanned. That is set by `source(none)` and the `@source`
// lines in tokens.css, and enforced by `npm run check:css-sources`.
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
};

export default config;
