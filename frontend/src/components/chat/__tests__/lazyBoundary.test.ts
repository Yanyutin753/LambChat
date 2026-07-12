import { readFileSync } from "node:fs";
function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("chat markdown rendering does not statically import CodeMirrorViewer", () => {
  const source = readSource("../ChatMessage/MarkdownContent.tsx");

  expect(source).not.toMatch(
    /import\s+\{?\s*CodeMirrorViewer\s*\}?\s+from\s+"..\/..\/common\/CodeMirrorViewer";/,
  );
  expect(source).toMatch(/DeferredCodeMirrorViewer/);
});

test("chat tool result items keep CodeMirrorViewer behind a lazy wrapper", () => {
  const files = [
    "../ChatMessage/items/ReadFileItem.tsx",
    "../ChatMessage/items/GrepItem.tsx",
    "../ChatMessage/items/WriteFileItem.tsx",
    "../ChatMessage/items/EditFileItem.tsx",
  ];

  for (const file of files) {
    const source = readSource(file);
    expect(source).not.toMatch(
      /import\s+\{?\s*CodeMirrorViewer\s*\}?\s+from\s+"..\/..\/..\/common\/CodeMirrorViewer";/,
    );
    expect(source).toMatch(/DeferredCodeMirrorViewer/);
  }
});

test("chat preview hosts do not statically import heavy preview panels", () => {
  const attachmentPreviewHost = readSource("../AttachmentPreviewHost.tsx");
  expect(attachmentPreviewHost).not.toMatch(
    /import\s+DocumentPreview\s+from\s+"..\/documents\/DocumentPreview";/,
  );
  expect(attachmentPreviewHost).toMatch(/LazyDocumentPreview/);

  const revealPreviewHost = readSource(
    "../ChatMessage/items/RevealPreviewHost.tsx",
  );
  expect(revealPreviewHost).not.toMatch(
    /import\s+DocumentPreview\s+from\s+"..\/..\/..\/documents\/DocumentPreview";/,
  );
  expect(revealPreviewHost).not.toMatch(
    /import\s+ProjectPreview\s+from\s+"..\/..\/..\/documents\/previews\/ProjectPreview";/,
  );
  expect(revealPreviewHost).toMatch(/LazyDocumentPreview/);
  expect(revealPreviewHost).toMatch(/LazyProjectPreview/);
});

test("project reveal items keep ProjectPreview behind a lazy wrapper", () => {
  const source = readSource("../ChatMessage/items/ProjectRevealItem.tsx");

  expect(source).not.toMatch(
    /import\s+ProjectPreview\s+from\s+"..\/..\/..\/documents\/previews\/ProjectPreview";/,
  );
  // ProjectRevealItem delegates preview rendering to RevealPreviewHost,
  // which in turn uses LazyProjectPreview — verified in the test above.
});
