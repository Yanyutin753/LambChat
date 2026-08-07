import { useCallback } from "react";
import {
  turndown,
  cleanPastedHtml,
} from "../components/chat/chatInputTurndown";
import { PASTE_TEXT_THRESHOLD } from "../components/chat/chatInputConstants";
import type { FileCategory } from "../types";

export interface UsePasteHandlerOptions {
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  input: string;
  setInput: (value: string) => void;
  uploadFiles: (files: FileList | File[], category?: FileCategory) => void;
  validateCount: (count: number) => boolean;
  scheduleTextareaResize: () => void;
  /** Convert oversized pasted text into a long-text attachment. */
  onLongTextPaste?: (text: string, preserveText?: string) => boolean;
}

export function usePasteHandler({
  textareaRef,
  input,
  setInput,
  uploadFiles,
  validateCount,
  scheduleTextareaResize,
  onLongTextPaste,
}: UsePasteHandlerOptions) {
  const insertText = useCallback(
    (text: string) => {
      const textarea = textareaRef.current;
      if (!textarea) {
        setInput(input + text);
        return;
      }
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const newValue = input.substring(0, start) + text + input.substring(end);
      setInput(newValue);
      setTimeout(() => {
        textarea.selectionStart = textarea.selectionEnd = start + text.length;
        textarea.focus();
        scheduleTextareaResize();
      }, 0);
    },
    [textareaRef, input, setInput, scheduleTextareaResize],
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      const clipboardData = e.clipboardData;
      if (!clipboardData) return;

      if (clipboardData.files && clipboardData.files.length > 0) {
        e.preventDefault();
        if (!validateCount(clipboardData.files.length)) return;
        uploadFiles(clipboardData.files);
        return;
      }

      const htmlText = clipboardData.getData("text/html");
      if (htmlText) {
        e.preventDefault();
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = htmlText;
        cleanPastedHtml(tempDiv);
        const markdownText = turndown.turndown(tempDiv);

        if (markdownText.length > PASTE_TEXT_THRESHOLD) {
          const textarea = textareaRef.current;
          const before = textarea
            ? input.substring(0, textarea.selectionStart)
            : input;
          const after = textarea ? input.substring(textarea.selectionEnd) : "";
          if (onLongTextPaste?.(markdownText, before + after)) return;
        }

        insertText(markdownText);
        return;
      }

      const plainText = clipboardData.getData("text/plain");
      if (plainText && plainText.length > PASTE_TEXT_THRESHOLD) {
        e.preventDefault();
        const textarea = textareaRef.current;
        const before = textarea
          ? input.substring(0, textarea.selectionStart)
          : input;
        const after = textarea ? input.substring(textarea.selectionEnd) : "";
        if (onLongTextPaste?.(plainText, before + after)) return;
        insertText(plainText);
      }
    },
    [
      uploadFiles,
      validateCount,
      onLongTextPaste,
      insertText,
      input,
      textareaRef,
    ],
  );

  return { handlePaste };
}
