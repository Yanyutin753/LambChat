import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../ViewerToolbar.tsx", import.meta.url),
  "utf8",
);
const imageViewerSource = readFileSync(
  new URL("../ImageViewer.tsx", import.meta.url),
  "utf8",
);
const mermaidSource = readFileSync(
  new URL("../../chat/ChatMessage/MermaidDiagram.tsx", import.meta.url),
  "utf8",
);
const excalidrawSource = readFileSync(
  new URL("../../documents/previews/ExcalidrawPreview.tsx", import.meta.url),
  "utf8",
);

test("ViewerToolbar handles bottom safe-area through positioning, not padding", () => {
  expect(source).toMatch(
    /bottom-\[calc\(1rem\+var\(--app-safe-area-bottom,0px\)\)\]/,
  );
  expect(source).not.toMatch(/env\(safe-area/);
});

test("ViewerToolbar call sites avoid safe-area padding that shifts controls off center", () => {
  for (const consumerSource of [
    imageViewerSource,
    mermaidSource,
    excalidrawSource,
  ]) {
    expect(consumerSource).not.toMatch(
      /<ViewerToolbar[\s\S]*?className="safe-area-bottom"/,
    );
  }
});
