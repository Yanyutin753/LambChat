import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function readRepoFile(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../..", ...segments),
    "utf8",
  );
}

test("tailwind config defines the serif stack led by Source Serif 4", () => {
  const config = readRepoFile("tailwind.config.js");

  expect(config).toMatch(/serif:\s*\[\s*"['"]Source Serif 4['"]"/);
});

test("serif stack avoids Georgia whose old-style digits drop below the baseline", () => {
  const config = readRepoFile("tailwind.config.js");
  const serifStack = config.match(/serif:\s*\[([\s\S]*?)\]/)?.[1] ?? "";

  expect(serifStack).not.toMatch(/Georgia/);
});

test("serif stack falls back to CJK serif fonts before the generic family", () => {
  const config = readRepoFile("tailwind.config.js");

  expect(config).toMatch(/Noto Serif SC/);
  expect(config).toMatch(/,\s*"serif",?\s*\]/);
});

test("fonts are self-hosted: no Google Fonts origin, local @font-face with swap", () => {
  const html = readRepoFile("index.html");
  const fontsCss = readRepoFile("src/fonts.css");
  const main = readRepoFile("src/main.tsx");

  expect(html).not.toMatch(/fonts\.googleapis\.com/);
  expect(html).not.toMatch(/fonts\.gstatic\.com/);
  expect(html).toMatch(/\/fonts\/source-sans-3-400-latin\.woff2/);
  expect(fontsCss).toMatch(/font-family:\s*['"]Source Serif 4['"]/);
  expect(fontsCss).toMatch(/font-family:\s*['"]Source Sans 3['"]/);
  expect(fontsCss).toMatch(/font-display:\s*swap/);
  expect(main).toMatch(/import\s+"\.\/fonts\.css"/);
});

test("font-serif utility forces lining numerals so digits share the text baseline", () => {
  const utilities = readRepoFile("src/styles/utilities.css");

  expect(utilities).toMatch(
    /\.font-serif\s*\{[^}]*font-variant-numeric:\s*lining-nums/s,
  );
});
