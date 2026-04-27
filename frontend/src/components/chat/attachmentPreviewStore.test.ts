import assert from "node:assert/strict";
import test from "node:test";
import {
  closeAttachmentPreview,
  getAttachmentPreviewState,
  openAttachmentPreview,
} from "./attachmentPreviewStore";

test("attachment preview store preserves the selected attachment until explicitly closed", () => {
  closeAttachmentPreview();

  openAttachmentPreview(
    {
      id: "a1",
      key: "uploads/a1.txt",
      name: "a1.txt",
      type: "document",
      mimeType: "text/plain",
      size: 12,
    },
    "chat-input",
  );

  assert.deepEqual(getAttachmentPreviewState()?.source, "chat-input");
  assert.deepEqual(
    getAttachmentPreviewState()?.attachment.key,
    "uploads/a1.txt",
  );

  openAttachmentPreview(
    {
      id: "a2",
      key: "uploads/a2.txt",
      name: "a2.txt",
      type: "document",
      mimeType: "text/plain",
      size: 24,
    },
    "user-message",
  );

  assert.deepEqual(getAttachmentPreviewState()?.source, "user-message");
  assert.deepEqual(
    getAttachmentPreviewState()?.attachment.key,
    "uploads/a2.txt",
  );

  closeAttachmentPreview();
  assert.equal(getAttachmentPreviewState(), null);
});
