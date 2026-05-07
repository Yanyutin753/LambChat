import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("attachment preview host is mounted at ChatView level", () => {
  const chatViewSource = readFileSync(
    new URL("../layout/AppContent/ChatView.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    chatViewSource,
    /<AttachmentPreviewHost\s*\/>/,
    "ChatView should mount a global attachment preview host outside ChatInput",
  );
});
