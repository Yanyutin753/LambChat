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

test("chat and shared routes defer the entire reveal preview host", () => {
  for (const file of [
    "../../layout/AppContent/ChatView.tsx",
    "../../share/SharedPage.tsx",
  ]) {
    const source = readSource(file);
    expect(source).not.toMatch(/import\s+\{\s*RevealPreviewHost\s*\}/);
    expect(source).toContain("<LazyRevealPreviewHost");
  }
});

test("closed profile settings stay outside the chat shell's static imports", () => {
  const source = readSource("../../layout/AppContent/AppShell.tsx");
  expect(source).not.toMatch(/import\s+\{\s*ProfileModal\s*\}\s+from/);
  expect(source).toMatch(
    /lazy\([\s\S]*?import\("\.\.\/\.\.\/profile\/ProfileModal"\)/,
  );
  expect(source).toMatch(/showProfileModal\s*&&\s*\(/);
});

test("management routes do not statically load the chat workspace", () => {
  const source = readSource("../../layout/AppContent/index.tsx");
  for (const component of ["ChatAppContent", "NonChatAppContent"]) {
    expect(source).not.toMatch(
      new RegExp(`import\\s+\\{\\s*${component}\\s*\\}\\s+from`),
    );
    expect(source).toContain(`import("./${component}")`);
  }
});

test("ZIP compression loads when exporting rather than when rendering artifacts", () => {
  const source = readSource("../../../utils/exportProjectZip.ts");
  expect(source).not.toMatch(/import\s+JSZip\s+from\s+"jszip"/);
  expect(source).toMatch(/await import\("jszip"\)/);
});

test("startup error and PWA controls do not statically load the animated icon registry", () => {
  for (const file of [
    "../../common/ErrorBoundary.tsx",
    "../../common/ui/IconButton.tsx",
    "../../pwa/PwaStatusToasts.tsx",
  ]) {
    const source = readSource(file);
    expect(source).not.toMatch(/from "[^"]*\/InteractiveIcon"/);
    expect(source).toContain("DeferredInteractiveIcon");
  }
});
