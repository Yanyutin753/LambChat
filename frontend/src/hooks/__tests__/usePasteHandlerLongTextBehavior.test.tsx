/** @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { PASTE_TEXT_THRESHOLD } from "../../components/chat/chatInputConstants";
import { usePasteHandler } from "../usePasteHandler";

const initialInput = "beforeSELECTEDafter";
const selectionStart = "before".length;
const selectionEnd = selectionStart + "SELECTED".length;
const pastedText = "p".repeat(PASTE_TEXT_THRESHOLD + 1);
const PNG_DATA_URL =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

function PasteHarness() {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [input, setInput] = useState(initialInput);
  const [convertedText, setConvertedText] = useState("");
  const [uploadedName, setUploadedName] = useState("");
  const [invalidImageCount, setInvalidImageCount] = useState(0);
  const { handlePaste } = usePasteHandler({
    textareaRef,
    input,
    setInput,
    uploadFiles: (files) => setUploadedName(Array.from(files)[0]?.name ?? ""),
    validateCount: () => true,
    scheduleTextareaResize: () => undefined,
    onLongTextPaste: (text) => {
      setConvertedText(text);
      return true;
    },
    onInvalidImagePaste: () => setInvalidImageCount((count) => count + 1),
  });

  return (
    <>
      <textarea
        aria-label="composer"
        ref={textareaRef}
        value={input}
        onChange={(event) => setInput(event.target.value)}
        onPaste={handlePaste}
      />
      <output aria-label="converted text">{convertedText}</output>
      <output aria-label="uploaded name">{uploadedName}</output>
      <output aria-label="invalid image count">{invalidImageCount}</output>
    </>
  );
}

function paste(getData: (type: string) => string, files: File[] = []) {
  const textarea = screen.getByRole("textbox", { name: "composer" });
  textarea.setSelectionRange(selectionStart, selectionEnd);
  fireEvent.paste(textarea, { clipboardData: { files, getData } });
}

test("plain long-text paste converts only the pasted fragment", () => {
  render(<PasteHarness />);
  paste((type) => (type === "text/plain" ? pastedText : ""));
  expect(screen.getByLabelText("converted text").textContent).toBe(pastedText);
});

test("HTML long-text paste converts only the pasted fragment", () => {
  render(<PasteHarness />);
  paste((type) => (type === "text/html" ? `<p>${pastedText}</p>` : ""));
  expect(screen.getByLabelText("converted text").textContent).toBe(pastedText);
});

test("zero-byte clipboard placeholders do not upload or insert fallback text", () => {
  render(<PasteHarness />);
  paste(
    (type) => (type === "text/plain" ? "stale fallback text" : ""),
    [new File([], "bpm_r5.bin", { type: "" })],
  );

  expect(screen.getByLabelText("invalid image count")).toHaveTextContent("1");
  expect(screen.getByLabelText("uploaded name")).toHaveTextContent("");
  expect(screen.getByRole("textbox", { name: "composer" })).toHaveValue(
    initialInput,
  );
});

test("embedded data images upload through the legacy paste handler", () => {
  render(<PasteHarness />);
  paste((type) => (type === "text/html" ? `<img src="${PNG_DATA_URL}">` : ""));

  expect(screen.getByLabelText("uploaded name")).toHaveTextContent(
    "pasted-image.png",
  );
  expect(screen.getByLabelText("invalid image count")).toHaveTextContent("0");
  expect(screen.getByRole("textbox", { name: "composer" })).toHaveValue(
    initialInput,
  );
});
