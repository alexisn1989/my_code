import type { Config } from "tailwindcss";

// Tailwind v4's primary configuration surface is CSS (`@theme` in
// src/styles/tokens.css), not this file — see that file for the actual
// MANDATE color tokens (product spec §27). This file exists for editor/
// tooling integrations that still expect a `tailwind.config.ts` and for
// explicit content-source globs.
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
};

export default config;
