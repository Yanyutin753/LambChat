import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import {
  $addUpdateTag,
  $getRoot,
  $getSelection,
  $isRangeSelection,
  COMMAND_PRIORITY_HIGH,
  PASTE_COMMAND,
  PASTE_TAG,
} from "lexical";
import { useEffect, useState } from "react";
import { uuid } from "../../../utils/uuid";
import {
  buildLongTextFileName,
  createLongTextFile,
  shouldConvertLongText,
} from "../longTextConversion";
import { cleanPastedHtml, turndown } from "../chatInputTurndown";
import type { LongTextPasteOptions } from "./RichChatComposer";
import { $createFileReferenceNode } from "./nodes/FileReferenceNode";

function getPastedText(clipboardData: DataTransfer): string {
  const html = clipboardData.getData("text/html");
  if (!html) return clipboardData.getData("text/plain");
  const container = document.createElement("div");
  container.innerHTML = html;
  cleanPastedHtml(container);
  return turndown.turndown(container);
}

export function LongTextPastePlugin({
  options,
}: {
  options: LongTextPasteOptions;
}) {
  const [editor] = useLexicalComposerContext();
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    return editor.registerCommand(
      PASTE_COMMAND,
      (event) => {
        if (!("clipboardData" in event) || !event.clipboardData) return false;
        const clipboardData = event.clipboardData;
        if (clipboardData.files.length > 0) return false;
        const pastedText = getPastedText(clipboardData);
        if (!pastedText) return false;
        let selection = $getSelection();
        if (!$isRangeSelection(selection)) selection = $getRoot().selectEnd();

        const shouldCreateReference =
          options.enabled &&
          shouldConvertLongText(pastedText) &&
          options.validateCount(1);
        event.preventDefault();
        $addUpdateTag(PASTE_TAG);

        if (!shouldCreateReference) {
          selection.insertRawText(pastedText);
          return true;
        }

        const referenceId = uuid();
        const file = createLongTextFile(pastedText, buildLongTextFileName());
        selection.insertNodes([
          $createFileReferenceNode({
            referenceId,
            fileName: file.name,
            category: "document",
            status: "uploading",
          }),
        ]);
        options.onCreate({ referenceId, file, originalText: pastedText });
        setAnnouncement(`Inserted file reference ${file.name}`);
        return true;
      },
      COMMAND_PRIORITY_HIGH,
    );
  }, [editor, options]);

  return (
    <span className="sr-only" aria-live="polite">
      {announcement}
    </span>
  );
}
