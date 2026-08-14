import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { COMMAND_PRIORITY_HIGH, PASTE_COMMAND } from "lexical";
import { useEffect, useRef } from "react";
import {
  classifyClipboardFiles,
  decodeEmbeddedClipboardImage,
} from "../clipboardFiles";
import type { FilePasteOptions } from "./RichChatComposer";

export function FilePastePlugin({ options }: { options: FilePasteOptions }) {
  const [editor] = useLexicalComposerContext();
  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
    const pendingDecodes = new Set<AbortController>();
    const unregister = editor.registerCommand(
      PASTE_COMMAND,
      (event) => {
        if (!("clipboardData" in event) || !event.clipboardData) return false;
        const result = classifyClipboardFiles(event.clipboardData);
        if (result.kind === "none") return false;

        event.preventDefault();
        if (result.kind === "invalid-image") {
          optionsRef.current.onInvalidImage();
          return true;
        }
        if (result.kind === "embedded-image") {
          const controller = new AbortController();
          pendingDecodes.add(controller);
          void decodeEmbeddedClipboardImage(
            result.source,
            result.mimeType,
            controller.signal,
          )
            .then((file) => {
              if (controller.signal.aborted) return;
              if (optionsRef.current.validateCount(1)) {
                optionsRef.current.onFiles([file]);
              }
            })
            .catch(() => {
              if (!controller.signal.aborted) {
                optionsRef.current.onInvalidImage();
              }
            })
            .finally(() => pendingDecodes.delete(controller));
          return true;
        }
        if (optionsRef.current.validateCount(result.files.length)) {
          optionsRef.current.onFiles(result.files);
        }
        return true;
      },
      COMMAND_PRIORITY_HIGH,
    );
    return () => {
      unregister();
      for (const controller of pendingDecodes) controller.abort();
      pendingDecodes.clear();
    };
  }, [editor]);

  return null;
}
