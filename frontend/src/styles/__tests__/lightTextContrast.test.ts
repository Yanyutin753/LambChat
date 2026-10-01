import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");
const light = source.slice(
  source.indexOf(":root {"),
  source.indexOf(".dark {"),
);
function luminance(hex: string): number {
  const channels = hex.match(/[a-f\d]{2}/gi)!.map((channel) => {
    const value = parseInt(channel, 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}
test("light theme supporting text remains readable on panel backgrounds", () => {
  const color = (name: string) => {
    const match = light.match(new RegExp(`--theme-${name}: (#\\w{6});`));
    expect(match, name).not.toBeNull();
    return luminance(match![1]);
  };
  for (const text of ["text-secondary", "text-tertiary"]) {
    for (const background of ["bg", "bg-card", "bg-subtle"]) {
      const ratio = (color(background) + 0.05) / (color(text) + 0.05);
      expect(ratio, `${text} on ${background}`).toBeGreaterThanOrEqual(4.5);
    }
  }
});
