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

  expect(config).toMatch(/serif:\s*\[\s*"'Source Serif 4'"/);
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

test("index.html loads Source Serif 4 with an async link and a noscript fallback", () => {
  const html = readRepoFile("index.html");

  const matches = html.match(/family=Source\+Serif\+4/g) ?? [];
  expect(matches.length).toBeGreaterThanOrEqual(2);
});

test("font-serif utility forces lining numerals so digits share the text baseline", () => {
  const utilities = readRepoFile("src/styles/utilities.css");

  expect(utilities).toMatch(
    /\.font-serif\s*\{[^}]*font-variant-numeric:\s*lining-nums/s,
  );
});
