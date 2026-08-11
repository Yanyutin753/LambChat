import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { COMMAND_PRIORITY_HIGH, PASTE_COMMAND } from "lexical";
import { useEffect } from "react";
import { classifyClipboardFiles } from "../clipboardFiles";
import type { FilePasteOptions } from "./RichChatComposer";

export function FilePastePlugin({ options }: { options: FilePasteOptions }) {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    return editor.registerCommand(
      PASTE_COMMAND,
      (event) => {
        if (!("clipboardData" in event) || !event.clipboardData) return false;
        const result = classifyClipboardFiles(event.clipboardData);
        if (result.kind === "none") return false;

        event.preventDefault();
        if (result.kind === "invalid-image") {
          options.onInvalidImage();
          return true;
        }
        if (options.validateCount(result.files.length)) {
          options.onFiles(result.files);
        }
        return true;
      },
      COMMAND_PRIORITY_HIGH,
    );
  }, [editor, options]);

  return null;
}
