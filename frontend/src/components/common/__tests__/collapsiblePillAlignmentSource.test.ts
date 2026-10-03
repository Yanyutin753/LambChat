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
    expect(animationSource).toMatch(
      /\.pill-btn\s*\{[^}]*items-center[^}]*font-mono[^}]*leading-normal/,
    );
    expect(animationSource).toMatch(
      /\.pill-btn > span\s*\{\s*line-height: inherit;/,
    );
    expect(animationSource).toMatch(
      /\.pill-btn > svg\s*\{[^}]*block[^}]*size-3[^}]*shrink-0/,
    );
    expect(source).not.toContain("tracking-[0.01em]");
    expect(source).not.toContain("translate-y-px");
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
