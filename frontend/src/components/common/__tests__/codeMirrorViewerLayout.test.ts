import { readFileSync } from "node:fs";
function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("CodeMirrorViewer fills the available parent height by default", () => {
  const source = readSource("../CodeMirrorViewer.tsx");

  expect(source).toMatch(/"\.cm-editor":\s*\{\s*height:\s*"100%"/);
  expect(source).toMatch(/"\.cm-scroller":\s*\{[\s\S]*height:\s*"100%"/);
  expect(source).toMatch(
    /"\.cm-content":\s*\{\s*minHeight:\s*"100% !important"/,
  );
  expect(source).toMatch(
    /"\.cm-gutters, \.cm-gutter":\s*\{[\s\S]*minHeight:\s*"100% !important"/,
  );
  expect(source).toMatch(/isDark \? "#282c34" : "#ffffff"/);
  expect(source).toMatch(/isDark \? "#282c34" : "#fafafa"/);
  expect(source).toMatch(/<CodeMirror[\s\S]*className="h-full"/);
  expect(source).toMatch(/<CodeMirror[\s\S]*height="100%"/);
  expect(source).toMatch(/copyable \? "group relative h-full"/);
});

test("CodeMirrorViewer exposes selected preview text to native copy", () => {
  const source = readSource("../CodeMirrorViewer.tsx");

  expect(source).toMatch(/function getSelectedText/);
  expect(source).toMatch(/state\.selection\.ranges/);
  expect(source).toMatch(/EditorView\.domEventHandlers\(\{\s*copy:/);
  expect(source).toMatch(
    /event\.clipboardData\.setData\("text\/plain", selectedText\)/,
  );
  expect(source).toMatch(/event\.preventDefault\(\)/);
  expect(source).toMatch(/"\.cm-content":\s*\{[\s\S]*userSelect:\s*"text"/);
  expect(source).toMatch(/"\.cm-line":\s*\{[\s\S]*userSelect:\s*"text"/);
  expect(source).toMatch(
    /"\.cm-lineNumbers \.cm-gutterElement":\s*\{[\s\S]*userSelect:\s*"none"/,
  );
});

test("CodeMirrorViewer keeps the selection layer visible", () => {
  const source = readSource("../CodeMirrorViewer.tsx");

  expect(source).toMatch(
    /"\.cm-content":\s*\{[\s\S]*backgroundColor:\s*"transparent !important"/,
  );
  expect(source).toMatch(/"\.cm-selectionLayer \.cm-selectionBackground,/);
  expect(source).toMatch(/"\.cm-content ::selection":\s*\{/);
  expect(source).toMatch(/rgba\(96, 165, 250, 0\.46\)/);
  expect(source).toMatch(/rgba\(37, 99, 235, 0\.26\)/);
});

test("DeferredCodeMirrorViewer fallback does not flash raw code", () => {
  const source = readSource("../DeferredCodeMirrorViewer.tsx");

  expect(source).toMatch(/LoadingSpinner/);
  expect(source).toMatch(/aria-label=\{loadingLabel\}/);
  expect(source).not.toMatch(/<pre[\s\S]*?\{value\}[\s\S]*?<\/pre>/);
});

test("document code preview relies on the shared viewer fill behavior", () => {
  const source = readSource("../../documents/previews/CodeRenderer.tsx");

  expect(source).not.toMatch(/\[&_\.cm-editor\]:h-full/);
  expect(source).not.toMatch(/\[&_\.cm-scroller\]:!overflow-auto/);
  expect(source).toMatch(/dark:bg-\[#282c34\]/);
  expect(source).toMatch(/className="h-full"/);
});
