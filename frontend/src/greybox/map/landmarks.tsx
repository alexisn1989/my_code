/**
 * Gate 4A3 M-1: original ink pictograms for the seven places, drawn for this game in the palette's
 * own colours (`tokens.css`). Decorative: every pictogram sits beside a text name, and is hidden from
 * assistive technology.
 */

import type { ReactNode } from "react";

import type { PlaceId } from "./places";

const INK = "var(--color-navy-950)";
const FILL = "var(--color-parchment-200)";
const FILL_LIGHT = "var(--color-parchment-100)";

const DRAWINGS: Record<PlaceId, ReactNode> = {
  parliament: (
    <>
      <path d="M6 14 a10 7 0 0 1 20 0z" fill={FILL} />
      <path d="M16 4v3M4 14h24M5 17h22M7 17v8M11 17v8M15 17v8M19 17v8M23 17v8M25 17v8M3 26h26M2 28.5h28" />
    </>
  ),
  palace: (
    <>
      <path d="M4 28V13l3-3 3 3v15M22 28V13l3-3 3 3v15" fill={FILL} />
      <path d="M10 28V17h12v11" fill={FILL_LIGHT} />
      <path d="M14 28v-5a2 2 0 0 1 4 0v5M25 10V4l4 1.5L25 7M2 28.5h28" />
    </>
  ),
  constitution: (
    <>
      <path d="M8 5h15a3 3 0 0 1 3 3v17H11a3 3 0 0 1-3-3z" fill={FILL_LIGHT} />
      <path d="M8 22a3 3 0 0 0 3 3M12 10h10M12 14h10M12 18h6" />
      <circle cx="22" cy="22" r="3.5" fill="var(--color-accent-red-600)" />
    </>
  ),
  treasury: (
    <>
      <rect x="5" y="10" width="22" height="16" rx="1.5" fill={FILL} />
      <path d="M5 15h22M16 17.5v-1M16 24.5v-1M9 10V7h14v3" />
      <circle cx="16" cy="20.5" r="3" />
    </>
  ),
  archive: (
    <>
      <path d="M5 25h22v3H5zM6 20h20v5H6zM8 14h17v6H8z" fill={FILL} />
      <path d="M10 9l12-3 1.5 5-12 3z" fill={FILL_LIGHT} />
    </>
  ),
  embassies: (
    <>
      <path d="M9 28V5M23 28V5M4 28.5h24" />
      <path d="M9 6h10l-2 3 2 3H9z" fill="var(--color-info-400)" />
      <path d="M23 6H13l2 3-2 3h10z" fill={FILL} />
    </>
  ),
  garrison: (
    <>
      <path d="M4 28V12h4v3h4v-3h8v3h4v-3h4v16z" fill={FILL} />
      <path d="M13 28v-6h6v6M16 12V4l5 2-5 2" />
    </>
  ),
};

export function Landmark({ id, className }: { id: PlaceId; className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
      className={className}
      fill="none"
      stroke={INK}
      strokeWidth={1.6}
      strokeLinejoin="round"
    >
      {DRAWINGS[id]}
    </svg>
  );
}
