import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import postcss from "postcss";
import tailwindcss from "tailwindcss";
import loadConfig from "tailwindcss/loadConfig.js";
import { expect, test } from "vitest";

test("tool reading typography compiles with monospace utilities without a cycle", async () => {
  const css = ["components.css", "animations.css"]
    .map((file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8"))
    .join("\n");
  const result = await postcss([
    tailwindcss({
      ...loadConfig(
        fileURLToPath(new URL("../../../tailwind.config.js", import.meta.url)),
      ),
      content: [
        {
          raw: "font-mono font-serif pill-btn tool-readable tool-args-block",
          extension: "html",
        },
      ],
    }),
  ]).process(`@tailwind utilities;\n${css}`, { from: undefined });
  expect(result.css).not.toContain("@apply");
  expect(result.css).toContain("Source Serif 4");
});
