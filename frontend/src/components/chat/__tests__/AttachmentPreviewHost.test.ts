import { readFileSync } from "node:fs";
test("attachment preview host is mounted at ChatView level", () => {
  const chatViewSource = readFileSync(
    new URL("../../layout/AppContent/ChatView.tsx", import.meta.url),
    "utf8",
  );

  expect(chatViewSource).toMatch(
    /<AttachmentPreviewHost runtimePlugins=\{runtimePlugins\} \/>/,
  );
});

test("attachment preview host fills the mobile viewport", () => {
  const attachmentPreviewHostSource = readFileSync(
    new URL("../AttachmentPreviewHost.tsx", import.meta.url),
    "utf8",
  );

  expect(attachmentPreviewHostSource).toMatch(
    /<LazyDocumentPreview[\s\S]*?\bmobileFillViewport\b[\s\S]*?\/>/,
  );
});
