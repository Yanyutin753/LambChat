import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

test("file and project reveal status cards share title and subtitle text", () => {
  const source = readSource("../RevealStatusText.tsx");
  const fileReveal = readSource("../FileRevealItem.tsx");
  const projectReveal = readSource("../ProjectRevealItem.tsx");

  expect(source).toMatch(/export function RevealStatusText/);
  expect(source).toMatch(/export function RevealStatusLabel/);
  expect(source).toMatch(
    /text-sm font-medium text-theme-text-secondary truncate/,
  );
  expect(source).toMatch(/text-xs text-theme-text-tertiary truncate mt-0\.5/);
  expect(source).toMatch(/text-xs text-amber-600 dark:text-amber-400/);

  for (const consumer of [fileReveal, projectReveal]) {
    expect(consumer).toMatch(
      /import \{ RevealStatusLabel, RevealStatusText \} from "\.\/RevealStatusText"/,
    );
    expect(consumer).toMatch(/<RevealStatusText[\s\S]*title=/);
    expect(consumer).toMatch(/<RevealStatusLabel>/);
    expect(consumer).not.toMatch(
      /text-sm font-medium text-theme-text-secondary truncate/,
    );
    expect(consumer).not.toMatch(
      /text-xs text-theme-text-tertiary truncate mt-0\.5/,
    );
    expect(consumer).not.toMatch(/text-xs text-amber-600 dark:text-amber-400/);
  }
});
