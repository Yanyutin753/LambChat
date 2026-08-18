/** @vitest-environment jsdom */

import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";
import type { MessageAttachment, UploadStage } from "../../../types";
import { AttachmentCard } from "../AttachmentCard";

const baseAttachment: MessageAttachment = {
  id: "temp-image",
  key: "",
  name: "capture.png",
  type: "image",
  mimeType: "image/png",
  size: 1024,
  uploadProgress: 0,
  uploadStage: "preparing",
  isUploading: true,
};

function renderStage(stage: UploadStage, progress: number) {
  return render(
    <AttachmentCard
      attachment={{
        ...baseAttachment,
        uploadStage: stage,
        uploadProgress: progress,
      }}
      variant="editable"
      size="compact"
      isUploading
      onCancel={vi.fn()}
    />,
  );
}

beforeEach(async () => {
  await i18n.changeLanguage("en");
});

test("shows preparing, uploading, and server-processing stages without 100 percent", () => {
  const view = renderStage("preparing", 0);
  expect(screen.getByText("Preparing upload…")).toBeInTheDocument();
  expect(screen.getByTitle("Cancel upload")).toBeInTheDocument();

  view.rerender(
    <AttachmentCard
      attachment={{
        ...baseAttachment,
        uploadStage: "uploading",
        uploadProgress: 42,
      }}
      variant="editable"
      size="compact"
      isUploading
      onCancel={vi.fn()}
    />,
  );
  expect(screen.getByText("42%")).toBeInTheDocument();

  view.rerender(
    <AttachmentCard
      attachment={{
        ...baseAttachment,
        uploadStage: "processing",
        uploadProgress: 99,
      }}
      variant="editable"
      size="compact"
      isUploading
      onCancel={vi.fn()}
    />,
  );
  expect(screen.getByText("Processing on server…")).toBeInTheDocument();
  expect(screen.queryByText("100%")).not.toBeInTheDocument();
  expect(screen.getByTitle("Cancel upload")).toBeInTheDocument();
});

test("uses generic preparing copy for non-image attachments", () => {
  render(
    <AttachmentCard
      attachment={{
        ...baseAttachment,
        name: "notes.txt",
        type: "document",
        mimeType: "text/plain",
      }}
      variant="editable"
      size="compact"
      isUploading
      onCancel={vi.fn()}
    />,
  );

  expect(screen.getByText("Preparing upload…")).toBeInTheDocument();
  expect(screen.queryByText("Preparing image…")).not.toBeInTheDocument();
});
