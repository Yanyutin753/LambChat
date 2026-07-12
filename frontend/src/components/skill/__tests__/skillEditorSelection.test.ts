import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../SkillEditor.tsx", import.meta.url),
  "utf8",
);

test("SkillEditor keeps CodeMirror text selection visible and selectable", () => {
  expect(source).toMatch(/"\.cm-content":\s*\{[\s\S]*minHeight:\s*"100%"/);
  expect(source).toMatch(
    /"\.cm-content":\s*\{[\s\S]*backgroundColor:\s*"transparent !important"/,
  );
  expect(source).toMatch(/"\.cm-content":\s*\{[\s\S]*userSelect:\s*"text"/);
  expect(source).toMatch(/"\.cm-content":\s*\{[\s\S]*caretColor:/);
  expect(source).toMatch(/"\.cm-cursor, \.cm-dropCursor":\s*\{/);
  expect(source).toMatch(/borderLeftColor:/);
  expect(source).toMatch(/"\.cm-focused":\s*\{/);
  expect(source).toMatch(/"\.cm-line":\s*\{[\s\S]*userSelect:\s*"text"/);
  expect(source).toMatch(/"\.cm-selectionLayer \.cm-selectionBackground,/);
  expect(source).toMatch(/"\.cm-content ::selection":\s*\{/);
  expect(source).toMatch(/rgba\(96, 165, 250, 0\.46\)/);
  expect(source).toMatch(/rgba\(37, 99, 235, 0\.26\)/);
  expect(source).toMatch(
    /"\.cm-lineNumbers \.cm-gutterElement":\s*\{[\s\S]*userSelect:\s*"none"/,
  );
});
