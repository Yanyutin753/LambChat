import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const css = readFileSync(
  new URL("../legacy-panels.css", import.meta.url),
  "utf8",
);
test("restored panel chrome does not override the shared mobile action visibility", () => {
  expect(css).not.toMatch(
    /\.panel-header__mobile-actions\s*\{\s*display:\s*none/,
  );
});
test("channels retain their original banner independently of skill cards", () => {
  const source = readFileSync(
    new URL("../../components/pages/ChannelsPage.tsx", import.meta.url),
    "utf8",
  );
  expect(source).toContain('className="scb__banner');
  expect(source).not.toMatch(/<SkillBaseCard\s/);
});
test("all panels use the original shared card and one layout rhythm", () => {
  const cards = readFileSync(
    new URL("../../components/common/SkillBaseCard.tsx", import.meta.url),
    "utf8",
  );
  const layout = readFileSync(
    new URL("../panels.css", import.meta.url),
    "utf8",
  );
  expect(cards).toContain('className="scb__banner');
  expect(cards).toContain("font-serif");
  expect(css).not.toContain(':not([data-panel="skills"])');
  expect(layout).toContain("--panel-inset");
  expect(layout).not.toContain('[data-panel="marketplace"]');
});
