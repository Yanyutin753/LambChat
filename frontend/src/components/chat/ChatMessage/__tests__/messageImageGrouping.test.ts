import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("ChatMessage image grouping", () => {
  const source = readFileSync(new URL("../index.tsx", import.meta.url), "utf8");

  it("imports isRevealFileImagePart utility", () => {
    expect(source).toContain("isRevealFileImagePart");
  });

  it("imports MessageImageGallery component", () => {
    expect(source).toContain("MessageImageGallery");
  });

  it("defines a groupPartsForGallery function", () => {
    expect(source).toContain("function groupPartsForGallery(");
  });

  it("renders MessageImageGallery for gallery groups", () => {
    expect(source).toContain("key={`gallery-${group.startPartIndex}`}");
  });

  it("uses groupPartsForGallery in the parts rendering loop", () => {
    expect(source).toContain("groupPartsForGallery(message.parts!)");
  });

  it("handles both gallery and single group types", () => {
    expect(source).toContain('group.type === "gallery"');
  });

  it("skips recommend_questions parts", () => {
    expect(source).toContain('part.type !== "recommend_questions"');
  });
});
