import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("MarkdownContent image sizing", () => {
  // Find the img override section in the react-markdown components prop
  const imgStart = "img: ({ src, alt })";
  const source = readFileSync(
    new URL("../MarkdownContent.tsx", import.meta.url),
    "utf8",
  );
  const startIdx = source.indexOf(imgStart);
  // End at the closing }, of the img handler (before the next property)
  const endIdx = source.indexOf("},", startIdx + imgStart.length);
  const imgSection = source.substring(startIdx, endIdx);

  it("limits markdown images to max-w-lg instead of max-w-full", () => {
    expect(imgSection).toContain("max-w-lg");
    expect(imgSection).not.toContain("max-w-full");
  });

  it("preserves h-auto for natural aspect ratio", () => {
    expect(imgSection).toContain("h-auto");
  });

  it("adds cursor-zoom-in for click affordance", () => {
    expect(imgSection).toContain("cursor-zoom-in");
  });
});
