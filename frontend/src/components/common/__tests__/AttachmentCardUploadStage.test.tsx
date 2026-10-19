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

test("shows measured server-processing percentage and keeps cancel available", () => {
  render(
    <AttachmentCard
      attachment={{
        ...baseAttachment,
        uploadStage: "processing",
        uploadProcessingProgress: 46,
      }}
      size="compact"
      variant="editable"
      isUploading
      onCancel={vi.fn()}
    />,
  );
  expect(screen.getByText("Processing on server… 46%")).toBeInTheDocument();
  expect(screen.getByTitle("Cancel upload")).toBeInTheDocument();
});

test("compact attachments expose separate preview and remove buttons", () => {
  const preview = vi.fn();
  const remove = vi.fn();
  render(
    <AttachmentCard
      attachment={{ ...baseAttachment, isUploading: false }}
      size="compact"
      variant="editable"
      onClick={preview}
      onRemove={remove}
    />,
  );
  screen.getByRole("button", { name: "capture.png" }).click();
  expect(preview).toHaveBeenCalledOnce();
  screen.getByRole("button", { name: i18n.t("common.remove") }).click();
  expect(remove).toHaveBeenCalledOnce();
  expect(preview).toHaveBeenCalledOnce();
});

test.each([
  ["preparing", true],
  ["uploading", true],
  ["processing", true],
  ["processing", false],
] as const)(
  "keeps action buttons outside the text layout in %s (uploading: %s)",
  (uploadStage, isUploading) => {
    render(
      <AttachmentCard
        attachment={{ ...baseAttachment, uploadStage, isUploading }}
        size="compact"
        variant="editable"
        isUploading={isUploading}
        onCancel={vi.fn()}
        onRemove={vi.fn()}
      />,
    );

    const textLayout = screen.getByText("capture.png").parentElement!;
    expect(textLayout.querySelector("button")).toBeNull();
    expect(
      screen.getByRole("button", {
        name: isUploading
          ? i18n.t("fileUpload.cancelUpload")
          : i18n.t("common.remove"),
      }),
    ).toBeEnabled();
  },
);
