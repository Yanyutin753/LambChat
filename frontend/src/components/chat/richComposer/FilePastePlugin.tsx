import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { COMMAND_PRIORITY_HIGH, PASTE_COMMAND } from "lexical";
import { useEffect } from "react";
import type { FilePasteOptions } from "./RichChatComposer";

export function FilePastePlugin({ options }: { options: FilePasteOptions }) {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    return editor.registerCommand(
      PASTE_COMMAND,
      (event) => {
        if (!("clipboardData" in event) || !event.clipboardData) return false;
        const files = event.clipboardData.files;
        if (files.length === 0) return false;

        event.preventDefault();
        if (options.validateCount(files.length)) options.onFiles(files);
        return true;
      },
      COMMAND_PRIORITY_HIGH,
    );
  }, [editor, options]);

  return null;
}
