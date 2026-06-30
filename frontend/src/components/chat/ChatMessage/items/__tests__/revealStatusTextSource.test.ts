import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

test("file and project reveal status cards share title and subtitle text", () => {
  const source = readSource("../RevealStatusText.tsx");
  const fileReveal = readSource("../FileRevealItem.tsx");
  const projectReveal = readSource("../ProjectRevealItem.tsx");

  assert.match(source, /export function RevealStatusText/);
  assert.match(source, /export function RevealStatusLabel/);
  assert.match(
    source,
    /text-sm font-medium text-theme-text-secondary truncate/,
  );
  assert.match(source, /text-xs text-theme-text-tertiary truncate mt-0\.5/);
  assert.match(source, /text-xs text-amber-600 dark:text-amber-400/);

  for (const consumer of [fileReveal, projectReveal]) {
    assert.match(
      consumer,
      /import \{ RevealStatusLabel, RevealStatusText \} from "\.\/RevealStatusText"/,
    );
    assert.match(consumer, /<RevealStatusText[\s\S]*title=/);
    assert.match(consumer, /<RevealStatusLabel>/);
    assert.doesNotMatch(
      consumer,
      /text-sm font-medium text-theme-text-secondary truncate/,
    );
    assert.doesNotMatch(
      consumer,
      /text-xs text-theme-text-tertiary truncate mt-0\.5/,
    );
    assert.doesNotMatch(consumer, /text-xs text-amber-600 dark:text-amber-400/);
  }
});
