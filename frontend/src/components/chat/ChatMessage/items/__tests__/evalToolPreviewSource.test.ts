import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

test("eval tool has a dedicated item with code preview", () => {
  const source = readSource("../EvalItem.tsx");

  assert.match(source, /function isEvalToolName/);
  assert.match(source, /function getEvalCodePreview/);
  assert.match(source, /function getEvalPillSummary/);
  assert.match(source, /Code2 size=\{12\}/);
  assert.match(source, /label=\{pillLabel\}/);
  assert.match(source, /formatLabel=\{false\}/);
  assert.match(source, /chat\.message\.codePreview/);
});

test("generic tool calls include an argument summary in the pill label", () => {
  const source = readSource("../../ToolCallItem.tsx");

  assert.match(source, /function buildToolPillSummary/);
  assert.match(source, /const pillLabel = pillSummary/);
  assert.match(source, /label=\{pillLabel\}/);
  assert.match(source, /formatLabel=\{false\}/);
});

test("eval code preview uses theme-aware surfaces", () => {
  const source = readSource("../EvalItem.tsx");

  assert.match(source, /eval-code-preview/);
  assert.doesNotMatch(source, /bg-stone-950|text-stone-100/);
});

test("message part renderer routes eval tools to the dedicated item for all agents", () => {
  const source = readSource("../../MessagePartRenderer.tsx");

  assert.match(source, /part\.name\s*===\s*"eval"/);
  assert.match(source, /<EvalItem/);
  assert.match(source, /<ToolCallItem/);
});
