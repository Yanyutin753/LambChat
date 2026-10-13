import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");
const dark = source.slice(
  source.indexOf(".dark {"),
  source.indexOf(".theme-sepia {"),
);
function channels(name: string): number[] {
  const match = dark.match(new RegExp(`--theme-${name}: (#\\w{6});`));
  expect(match, name).not.toBeNull();
  return match![1]
    .slice(1)
    .match(/../g)!
    .map((value) => parseInt(value, 16));
}
function luminance(name: string): number {
  const values = channels(name).map((channel) => {
    const value = channel / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return values[0] * 0.2126 + values[1] * 0.7152 + values[2] * 0.0722;
}

test("dark surfaces use a neutral graphite undertone", () => {
  for (const name of [
    "bg",
    "bg-sidebar",
    "bg-card",
    "bg-subtle",
    "bg-elevated",
  ]) {
    const values = channels(name);
    expect(Math.max(...values) - Math.min(...values), name).toBeLessThanOrEqual(
      4,
    );
  }
  expect(luminance("bg-sidebar")).toBeGreaterThan(luminance("bg"));
  expect(luminance("bg-card")).toBeGreaterThan(luminance("bg-sidebar"));
  expect(luminance("bg-elevated")).toBeGreaterThan(luminance("bg-card"));
});

test("dark supporting text remains readable on every neutral surface", () => {
  for (const text of ["text", "text-secondary", "text-tertiary"]) {
    for (const background of [
      "bg",
      "bg-sidebar",
      "bg-card",
      "bg-subtle",
      "bg-elevated",
    ]) {
      const ratio = (luminance(text) + 0.05) / (luminance(background) + 0.05);
      expect(ratio, `${text} on ${background}`).toBeGreaterThanOrEqual(4.5);
    }
  }
});
