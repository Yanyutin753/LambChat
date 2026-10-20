import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = (name: string) =>
  readFileSync(new URL(`../${name}.tsx`, import.meta.url), "utf8");
const css = readFileSync(
  new URL("../../../../../styles/components.css", import.meta.url),
  "utf8",
);

test.each(["ReadFileItem", "WriteFileItem", "GrepItem", "EditFileItem"])(
  "%s keeps search and content copy in a separate editor toolbar",
  (name) => {
    const detail = source(name).split(`const ${name} =`)[0];
    expect(detail).toMatch(/<DeferredCodeMirrorViewer[\s\S]*?\bcopyable\b/);
    expect(detail).toMatch(/toolbarLabel=\{/);
    expect(detail).not.toMatch(/position="panel"/);
  },
);

test("tool panels theme the editor surface and keep content clear of its toolbar", () => {
  expect(css).toMatch(
    /\.tool-console-body__content\s*\{[^}]*--theme-bg-code:\s*var\(--theme-bg-card\)/,
  );
  expect(css).toMatch(
    /\.tool-panel-code \.code-editor-toolbar\s*\{[^}]*border-bottom:/,
  );
  const viewer = readFileSync(
    new URL("../../../../common/CodeMirrorViewer.tsx", import.meta.url),
    "utf8",
  );
  expect(viewer).not.toContain('isDark ? "#282c34"');
});

test.each([
  "WebSearchItem",
  "WebFetchItem",
  "ToolSearchItem",
  "SkillSearchItem",
  "TransferItem",
  "UploadUrlToSandboxItem",
])("%s detail uses the shared panel reading edge", (name) => {
  const detail = source(name).split(`const ${name} =`)[0];
  expect(detail).toMatch(/className="[^"]*tool-panel-content/);
});

// A partial read already contains only the requested lines; a second absolute
// highlight would scroll into the middle and tint the wrong lines.
test("partial file reads keep the original line numbers without a second highlight", () => {
  const read = source("ReadFileItem");
  expect(read).toContain("startLine={startLine}");
  expect(read).not.toContain("highlightLineRange=");
});

test("flat metadata does not strip the inset from a diff card header", () => {
  expect(css).toMatch(
    /\.tool-args-block\[data-size="detail"\]:not\(\.ai-file-diff__header\)/,
  );
});

test("panel content respects the reduced motion setting", () => {
  const reducedMotion = css
    .match(/@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\n\}/g)
    ?.find((block) => block.includes(".tool-console-panel"));
  expect(reducedMotion).toMatch(
    /\.tool-panel-content[\s\S]*animation: none !important/,
  );
});
