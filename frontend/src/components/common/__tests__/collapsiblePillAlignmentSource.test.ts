import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";

const source = readFileSync(
  new URL("../CollapsiblePill.tsx", import.meta.url),
  "utf8",
);
const animationSource = readFileSync(
  new URL("../../../styles/animations.css", import.meta.url),
  "utf8",
);

describe("CollapsiblePill alignment", () => {
  test("uses a readable line height while preserving monospace labels", () => {
    expect(source).toMatch(
      /"font-sans font-medium tracking-\[0\.01em\] min-w-0 truncate overflow-hidden h-4 text-xs leading-4 inline-flex items-center translate-y-px"/,
    );
  });

  test("does not lift the pill on touch hover states", () => {
    expect(animationSource).toMatch(
      /@media \(hover: none\), \(pointer: coarse\)[\s\S]*?\.pill-btn:hover:not\(:disabled\)\s*\{[\s\S]*?transform:\s*none;/,
    );
  });

  test("does not lift the pill on any hover state", () => {
    expect(animationSource).not.toContain("transform: translateY(-1px);");
  });
});
