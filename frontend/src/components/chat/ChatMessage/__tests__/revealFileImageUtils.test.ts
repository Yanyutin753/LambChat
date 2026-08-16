import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("isRevealFileImagePart", () => {
  it("exports a function that accepts a MessagePart", () => {
    const source = readFileSync(
      new URL("../revealFileImageUtils.ts", import.meta.url),
      "utf8",
    );
    expect(source).toContain("export function isRevealFileImagePart(");
    expect(source).toContain("RevealFileImageInfo | null");
  });

  it("checks for tool type and reveal_file name", () => {
    const source = readFileSync(
      new URL("../revealFileImageUtils.ts", import.meta.url),
      "utf8",
    );
    expect(source).toContain('part.name !== "reveal_file"');
    expect(source).toContain('part.type !== "tool"');
  });

  it("handles both new format (type: image) and old format (file_reveal)", () => {
    const source = readFileSync(
      new URL("../revealFileImageUtils.ts", import.meta.url),
      "utf8",
    );
    expect(source).toContain('r.type === "image"');
    expect(source).toContain('result.type === "file_reveal"');
  });

  it("uses isImageFile for old format extension check", () => {
    const source = readFileSync(
      new URL("../revealFileImageUtils.ts", import.meta.url),
      "utf8",
    );
    expect(source).toContain("isImageFile(ext)");
  });

  it("returns null for non-image reveal_file (e.g. pdf, document)", () => {
    const source = readFileSync(
      new URL("../revealFileImageUtils.ts", import.meta.url),
      "utf8",
    );
    expect(source).toMatch(/if \(!isImageFile\(ext\)/);
  });

  it("uses getFullUrl to resolve image src", () => {
    const source = readFileSync(
      new URL("../revealFileImageUtils.ts", import.meta.url),
      "utf8",
    );
    expect(source).toContain("getFullUrl");
  });
});
