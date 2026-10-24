/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { DocumentPreviewProps } from "../../documents/useDocumentPreviewState";
import type { MessageAttachment } from "../../../types";
import { AttachmentPreviewHost } from "../AttachmentPreviewHost";
import {
  clearAttachmentPreviews,
  openAttachmentPreview,
} from "../attachmentPreviewStore";

vi.mock(
  "../../../services/api",
  async () => import("../../../services/api/config"),
);
vi.mock("../../documents/LazyDocumentPreview", () => ({
  LazyDocumentPreview: ({ path, signedUrl, s3Key }: DocumentPreviewProps) => (
    <a href={signedUrl} data-storage-key={s3Key}>
      {path}
    </a>
  ),
}));

afterEach(() => {
  cleanup();
  clearAttachmentPreviews();
});

test.each([
  ["report.pptx", "document"],
  ["report.pdf", "document"],
  ["report.docx", "document"],
  ["data.xlsx", "document"],
  ["archive.zip", "document"],
  ["video.mp4", "video"],
  ["audio.mp3", "audio"],
] as const)("opening shared %s preserves its file capability", (name, type) => {
  const key = `uploads/${name}`;
  const url = `${
    window.location.origin
  }/api/upload/file/${key}?file_token=header.${btoa(
    JSON.stringify({ share_id: "shared", exp: 4102444800 }),
  )}.signature`;
  openAttachmentPreview(
    {
      id: "attachment",
      key,
      name,
      type,
      url,
      size: 123,
      mimeType: "application/octet-stream",
    },
    "user-message",
  );

  render(<AttachmentPreviewHost />);

  expect(screen.getByText(name).getAttribute("href")).toBe(url);
  expect(screen.getByText(name).getAttribute("data-storage-key")).toBe(key);
});

test("legacy owner attachments without a URL retain the storage key fallback", () => {
  const attachment: MessageAttachment = {
    id: "legacy",
    key: "uploads/old.pdf",
    name: "old.pdf",
    type: "document",
    mimeType: "application/pdf",
    size: 123,
  };
  openAttachmentPreview(attachment, "user-message");
  render(<AttachmentPreviewHost />);
  expect(screen.getByText("old.pdf").getAttribute("href")).toBeNull();
  expect(screen.getByText("old.pdf").getAttribute("data-storage-key")).toBe(
    attachment.key,
  );
});

test.each([
  "https://storage.example/old.pdf?X-Amz-Expires=1",
  `https://foreign.example/api/upload/file/uploads/old.pdf?file_token=header.${btoa(
    JSON.stringify({ share_id: "foreign" }),
  )}.signature`,
  `/api/upload/file/uploads/old.pdf?file_token=header.${btoa(
    JSON.stringify({ type: "file", exp: 1 }),
  )}.signature`,
])("owner attachments with stale URL %s retain key-based renewal", (url) => {
  openAttachmentPreview(
    {
      id: "old",
      key: "uploads/old.pdf",
      name: "old.pdf",
      type: "document",
      mimeType: "application/pdf",
      size: 123,
      url,
    },
    "user-message",
  );
  render(<AttachmentPreviewHost />);
  expect(screen.getByText("old.pdf").getAttribute("href")).toBeNull();
  expect(screen.getByText("old.pdf").getAttribute("data-storage-key")).toBe(
    "uploads/old.pdf",
  );
});

test("expired share capabilities remain share-bound instead of falling back to owner access", () => {
  const url = `/api/upload/file/uploads/old.pdf?file_token=header.${btoa(
    JSON.stringify({ share_id: "expired-share", exp: 1 }),
  )}.signature`;
  openAttachmentPreview(
    {
      id: "old",
      key: "uploads/old.pdf",
      name: "old.pdf",
      type: "document",
      mimeType: "application/pdf",
      size: 123,
      url,
    },
    "user-message",
  );
  render(<AttachmentPreviewHost />);
  expect(screen.getByText("old.pdf").getAttribute("href")).toBe(url);
});
