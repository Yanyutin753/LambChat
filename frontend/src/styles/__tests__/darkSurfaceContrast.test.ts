import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");
const dark = source.slice(
  source.indexOf(".dark {"),
  source.indexOf(".theme-sepia {"),
);
const surfaces = ["bg", "bg-sidebar", "bg-card", "bg-subtle", "bg-elevated"];
function channels(name: string) {
  const hex = dark.match(new RegExp(`--theme-${name}: (#\\w{6});`))![1];
  return hex.match(/[a-f\d]{2}/gi)!.map((value) => parseInt(value, 16));
}
function luminance(name: string) {
  const rgb = channels(name).map((channel) => {
    const value = channel / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}

test("dark workspace surfaces use neutral gray without a brown cast", () => {
  for (const name of [...surfaces, "border", "border-hover", "border-subtle"]) {
    const rgb = channels(name);
    expect(Math.max(...rgb) - Math.min(...rgb), name).toBeLessThanOrEqual(5);
    expect(rgb[0], name).toBeLessThanOrEqual(rgb[2]);
  }
});

test("dark supporting text meets AA contrast on every shared surface", () => {
  for (const text of ["text-secondary", "text-tertiary"]) {
    for (const background of surfaces) {
      expect(
        (luminance(text) + 0.05) / (luminance(background) + 0.05),
        `${text} on ${background}`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  }
});
