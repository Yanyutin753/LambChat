/** @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { PASTE_TEXT_THRESHOLD } from "../../components/chat/chatInputConstants";
import { usePasteHandler } from "../usePasteHandler";

const initialInput = "beforeSELECTEDafter";
const selectionStart = "before".length;
const selectionEnd = selectionStart + "SELECTED".length;
const pastedText = "p".repeat(PASTE_TEXT_THRESHOLD + 1);

function PasteHarness() {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [input, setInput] = useState(initialInput);
  const [convertedText, setConvertedText] = useState("");
  const { handlePaste } = usePasteHandler({
    textareaRef,
    input,
    setInput,
    uploadFiles: () => undefined,
    validateCount: () => true,
    scheduleTextareaResize: () => undefined,
    onLongTextPaste: (text) => {
      setConvertedText(text);
      return true;
    },
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
    </>
  );
}

function paste(getData: (type: string) => string) {
  const textarea = screen.getByRole("textbox", { name: "composer" });
  textarea.setSelectionRange(selectionStart, selectionEnd);
  fireEvent.paste(textarea, { clipboardData: { files: [], getData } });
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
