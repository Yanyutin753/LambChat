/** @vitest-environment jsdom */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { MessageAttachment } from "../../../types";
import { ChatInputAttachments } from "../ChatInputAttachments";

const uploadedAttachment: MessageAttachment = {
  id: "uploaded-1",
  key: "uploads/report.pdf",
  name: "report.pdf",
  type: "document",
  mimeType: "application/pdf",
  size: 2048,
  url: "/api/upload/file/uploads/report.pdf",
};

test("removing an uploaded draft attachment only updates local state", () => {
  const onAttachmentsChange = vi.fn();
  const onCancelUpload = vi.fn();
  render(
    <ChatInputAttachments
      attachments={[uploadedAttachment]}
      onAttachmentsChange={onAttachmentsChange}
      onCancelUpload={onCancelUpload}
      onImageViewerOpen={vi.fn()}
    />,
  );

  const card = screen.getByText("report.pdf").closest(".attachment-card-enter");
  expect(card).not.toBeNull();
  fireEvent.click(within(card as HTMLElement).getByRole("button"));

  const update = onAttachmentsChange.mock.calls[0]?.[0] as (
    previous: MessageAttachment[],
  ) => MessageAttachment[];
  expect(update([uploadedAttachment])).toEqual([]);
  expect(onCancelUpload).not.toHaveBeenCalled();
});

test("cancelling an in-flight attachment delegates to upload abort", () => {
  const uploadingAttachment: MessageAttachment = {
    ...uploadedAttachment,
    id: "temp-upload-1",
    key: "",
    name: "uploading.pdf",
    isUploading: true,
    uploadProgress: 40,
  };
  const onAttachmentsChange = vi.fn();
  const onCancelUpload = vi.fn();
  render(
    <ChatInputAttachments
      attachments={[uploadingAttachment]}
      onAttachmentsChange={onAttachmentsChange}
      onCancelUpload={onCancelUpload}
      onImageViewerOpen={vi.fn()}
    />,
  );

  const card = screen
    .getByText("uploading.pdf")
    .closest(".attachment-card-enter");
  expect(card).not.toBeNull();
  fireEvent.click(within(card as HTMLElement).getByRole("button"));

  expect(onCancelUpload).toHaveBeenCalledWith("temp-upload-1");
  expect(onAttachmentsChange).not.toHaveBeenCalled();
});
