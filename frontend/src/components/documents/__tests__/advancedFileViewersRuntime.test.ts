import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("document preview gates advanced viewers through plugin runtime state", () => {
  const stateSource = readSource("../useDocumentPreviewState.ts");
  const contentSource = readSource("../DocumentPreviewContent.tsx");

  assert.match(stateSource, /runtimePlugins\?: PluginRuntimeContributionStates/);
  assert.match(stateSource, /hasFileViewerContribution\("code", runtimePlugins\)/);
  assert.match(stateSource, /hasPluginAssetSlot\("file_viewer", runtimePlugins\)/);
  assert.match(stateSource, /advancedFileViewersEnabled && resolvedPdfFile/);
  assert.match(stateSource, /advancedFileViewersEnabled && cadFile/);
  assert.match(stateSource, /advancedFileViewersEnabled && \(wordPreviewFile \|\| excelFile\)/);
  assert.match(contentSource, /!advancedFileViewersEnabled/);
  assert.match(contentSource, /<FileFallbackPanel/);
});

test("chat preview hosts pass runtime state into document preview", () => {
  const attachmentHost = readSource("../../chat/AttachmentPreviewHost.tsx");
  const revealHost = readSource(
    "../../chat/ChatMessage/items/RevealPreviewHost.tsx",
  );
  const chatView = readSource("../../layout/AppContent/ChatView.tsx");

  assert.match(attachmentHost, /runtimePlugins\?: PluginRuntimeContributionStates/);
  assert.match(attachmentHost, /runtimePlugins=\{runtimePlugins\}/);
  assert.match(revealHost, /runtimePlugins\?: PluginRuntimeContributionStates/);
  assert.match(revealHost, /runtimePlugins=\{runtimePlugins\}/);
  assert.match(chatView, /<AttachmentPreviewHost runtimePlugins=\{runtimePlugins\}/);
  assert.match(chatView, /<RevealPreviewHost[\s\S]*runtimePlugins=\{runtimePlugins\}/);
});

test("file library gates advanced viewer shortcuts through the plugin asset slot", () => {
  const fileLibrarySource = readSource("../../fileLibrary/RevealedFilesPanel.tsx");

  assert.match(fileLibrarySource, /hasFileViewerContribution\("code", runtimePlugins\)/);
  assert.match(fileLibrarySource, /hasPluginAssetSlot\("file_viewer", runtimePlugins\)/);
  assert.match(fileLibrarySource, /advancedFileViewersEnabled && file\.url && isExcalidrawFile/);
});
