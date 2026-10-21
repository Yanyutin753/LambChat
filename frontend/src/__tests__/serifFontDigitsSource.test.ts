import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function readRepoFile(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../..", ...segments),
    "utf8",
  );
}

test("legacy font-serif shares the Windows/Linux titlebar system font", () => {
  const config = readRepoFile("tailwind.config.js");
  const tokens = readRepoFile("src/styles/tokens.css");
  const desktop = readRepoFile("src/styles/desktop.css");

  expect(config).toMatch(/serif:\s*\["var\(--desktop-ui-font\)"\]/);
  expect(tokens).toMatch(
    /:root\s*\{[^}]*--desktop-ui-font:\s*-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;/s,
  );
  expect(desktop).toMatch(
    /\[data-titlebar\][^{}]*\{\s*font-family: var\(--desktop-ui-font\);/,
  );
  expect(desktop).not.toMatch(/--desktop-ui-font\s*:/);
});

test("legacy font-serif avoids Georgia and its old-style digits", () => {
  const config = readRepoFile("tailwind.config.js");
  const serifStack = config.match(/serif:\s*\[([\s\S]*?)\]/)?.[1] ?? "";

  expect(serifStack).not.toMatch(/Georgia/);
});

test("legacy font-serif does not force a CJK serif fallback", () => {
  const config = readRepoFile("tailwind.config.js");
  const serifStack = config.match(/serif:\s*\[([\s\S]*?)\]/)?.[1] ?? "";

  expect(serifStack).not.toMatch(/Noto Serif|Cambria|Times|SimSun/);
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
