# Long-text Paste Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure automatically converted long-text attachments contain the complete composer value after paste, including text written before the paste.

**Architecture:** Derive the complete post-paste value at the paste-handler boundary using the current input and textarea selection. Pass that single value through the existing conversion callback, so the attachment and restore metadata share the same complete content and the composer can be cleared after conversion.

**Tech Stack:** React 19, TypeScript, Vitest 4, Testing Library, jsdom

## Global Constraints

- Preserve normal replacement semantics for selected composer text.
- Apply identical content assembly to plain-text and HTML-to-Markdown paste paths.
- Keep expanded-composer, upload API, attachment schema, threshold, and backend behavior unchanged.
- If conversion declines, retain the existing normal-insertion fallback.

---

### Task 1: Convert the complete post-paste composer value

**Files:**
- Create: `frontend/src/hooks/__tests__/usePasteHandlerLongTextBehavior.test.tsx`
- Modify: `frontend/src/hooks/usePasteHandler.tsx`
- Modify: `frontend/src/hooks/useLongTextConversion.ts`
- Modify: `frontend/src/components/chat/ChatInput.tsx`

**Interfaces:**
- Consumes: `input: string`, `textarea.selectionStart`, `textarea.selectionEnd`, and the normalized pasted text.
- Produces: `buildPostPasteInput(input: string, pastedText: string, selectionStart: number, selectionEnd: number): string` and `onLongTextPaste(text: string): boolean`.

- [x] **Step 1: Write failing behavioral tests for plain-text and HTML paste**

Create a jsdom test harness around the real `usePasteHandler` hook. Use a composer value of `beforeSELECTEDafter`, set its selection range to the `SELECTED` span, and paste more than `PASTE_TEXT_THRESHOLD` characters. The callback should expose its received value in an `<output>` element so the assertion observes rendered behavior rather than a mock call.

```tsx
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

test("plain long-text paste converts the complete composer value", () => {
  render(<PasteHarness />);
  paste((type) => (type === "text/plain" ? pastedText : ""));
  expect(screen.getByLabelText("converted text")).toHaveTextContent(
    `before${pastedText}after`,
  );
});

test("HTML long-text paste converts the complete composer value", () => {
  render(<PasteHarness />);
  paste((type) => (type === "text/html" ? `<p>${pastedText}</p>` : ""));
  expect(screen.getByLabelText("converted text")).toHaveTextContent(
    `before${pastedText}after`,
  );
});
```

- [x] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd frontend && pnpm test -- src/hooks/__tests__/usePasteHandlerLongTextBehavior.test.tsx
```

Expected: both tests fail because the current callback receives only `pastedText`, omitting `before` and `after`.

- [x] **Step 3: Implement complete post-paste value assembly**

In `usePasteHandler.tsx`, add the shared computation and use it in both paste branches:

```ts
export function buildPostPasteInput(
  input: string,
  pastedText: string,
  selectionStart: number,
  selectionEnd: number,
): string {
  return (
    input.substring(0, selectionStart) +
    pastedText +
    input.substring(selectionEnd)
  );
}
```

For each oversized paste, default both selection positions to `input.length` when the textarea ref is absent, build the complete post-paste input, and pass only that value to `onLongTextPaste`.

Change the callback contract in `UsePasteHandlerOptions`, `ChatInput.tsx`, and `useLongTextConversion.ts` from `(text, preserveText?)` to `(text)`. Keep `convertTextToAttachment` calling `setInput("")`, because the attachment now owns the complete content.

- [x] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
cd frontend && pnpm test -- src/hooks/__tests__/usePasteHandlerLongTextBehavior.test.tsx src/hooks/__tests__/usePasteHandlerLongText.test.ts src/components/chat/__tests__/longTextConversion.test.ts
```

Expected: all selected tests pass with no warnings.

- [x] **Step 5: Run frontend quality checks**

Run:

```bash
cd frontend && pnpm test
cd frontend && pnpm run lint
cd frontend && pnpm run build
```

Expected: the complete frontend test suite, ESLint, TypeScript build, and Vite production build pass.

- [x] **Step 6: Commit the focused fix**

```bash
git add frontend/src/hooks/__tests__/usePasteHandlerLongTextBehavior.test.tsx frontend/src/hooks/usePasteHandler.tsx frontend/src/hooks/useLongTextConversion.ts frontend/src/components/chat/ChatInput.tsx docs/superpowers/plans/2026-08-09-long-text-paste-content.md
git commit -m "fix(chat): include draft in long-text paste attachment"
```
