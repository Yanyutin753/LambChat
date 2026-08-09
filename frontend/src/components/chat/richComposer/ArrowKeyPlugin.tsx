import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { mergeRegister } from "@lexical/utils";
import {
  COMMAND_PRIORITY_LOW,
  KEY_ARROW_DOWN_COMMAND,
  KEY_ARROW_UP_COMMAND,
} from "lexical";
import { useEffect } from "react";

export type ComposerArrowDirection = "up" | "down";

export function ArrowKeyPlugin({
  onArrowKey,
}: {
  onArrowKey?: (
    direction: ComposerArrowDirection,
    editor: HTMLElement,
  ) => boolean;
}) {
  const [editor] = useLexicalComposerContext();

  useEffect(() => {
    const handleArrow =
      (direction: ComposerArrowDirection) => (event: KeyboardEvent) => {
        const rootElement = editor.getRootElement();
        if (!rootElement || !onArrowKey?.(direction, rootElement)) return false;
        event.preventDefault();
        return true;
      };

    return mergeRegister(
      editor.registerCommand(
        KEY_ARROW_UP_COMMAND,
        handleArrow("up"),
        COMMAND_PRIORITY_LOW,
      ),
      editor.registerCommand(
        KEY_ARROW_DOWN_COMMAND,
        handleArrow("down"),
        COMMAND_PRIORITY_LOW,
      ),
    );
  }, [editor, onArrowKey]);

  return null;
}
