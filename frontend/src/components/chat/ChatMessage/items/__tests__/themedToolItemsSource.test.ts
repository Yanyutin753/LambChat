import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

const themedItems = [
  { file: "../ImageGenerateItem.tsx", accent: "violet" },
  { file: "../AudioTranscribeItem.tsx", accent: "violet" },
  { file: "../ScheduledTaskItem.tsx", accent: "emerald" },
  { file: "../EnvVarItem.tsx", accent: "emerald" },
  { file: "../PersonaItem.tsx", accent: "amber" },
  { file: "../TeamItem.tsx", accent: "emerald" },
  { file: "../SandboxMcpItem.tsx", accent: "teal" },
];

test("internal tool items keep accents while using theme surfaces", () => {
  for (const { file, accent } of themedItems) {
    const source = readSource(file);

    expect(source).toMatch(new RegExp(`text-${accent}-[0-9]`));
    expect(source).toMatch(/bg-theme-bg/);
    expect(source).toMatch(/border-theme-border/);
  }
});

test("sandbox MCP renders as a teal terminal card instead of a stone panel", () => {
  const source = readSource("../SandboxMcpItem.tsx");

  expect(source).toMatch(/Terminal/);
  expect(source).toMatch(/text-teal-500/);
  expect(source).toMatch(/bg-teal-950/);
  expect(source).toMatch(/border-teal-500\/20/);
  expect(source).toMatch(/command\.length > 120/);
  expect(source).not.toMatch(/bg-stone-900|dark:bg-stone-950/);
});
