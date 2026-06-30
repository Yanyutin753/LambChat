import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("CodeMirrorViewer fills the available parent height by default", () => {
  const source = readSource("../CodeMirrorViewer.tsx");

  assert.match(source, /"\.cm-editor":\s*\{\s*height:\s*"100%"/);
  assert.match(source, /"\.cm-scroller":\s*\{[\s\S]*height:\s*"100%"/);
  assert.match(source, /"\.cm-content":\s*\{\s*minHeight:\s*"100% !important"/);
  assert.match(
    source,
    /"\.cm-gutters, \.cm-gutter":\s*\{[\s\S]*minHeight:\s*"100% !important"/,
  );
  assert.match(source, /isDark \? "#282c34" : "#ffffff"/);
  assert.match(source, /isDark \? "#282c34" : "#fafafa"/);
  assert.match(source, /<CodeMirror[\s\S]*className="h-full"/);
  assert.match(source, /<CodeMirror[\s\S]*height="100%"/);
  assert.match(source, /copyable \? "group relative h-full"/);
});

test("CodeMirrorViewer exposes selected preview text to native copy", () => {
  const source = readSource("../CodeMirrorViewer.tsx");

  assert.match(source, /function getSelectedText/);
  assert.match(source, /state\.selection\.ranges/);
  assert.match(source, /EditorView\.domEventHandlers\(\{\s*copy:/);
  assert.match(
    source,
    /event\.clipboardData\.setData\("text\/plain", selectedText\)/,
  );
  assert.match(source, /event\.preventDefault\(\)/);
  assert.match(source, /"\.cm-content":\s*\{[\s\S]*userSelect:\s*"text"/);
  assert.match(source, /"\.cm-line":\s*\{[\s\S]*userSelect:\s*"text"/);
  assert.match(
    source,
    /"\.cm-lineNumbers \.cm-gutterElement":\s*\{[\s\S]*userSelect:\s*"none"/,
  );
});

test("CodeMirrorViewer keeps the selection layer visible", () => {
  const source = readSource("../CodeMirrorViewer.tsx");

  assert.match(
    source,
    /"\.cm-content":\s*\{[\s\S]*backgroundColor:\s*"transparent !important"/,
  );
  assert.match(source, /"\.cm-selectionLayer \.cm-selectionBackground,/);
  assert.match(source, /"\.cm-content ::selection":\s*\{/);
  assert.match(source, /rgba\(96, 165, 250, 0\.46\)/);
  assert.match(source, /rgba\(37, 99, 235, 0\.26\)/);
});

test("DeferredCodeMirrorViewer fallback does not flash raw code", () => {
  const source = readSource("../DeferredCodeMirrorViewer.tsx");

  assert.match(source, /LoadingSpinner/);
  assert.match(source, /aria-label=\{loadingLabel\}/);
  assert.doesNotMatch(
    source,
    /<pre[\s\S]*?\{value\}[\s\S]*?<\/pre>/,
    "lazy CodeMirror fallback should not render raw source before highlighting loads",
  );
});

test("document code preview relies on the shared viewer fill behavior", () => {
  const source = readSource("../../documents/previews/CodeRenderer.tsx");

  assert.doesNotMatch(source, /\[&_\.cm-editor\]:h-full/);
  assert.doesNotMatch(source, /\[&_\.cm-scroller\]:!overflow-auto/);
  assert.match(source, /dark:bg-\[#282c34\]/);
  assert.match(source, /className="h-full"/);
});
