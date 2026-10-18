import { readFileSync } from "node:fs";
import postcss from "postcss";
import { expect, test } from "vitest";

// Custom properties accept unknown functions even when their consumer cannot.
// Model the capability cascade, then resolve the actual shipped token values.
function tokensFor(
  file: string,
  shell: string,
  theme: string,
  colorMix: boolean,
) {
  const values = new Map<string, string>();
  const selectors = new Set([
    ":root",
    shell,
    ...(theme ? [theme, `${theme} ${shell}`] : []),
  ]);
  for (const name of ["tokens.css", file]) {
    const css = postcss.parse(
      readFileSync(new URL(`../${name}`, import.meta.url), "utf8"),
    );
    css.walkRules((rule) => {
      if (!rule.selectors.some((selector) => selectors.has(selector))) return;
      for (let parent = rule.parent; parent; parent = parent.parent) {
        if (parent.type !== "atrule") continue;
        if (
          parent.name !== "supports" ||
          !parent.params.includes("color-mix")
        ) {
          continue;
        }
        if (parent.params.trim().startsWith("not") === colorMix) return;
      }
      rule.walkDecls(/^--/, (declaration) => {
        values.set(declaration.prop, declaration.value);
      });
    });
  }
  function resolve(name: string): string {
    return values
      .get(name)!
      .replace(/var\((--[\w-]+)\)/g, (_, key: string) => resolve(key));
  }
  return resolve;
}

for (const [theme, border] of [
  ["", "#e7e5e4"],
  [".dark", "#353639"],
  [".theme-sepia", "#ddd2b8"],
]) {
  for (const [file, shell, prefix, surfaces] of [
    ["glass.css", ".glass-shell", "glass", ["bg", "bg-hover", "bg-subtle"]],
    [
      "components.css",
      ".usage-panel",
      "usage",
      ["surface", "surface-hover", "inset-bg", "code-bg"],
    ],
    [
      "skill.css",
      ".skill-theme-shell",
      "skill",
      ["surface-alt", "surface-strong"],
    ],
  ] as const) {
    test(`${shell} retains themed borders and surfaces without color-mix in ${
      theme || "light"
    }`, () => {
      const resolve = tokensFor(file, shell, theme, false);
      const borderName = prefix === "skill" ? "border-strong" : "border";
      expect(resolve(`--${prefix}-${borderName}`)).toBe(border);
      if (prefix !== "skill") {
        expect(resolve(`--${prefix}-border-hover`)).not.toContain("color-mix(");
      }
      for (const surface of surfaces) {
        expect(resolve(`--${prefix}-${surface}`)).not.toContain("color-mix(");
      }
    });

    test(`${shell} preserves mixed border colors on supported engines in ${
      theme || "light"
    }`, () => {
      const resolve = tokensFor(file, shell, theme, true);
      expect(
        resolve(
          `--${prefix}-${prefix === "skill" ? "border-strong" : "border"}`,
        ),
      ).toContain("color-mix(");
    });
  }
}
