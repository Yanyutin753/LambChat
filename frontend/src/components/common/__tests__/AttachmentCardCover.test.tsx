/** @vitest-environment jsdom */

import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import i18n from "../../../i18n";
import type { MessageAttachment } from "../../../types";
import { AttachmentCard } from "../AttachmentCard";

function makeAttachment(
  overrides: Partial<MessageAttachment>,
): MessageAttachment {
  return {
    id: "a1",
    key: "files/report.pdf",
    name: "report.pdf",
    type: "document",
    mimeType: "application/pdf",
    size: 2048,
    ...overrides,
  };
}

beforeEach(async () => {
  await i18n.changeLanguage("en");
});

test("image attachments load the thumbnail URL, not the original", () => {
  render(
    <AttachmentCard
      attachment={makeAttachment({
        name: "hero.jpg",
        mimeType: "image/jpeg",
        type: "image",
        url: "/api/upload/file/abc/hero.jpg",
      })}
    />,
  );
  const img = screen.getByAltText("hero.jpg") as HTMLImageElement;
  expect(img.getAttribute("src")).toBe(
    "http://localhost:3000/api/upload/file/abc/hero.jpg?thumb=1",
  );
});

test("pdf attachments render the server-side cover preview", () => {
  render(
    <AttachmentCard
      attachment={makeAttachment({
        url: "/api/upload/file/abc/report.pdf",
      })}
    />,
  );
  const img = screen.getByAltText("report.pdf") as HTMLImageElement;
  expect(img.getAttribute("src")).toBe(
    "http://localhost:3000/api/upload/file/abc/report.pdf?cover=1",
  );
});

test("plain text attachments keep the file icon", () => {
  render(
    <AttachmentCard
      attachment={makeAttachment({
        name: "notes.txt",
        mimeType: "text/plain",
        url: "/api/upload/files/notes.txt",
      })}
    />,
  );
  expect(screen.queryByAltText("notes.txt")).not.toBeInTheDocument();
  expect(screen.getByText("notes.txt")).toBeInTheDocument();
});
