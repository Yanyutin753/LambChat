/** @vitest-environment jsdom */

import { createEvent, fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { PASTE_TEXT_THRESHOLD } from "../../chatInputConstants";
import { RichChatComposer } from "../RichChatComposer";

const PNG_DATA_URL =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

function paste(
  element: HTMLElement,
  files: File[],
  text = "",
  html = "",
): ClipboardEvent {
  const event = createEvent.paste(element, {
    clipboardData: {
      files,
      getData: (type: string) => {
        if (type === "text/html") return html;
        if (type === "text/plain") return text;
        return "";
      },
    },
  });
  fireEvent(element, event);
  return event;
}

test("pasting an image uploads it instead of inserting accompanying text", () => {
  const validateCount = vi.fn(() => true);
  const onFiles = vi.fn();
  const onLongTextCreate = vi.fn();
  render(
    <RichChatComposer
      ariaLabel="message"
      filePaste={{ validateCount, onFiles, onInvalidImage: vi.fn() }}
      longTextPaste={{
        enabled: true,
        validateCount: () => true,
        onCreate: onLongTextCreate,
      }}
    />,
  );
  const editor = screen.getByRole("textbox", { name: "message" });
  const image = new File(["image"], "screenshot.png", { type: "image/png" });
  const files = [image];
  const accompanyingText = "x".repeat(PASTE_TEXT_THRESHOLD + 1);

  const event = paste(editor, files, accompanyingText);

  expect(event.defaultPrevented).toBe(true);
  expect(validateCount).toHaveBeenCalledWith(1);
  expect(onFiles).toHaveBeenCalledWith(files);
  expect(onLongTextCreate).not.toHaveBeenCalled();
  expect(editor).not.toHaveTextContent(accompanyingText);
});

test("pasting multiple files forwards the complete collection", () => {
  const validateCount = vi.fn(() => true);
  const onFiles = vi.fn();
  render(
    <RichChatComposer
      ariaLabel="message"
      filePaste={{ validateCount, onFiles, onInvalidImage: vi.fn() }}
    />,
  );
  const files = [
    new File(["one"], "one.pdf", { type: "application/pdf" }),
    new File(["two"], "two.txt", { type: "text/plain" }),
  ];

  paste(screen.getByRole("textbox", { name: "message" }), files);

  expect(validateCount).toHaveBeenCalledWith(2);
  expect(onFiles).toHaveBeenCalledWith(files);
});

test("rejected file paste is consumed without upload or fallback text", () => {
  const validateCount = vi.fn(() => false);
  const onFiles = vi.fn();
  const onLongTextCreate = vi.fn();
  render(
    <RichChatComposer
      ariaLabel="message"
      filePaste={{ validateCount, onFiles, onInvalidImage: vi.fn() }}
      longTextPaste={{
        enabled: true,
        validateCount: () => true,
        onCreate: onLongTextCreate,
      }}
    />,
  );
  const editor = screen.getByRole("textbox", { name: "message" });
  const fallbackText = "fallback text";

  const event = paste(
    editor,
    [new File(["data"], "blocked.txt", { type: "text/plain" })],
    fallbackText,
  );

  expect(event.defaultPrevented).toBe(true);
  expect(validateCount).toHaveBeenCalledWith(1);
  expect(onFiles).not.toHaveBeenCalled();
  expect(onLongTextCreate).not.toHaveBeenCalled();
  expect(editor).not.toHaveTextContent(fallbackText);
});

test("text-only paste falls through to long-text conversion", () => {
  const onFiles = vi.fn();
  const onLongTextCreate = vi.fn();
  render(
    <RichChatComposer
      ariaLabel="message"
      filePaste={{
        validateCount: () => true,
        onFiles,
        onInvalidImage: vi.fn(),
      }}
      longTextPaste={{
        enabled: true,
        validateCount: () => true,
        onCreate: onLongTextCreate,
      }}
    />,
  );
  const longText = "x".repeat(PASTE_TEXT_THRESHOLD + 1);

  paste(screen.getByRole("textbox", { name: "message" }), [], longText);

  expect(onFiles).not.toHaveBeenCalled();
  expect(onLongTextCreate).toHaveBeenCalledTimes(1);
});

test("zero-byte clipboard placeholders are consumed as unavailable images", () => {
  const onFiles = vi.fn();
  const onInvalidImage = vi.fn();
  const onLongTextCreate = vi.fn();
  render(
    <RichChatComposer
      ariaLabel="message"
      filePaste={{ validateCount: () => true, onFiles, onInvalidImage }}
      longTextPaste={{
        enabled: true,
        validateCount: () => true,
        onCreate: onLongTextCreate,
      }}
    />,
  );
  const editor = screen.getByRole("textbox", { name: "message" });
  const placeholder = new File([], "bpm_r5.bin", { type: "" });

  const event = paste(editor, [placeholder], "stale fallback text");

  expect(event.defaultPrevented).toBe(true);
  expect(onInvalidImage).toHaveBeenCalledOnce();
  expect(onFiles).not.toHaveBeenCalled();
  expect(onLongTextCreate).not.toHaveBeenCalled();
  expect(editor).not.toHaveTextContent("stale fallback text");
});

test("embedded data images are uploaded instead of inserted as text", () => {
  const onFiles = vi.fn();
  const onInvalidImage = vi.fn();
  const onLongTextCreate = vi.fn();
  render(
    <RichChatComposer
      ariaLabel="message"
      filePaste={{ validateCount: () => true, onFiles, onInvalidImage }}
      longTextPaste={{
        enabled: true,
        validateCount: () => true,
        onCreate: onLongTextCreate,
      }}
    />,
  );
  const editor = screen.getByRole("textbox", { name: "message" });

  paste(editor, [], "", `<img src="${PNG_DATA_URL}">`);

  expect(onFiles).toHaveBeenCalledOnce();
  const uploadedFiles = onFiles.mock.calls[0]?.[0] as File[];
  expect(uploadedFiles[0]).toMatchObject({
    name: "pasted-image.png",
    type: "image/png",
  });
  expect(uploadedFiles[0].size).toBeGreaterThan(0);
  expect(onInvalidImage).not.toHaveBeenCalled();
  expect(onLongTextCreate).not.toHaveBeenCalled();
  expect(editor).toHaveTextContent("");
});
