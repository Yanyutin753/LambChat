import { describe, expect, test } from "vitest";
import {
  areAttachmentsSendable,
  filterSendableAttachments,
  isAttachmentSendable,
} from "../attachmentValidation";

const valid = {
  id: "file-1",
  key: "uploads/file-1",
  name: "photo.png",
  type: "image" as const,
  mimeType: "image/png",
  size: 10,
  url: "/api/files/file-1",
};

describe("attachmentValidation", () => {
  test("rejects incomplete or failed uploads", () => {
    expect(isAttachmentSendable({ ...valid, key: "" })).toBe(false);
    expect(isAttachmentSendable({ ...valid, isUploading: true })).toBe(false);
    expect(isAttachmentSendable({ ...valid, uploadError: "gone" })).toBe(false);
  });

  test("accepts only when every attachment is sendable", () => {
    expect(areAttachmentsSendable([valid])).toBe(true);
    expect(
      areAttachmentsSendable([valid, { ...valid, id: "bad", key: "" }]),
    ).toBe(false);
  });

  test("filters unusable attachments before a message is submitted", () => {
    const invalid = { ...valid, id: "bad", key: "" };
    expect(filterSendableAttachments([valid, invalid])).toEqual([valid]);
  });
});
