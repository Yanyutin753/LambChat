import {
  closeAttachmentPreview,
  getAttachmentPreviewState,
  openAttachmentPreview,
} from "../attachmentPreviewStore";

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

  expect(getAttachmentPreviewState()?.source).toEqual("chat-input");
  expect(getAttachmentPreviewState()?.attachment.key).toEqual("uploads/a1.txt");

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

  expect(getAttachmentPreviewState()?.source).toEqual("user-message");
  expect(getAttachmentPreviewState()?.attachment.key).toEqual("uploads/a2.txt");

  closeAttachmentPreview();
  expect(getAttachmentPreviewState()).toBe(null);
});
