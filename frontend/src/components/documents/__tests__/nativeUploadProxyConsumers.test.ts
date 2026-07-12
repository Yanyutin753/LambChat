import { readFileSync } from "node:fs";
function source(path: string): string {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

test("known upload file content fetchers use the native-app upload proxy helper", () => {
  const consumers = [
    "../useDocumentPreviewState.ts",
    "../previews/ExcalidrawCardPreview.tsx",
    "../previews/ExcalidrawDirectViewer.tsx",
    "../../common/ExcalidrawThumbnail.tsx",
    "../../fileLibrary/hooks/useCodePreview.ts",
    "../../chat/ChatMessage/items/revealPreviewData.ts",
    "../../../utils/exportProjectZip.ts",
  ];

  for (const relativePath of consumers) {
    expect(source(relativePath)).toMatch(/buildUploadProxyUrl/);
  }
});
