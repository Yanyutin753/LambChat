import { expect, test } from "vitest";
import { GRADIENT_PALETTES, nameToGradient } from "../cardUtils";

test("original banner colors are deterministic for multilingual names", () => {
  const names = [
    "Hire Me",
    "Research",
    "研究",
    "調査",
    "연구",
    "Исследование",
    "",
    "x".repeat(500),
  ];
  for (const name of names) {
    const colors = nameToGradient(name);
    expect(GRADIENT_PALETTES).toContain(colors);
    expect(nameToGradient(name)).toEqual(colors);
    expect(colors).toHaveLength(3);
  }
  expect(
    new Set(names.map((name) => nameToGradient(name))).size,
  ).toBeGreaterThan(1);
});
