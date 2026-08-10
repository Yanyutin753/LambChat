/** @vitest-environment jsdom */

import { createEvent, fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { PASTE_TEXT_THRESHOLD } from "../../chatInputConstants";
import { RichChatComposer } from "../RichChatComposer";

function paste(element: HTMLElement, files: File[], text = ""): ClipboardEvent {
  const event = createEvent.paste(element, {
    clipboardData: {
      files,
      getData: (type: string) => (type === "text/plain" ? text : ""),
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
      filePaste={{ validateCount, onFiles }}
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
      filePaste={{ validateCount, onFiles }}
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
      filePaste={{ validateCount, onFiles }}
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
      filePaste={{ validateCount: () => true, onFiles }}
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
