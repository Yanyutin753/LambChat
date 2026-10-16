import { readFileSync } from "node:fs";
import { join } from "node:path";

const css = readFileSync(
  join(import.meta.dirname, "../card-base.css"),
  "utf8",
).replace(/\s+/g, " ");

test("card actions share 36px controls and 16px icons", () => {
  for (const selector of [".scb__action-btn", ".mp-card__action-btn"]) {
    const rule = css.slice(css.indexOf(`${selector} {`)).split("}")[0];
    expect(rule).toContain("width: 2.25rem;");
    expect(rule).toContain("height: 2.25rem;");
    expect(rule).toContain("min-width: 2.25rem;");
    expect(rule).toContain("min-height: 2.25rem;");
  }
  const ghost = css.split(".scb__action-btn--ghost {")[1].split("}")[0];
  expect(ghost).not.toMatch(/(?:width|height|border-radius):/);
  const textAction = css
    .split(".scb__footer .pps-card__action {")[1]
    .split("}")[0];
  expect(textAction).toContain("height: 2.25rem;");
  expect(textAction).toContain("padding-block: 0;");
  const icons = css
    .split(
      ":is(.scb__action-btn, .mp-card__action-btn, .scb__footer .pps-card__action) > svg {",
    )[1]
    .split("}")[0];
  expect(icons).toContain("width: 1rem;");
  expect(icons).toContain("height: 1rem;");
});

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

test("shared resource cards retain readable labels over a quiet theme-aware banner", () => {
  const status = css.split(".scb__status-pill {")[1].split("}")[0];
  expect(status).toContain("background: var(--theme-bg-card);");
  expect(status).toContain("border: 1px solid");
  expect(status).toContain("min-height: 1.5rem;");
  expect(status).toContain("border-radius: 0.375rem;");
  expect(css).not.toContain(".scb .scb__banner .scb__status-pill");
  expect(css).not.toContain(".scb .scb__body :is(");
  const banner = css.split(".scb__banner::before {")[1].split("}")[0];
  expect(banner).toContain("var(--theme-bg-card) 62%");
  expect(banner).toContain("pointer-events: none;");
  expect(css).not.toContain(".scb:hover .scb__banner::after");
});

test("card tag hover and selection keep the same transparent background", () => {
  for (const selector of [
    "button.scb__mini-tag:hover",
    ".scb__mini-tag--active",
    ".mp-card__mini-tag:hover",
    ".mp-card__mini-tag--active",
  ]) {
    const rule = css.split(`${selector} {`)[1].split("}")[0];
    expect(rule, selector).not.toMatch(/background(?:-color)?:/);
  }
});
