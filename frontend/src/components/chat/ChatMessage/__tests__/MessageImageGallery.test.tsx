import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("MessageImageGallery", () => {
  const source = readFileSync(
    new URL("../MessageImageGallery.tsx", import.meta.url),
    "utf8",
  );

  it("exports a MessageImageGallery component", () => {
    expect(source).toContain("export function MessageImageGallery");
  });

  it("accepts images prop of type RevealFileImageInfo[]", () => {
    expect(source).toContain("images: RevealFileImageInfo[]");
  });

  it("uses flex justify-center layout for single image", () => {
    expect(source).toContain("images.length === 1");
    expect(source).toContain("flex justify-center");
  });

  it("uses grid grid-cols-2 for 2-3 images", () => {
    expect(source).toContain("images.length === 3");
    expect(source).toContain("grid grid-cols-2");
  });

  it("uses columns-2 masonry for 4+ images", () => {
    expect(source).toContain("columns-2");
  });

  it("applies col-span-2 to first image when there are 3 images", () => {
    expect(source).toContain("col-span-2");
  });

  it("constrains single image width with max-w-md", () => {
    expect(source).toContain("max-w-md");
  });

  it("uses object-contain instead of object-cover for full image visibility", () => {
    expect(source).toContain("object-contain");
    expect(source).not.toContain("object-cover");
  });

  it("uses ImageWithSkeleton with inline mode", () => {
    expect(source).toContain("ImageWithSkeleton");
    expect(source).toContain("skipUrlResolve");
  });

  it("opens session image gallery on click", () => {
    expect(source).toContain("sessionImageGallery?.openImage");
    expect(source).toContain('"reveal-file"');
  });

  it("shows hover overlay with ExternalLink icon", () => {
    expect(source).toContain("ExternalLink");
    expect(source).toContain("group-hover:opacity-100");
  });

  it("shows file name on hover at bottom", () => {
    expect(source).toContain("image.fileName");
    expect(source).toContain("truncate block");
  });

  it("uses break-inside-avoid for masonry items", () => {
    expect(source).toContain("break-inside-avoid");
  });
});
