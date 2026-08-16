import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("FileRevealItem image sizing", () => {
  const source = readFileSync(
    new URL("../items/FileRevealItem.tsx", import.meta.url),
    "utf8",
  );

  it("adds max-w-md for image container (left-aligned)", () => {
    expect(source).toContain('isImage && "max-w-md"');
    expect(source).not.toContain("mx-auto");
  });

  it("does not set fixed aspectRatio for images", () => {
    expect(source).toContain("isImage ? undefined : { aspectRatio");
    expect(source).not.toContain('isImage ? "16/10"');
  });

  it("uses object-contain instead of object-cover for images", () => {
    expect(source).toContain("object-contain");
  });

  it("uses w-full h-auto for natural image sizing", () => {
    expect(source).toContain("w-full h-auto object-contain");
  });

  it("does not use absolute positioning for image", () => {
    const lines = source.split("\n");
    const objectContainLineIdx = lines.findIndex((l) =>
      l.includes("object-contain"),
    );
    expect(objectContainLineIdx).toBeGreaterThanOrEqual(0);
    expect(lines[objectContainLineIdx]).not.toContain("absolute inset-0");
  });
});
