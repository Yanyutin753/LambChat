import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../SkillEditor.tsx", import.meta.url),
  "utf8",
);

test("SkillEditor keeps CodeMirror text selection visible and selectable", () => {
  assert.match(source, /"\.cm-content":\s*\{[\s\S]*minHeight:\s*"100%"/);
  assert.match(
    source,
    /"\.cm-content":\s*\{[\s\S]*backgroundColor:\s*"transparent !important"/,
  );
  assert.match(source, /"\.cm-content":\s*\{[\s\S]*userSelect:\s*"text"/);
  assert.match(source, /"\.cm-content":\s*\{[\s\S]*caretColor:/);
  assert.match(source, /"\.cm-cursor, \.cm-dropCursor":\s*\{/);
  assert.match(source, /borderLeftColor:/);
  assert.match(source, /"\.cm-focused":\s*\{/);
  assert.match(source, /"\.cm-line":\s*\{[\s\S]*userSelect:\s*"text"/);
  assert.match(source, /"\.cm-selectionLayer \.cm-selectionBackground,/);
  assert.match(source, /"\.cm-content ::selection":\s*\{/);
  assert.match(source, /rgba\(96, 165, 250, 0\.46\)/);
  assert.match(source, /rgba\(37, 99, 235, 0\.26\)/);
  assert.match(
    source,
    /"\.cm-lineNumbers \.cm-gutterElement":\s*\{[\s\S]*userSelect:\s*"none"/,
  );
});
