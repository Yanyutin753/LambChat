import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("chat markdown rendering does not statically import CodeMirrorViewer", () => {
  const source = readSource("./ChatMessage/MarkdownContent.tsx");

  assert.doesNotMatch(
    source,
    /import\s+\{?\s*CodeMirrorViewer\s*\}?\s+from\s+"..\/..\/common\/CodeMirrorViewer";/,
  );
  assert.match(source, /DeferredCodeMirrorViewer/);
});

test("chat tool result items keep CodeMirrorViewer behind a lazy wrapper", () => {
  const files = [
    "./ChatMessage/items/ReadFileItem.tsx",
    "./ChatMessage/items/GrepItem.tsx",
    "./ChatMessage/items/WriteFileItem.tsx",
    "./ChatMessage/items/EditFileItem.tsx",
  ];

  for (const file of files) {
    const source = readSource(file);
    assert.doesNotMatch(
      source,
      /import\s+\{?\s*CodeMirrorViewer\s*\}?\s+from\s+"..\/..\/..\/common\/CodeMirrorViewer";/,
      `${file} should not statically import CodeMirrorViewer`,
    );
    assert.match(
      source,
      /DeferredCodeMirrorViewer/,
      `${file} should render the deferred wrapper instead`,
    );
  }
});

test("chat preview hosts do not statically import heavy preview panels", () => {
  const attachmentPreviewHost = readSource("./AttachmentPreviewHost.tsx");
  assert.doesNotMatch(
    attachmentPreviewHost,
    /import\s+DocumentPreview\s+from\s+"..\/documents\/DocumentPreview";/,
  );
  assert.match(attachmentPreviewHost, /LazyDocumentPreview/);

  const revealPreviewHost = readSource(
    "./ChatMessage/items/RevealPreviewHost.tsx",
  );
  assert.doesNotMatch(
    revealPreviewHost,
    /import\s+DocumentPreview\s+from\s+"..\/..\/..\/documents\/DocumentPreview";/,
  );
  assert.doesNotMatch(
    revealPreviewHost,
    /import\s+ProjectPreview\s+from\s+"..\/..\/..\/documents\/previews\/ProjectPreview";/,
  );
  assert.match(revealPreviewHost, /LazyDocumentPreview/);
  assert.match(revealPreviewHost, /LazyProjectPreview/);
});

test("project reveal items keep ProjectPreview behind a lazy wrapper", () => {
  const source = readSource("./ChatMessage/items/ProjectRevealItem.tsx");

  assert.doesNotMatch(
    source,
    /import\s+ProjectPreview\s+from\s+"..\/..\/..\/documents\/previews\/ProjectPreview";/,
  );
  assert.match(source, /LazyProjectPreview/);
});
