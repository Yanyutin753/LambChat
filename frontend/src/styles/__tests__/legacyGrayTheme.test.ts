import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import postcss from "postcss";
import tailwindcss from "tailwindcss";
import loadConfig from "tailwindcss/loadConfig.js";
import { expect, test } from "vitest";

test("legacy gray utilities follow neutral dark tokens and retain opacity modifiers", async () => {
  const tokens = readFileSync(
    new URL("../tokens.css", import.meta.url),
    "utf8",
  );
  const dark = tokens.slice(
    tokens.indexOf(".dark {"),
    tokens.indexOf(".theme-sepia {"),
  );
  const shades = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];
  const result = await postcss([
    tailwindcss({
      ...loadConfig(
        fileURLToPath(new URL("../../../tailwind.config.js", import.meta.url)),
      ),
      content: [
        {
          raw: shades
            .map(
              (shade) =>
                `dark:bg-stone-${shade}/50 dark:border-stone-${shade} dark:text-stone-${shade}`,
            )
            .join(" "),
          extension: "html",
        },
      ],
    }),
  ]).process("@tailwind utilities;", { from: undefined });

  for (const shade of shades) {
    expect(result.css, `stone-${shade}`).toContain(
      `var(--theme-neutral-${shade},`,
    );
    const match = dark.match(
      new RegExp(`--theme-neutral-${shade}: (#\\w{6});`),
    );
    expect(match, `dark shade ${shade}`).not.toBeNull();
    const rgb = match![1]
      .match(/[a-f\d]{2}/gi)!
      .map((value) => parseInt(value, 16));
    expect(Math.max(...rgb) - Math.min(...rgb)).toBe(0);
  }
  expect(result.css).toContain("calc(0.5 * 100%)");
  expect(result.css).not.toContain("<alpha-value>");
});

test("shared dark panel styles do not override neutral utilities with warm gray literals", () => {
  const warmGray =
    /#(?:fafaf9|f5f5f4|e7e5e4|d6d3d1|a8a29e|78716c|57534e|44403c|292524|1c1917)\b|rgba?\((?:168, 162, 158|120, 113, 108)/i;
  for (const file of [
    "base.css",
    "components.css",
    "card-base.css",
    "markdown.css",
    "skill.css",
    "team.css",
  ]) {
    const css = postcss.parse(
      readFileSync(new URL(`../${file}`, import.meta.url), "utf8"),
    );
    css.walkRules((rule) => {
      if (!rule.selector.includes(".dark")) return;
      rule.walkDecls((decl) => {
        if (!decl.value.includes("var(")) {
          expect(
            decl.value,
            `${file}: ${rule.selector} ${decl.prop}`,
          ).not.toMatch(warmGray);
        }
      });
    });
  }
});
