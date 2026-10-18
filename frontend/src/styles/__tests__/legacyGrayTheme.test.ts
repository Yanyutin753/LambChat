import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import postcss from "postcss";
import tailwindcss from "@tailwindcss/postcss";
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
    tailwindcss({ base: fileURLToPath(new URL("../../../", import.meta.url)) }),
  ]).process(
    `@import "../tailwind.css";
@source inline("${shades
      .map(
        (shade) =>
          `dark:bg-stone-${shade}/50 dark:border-stone-${shade} dark:text-stone-${shade}`,
      )
      .join(" ")}");`,
    {
      from: fileURLToPath(new URL("./neutral-test.css", import.meta.url)),
    },
  );

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
  expect(result.css).toMatch(/(?:50%|calc\(0\.5 \* 100%\))/);
  expect(result.css).not.toContain("<alpha-value>");
});

test("sepia theme defines a complete warm neutral scale for legacy stone utilities", () => {
  const tokens = readFileSync(
    new URL("../tokens.css", import.meta.url),
    "utf8",
  );
  const sepia = tokens.slice(tokens.indexOf(".theme-sepia {"));
  const shades = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];
  let previousLuma = Infinity;
  for (const shade of shades) {
    const match = sepia.match(
      new RegExp(`--theme-neutral-${shade}: (#\\w{6});`),
    );
    expect(match, `sepia shade ${shade}`).not.toBeNull();
    const [r, g, b] = match![1]
      .match(/[a-f\d]{2}/gi)!
      .map((value) => parseInt(value, 16));
    // 暖调（R>G>B）：sepia 下 stone 类须变米黄/暖褐，而非 fallback 的原生冷暖灰
    expect(r, `sepia neutral-${shade} R>G`).toBeGreaterThan(g);
    expect(g, `sepia neutral-${shade} G>B`).toBeGreaterThan(b);
    // 刻度单调递深，防止插档错乱
    const luma = (r + g + b) / 3;
    expect(luma, `sepia neutral-${shade} luma decreasing`).toBeLessThan(
      previousLuma,
    );
    previousLuma = luma;
  }
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

test("Tailwind 4 keeps legacy shrink, outline, and theme-alpha utilities available", async () => {
  const result = await postcss([
    tailwindcss({ base: fileURLToPath(new URL("../../../", import.meta.url)) }),
  ]).process(
    `@import "../tailwind.css";
@source inline("flex-shrink-0 outline-hidden border-theme-border/60 rounded-sm shadow-sm");`,
    {
      from: fileURLToPath(new URL("./compatibility-test.css", import.meta.url)),
    },
  );
  expect(result.css).toContain("flex-shrink: 0");
  expect(result.css).toMatch(/forced-colors:\s*active/);
  expect(result.css).toContain("var(--theme-border)");
  expect(result.css).not.toContain("<alpha-value>");
  expect(result.css).toContain("0.125rem");
});
