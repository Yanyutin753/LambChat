import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import postcss from "postcss";
import tailwindcss from "@tailwindcss/postcss";
import { expect, test } from "vitest";

test("tool reading typography compiles with monospace utilities without a cycle", async () => {
  const css = ["components.css", "animations.css"]
    .map((file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8"))
    .join("\n");
  const result = await postcss([
    tailwindcss({ base: fileURLToPath(new URL("../../../", import.meta.url)) }),
  ]).process(css, {
    from: fileURLToPath(new URL("../typography-test.css", import.meta.url)),
  });
  expect(result.css).not.toContain("@apply");
  expect(result.css).toContain("Source Serif 4");
});


test.each(["base.css", "animations.css", "landing.css", "components.css", "auth.css"])(
  "%s resolves its shared Tailwind reference",
  async (file) => {
    const source = new URL(`../${file}`, import.meta.url);
    const result = await postcss([tailwindcss()]).process(
      readFileSync(source, "utf8"),
      { from: fileURLToPath(source) },
    );
    expect(result.css).not.toContain("@reference");
    expect(result.css).not.toContain("@apply");
  },
);


test("production utilities exclude test fixtures while retaining application styles", async () => {
  const source = new URL("../tailwind.css", import.meta.url);
  const { css } = await postcss([tailwindcss()]).process(
    readFileSync(source, "utf8"),
    { from: fileURLToPath(source) },
  );
  const testOnlyUtility = "z-[8675309]";
  expect(css).not.toContain(testOnlyUtility.replace("[", "\\[").replace("]", "\\]"));
  expect(css).not.toContain("z-index: 8675309");
  expect(css).toContain(".items-center");
  expect(css).toContain("var(--theme-border)");
});
