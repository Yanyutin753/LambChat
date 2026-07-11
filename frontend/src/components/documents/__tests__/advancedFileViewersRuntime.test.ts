import { readFileSync } from "node:fs";
function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("document preview gates advanced viewers through plugin runtime state", () => {
  const stateSource = readSource("../useDocumentPreviewState.ts");
  const contentSource = readSource("../DocumentPreviewContent.tsx");

  expect(stateSource).toMatch(/runtimePlugins\?: PluginRuntimeContributionStates/);
  expect(stateSource).toMatch(/hasFileViewerContribution\("code", runtimePlugins\)/);
  expect(stateSource).toMatch(/hasPluginAssetSlot\("file_viewer", runtimePlugins\)/);
  expect(stateSource).not.toMatch(/runtimePlugins === undefined/);
  expect(stateSource).toMatch(/advancedFileViewersEnabled && resolvedPdfFile/);
  expect(stateSource).toMatch(/advancedFileViewersEnabled && cadFile/);
  expect(stateSource).toMatch(/advancedFileViewersEnabled && \(wordPreviewFile \|\| excelFile\)/);
  expect(contentSource).toMatch(/!advancedFileViewersEnabled/);
  expect(contentSource).toMatch(/<FileFallbackPanel/);
});

test("chat preview hosts pass runtime state into document preview", () => {
  const attachmentHost = readSource("../../chat/AttachmentPreviewHost.tsx");
  const revealHost = readSource(
    "../../chat/ChatMessage/items/RevealPreviewHost.tsx",
  );
  const chatView = readSource("../../layout/AppContent/ChatView.tsx");

  expect(attachmentHost).toMatch(/runtimePlugins\?: PluginRuntimeContributionStates/);
  expect(attachmentHost).toMatch(/runtimePlugins=\{runtimePlugins\}/);
  expect(revealHost).toMatch(/runtimePlugins\?: PluginRuntimeContributionStates/);
  expect(revealHost).toMatch(/runtimePlugins=\{runtimePlugins\}/);
  expect(chatView).toMatch(/<AttachmentPreviewHost runtimePlugins=\{runtimePlugins\}/);
  expect(chatView).toMatch(/<RevealPreviewHost[\s\S]*runtimePlugins=\{runtimePlugins\}/);
});

test("file library gates advanced viewer shortcuts through the plugin asset slot", () => {
  const fileLibrarySource = readSource("../../fileLibrary/RevealedFilesPanel.tsx");

  expect(fileLibrarySource).toMatch(/hasFileViewerContribution\("code", runtimePlugins\)/);
  expect(fileLibrarySource).toMatch(/hasPluginAssetSlot\("file_viewer", runtimePlugins\)/);
  expect(fileLibrarySource).not.toMatch(/runtimePlugins === undefined/);
  expect(fileLibrarySource).toMatch(/advancedFileViewersEnabled && file\.url && isExcalidrawFile/);
});
