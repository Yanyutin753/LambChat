import { readFileSync } from "node:fs";
import postcss from "postcss";
import { expect, test } from "vitest";

test.each([
  ["components.css", ".ui-select-trigger"],
  ["components.css", ".ui-select-option"],
  ["components.css", ".glass-input.es-select-btn"],
  ["components.css", ".glass-select-option"],
  ["chat.css", ".chat-input-toolbar button"],
])("%s gives %s a 44px mobile touch height", (file, selector) => {
  const css = postcss.parse(
    readFileSync(new URL(`../${file}`, import.meta.url), "utf8"),
  );
  let height: string | undefined;
  css.walkAtRules("media", (media) => {
    if (media.params !== "(max-width: 639px)") return;
    media.walkRules((rule) => {
      if (!rule.selectors.includes(selector)) return;
      rule.walkDecls("min-height", (declaration) => {
        height = declaration.value;
      });
    });
  });
  expect(height).toBe("2.75rem");
});

test("select menus stop their entrance animation with reduced motion", () => {
  const css = postcss.parse(
    readFileSync(new URL("../components.css", import.meta.url), "utf8"),
  );
  const reduced = new Set<string>();
  css.walkAtRules("media", (media) => {
    if (media.params !== "(prefers-reduced-motion: reduce)") return;
    media.walkRules((rule) => {
      rule.walkDecls("animation", (declaration) => {
        if (declaration.value === "none")
          rule.selectors.forEach((selector) => reduced.add(selector));
      });
    });
  });
  expect(reduced.has(".ui-select-dropdown")).toBe(true);
  expect(reduced.has(".glass-select-dropdown")).toBe(true);
});
