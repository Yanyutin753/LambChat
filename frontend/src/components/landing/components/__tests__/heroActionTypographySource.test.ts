import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const hero = readFileSync(new URL("../HeroSection.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../../../../styles/landing.css", import.meta.url), "utf8");

test("hero actions use serif typography without a sans override", () => {
  const actions = [...hero.matchAll(/className="([^"]*public-action[^"]*)"/g)];
  expect(actions).toHaveLength(2);
  for (const action of actions) {
    expect(action[1].split(/\s+/)).toContain("font-serif");
  }
  expect(css).not.toMatch(/\.public-action[^{}]*\{[^}]*font-family:/);
});
