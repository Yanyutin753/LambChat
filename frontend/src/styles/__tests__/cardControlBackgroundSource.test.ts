import { readFileSync } from "node:fs";
import { join } from "node:path";

const css = readFileSync(join(import.meta.dirname, "../card-base.css"), "utf8");

test("shared card tags and secondary actions blend into the card surface", () => {
  for (const selector of [
    "scb__mini-tag",
    "scb__action-btn",
    "mp-card__mini-tag",
    "mp-card__action-btn",
  ]) {
    const rule = css.match(new RegExp(`\\.${selector} \\{([^}]+)\\}`))?.[1];
    expect(rule, selector).toMatch(/background: transparent;/);
  }
});

test("dark card status badges use the theme surface instead of black", () => {
  const rules =
    css.match(/\.dark \.(?:scb|mp-card)__status-pill--[^{}]*\{[^}]*\}/g) || [];
  expect(rules.length).toBeGreaterThan(0);
  for (const rule of rules) {
    expect(rule).not.toMatch(/background: rgba\(0, 0, 0,/);
    expect(rule).toContain("background: var(--theme-bg-subtle);");
  }
});
