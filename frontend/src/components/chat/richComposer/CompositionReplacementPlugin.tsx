import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import {
  $addUpdateTag,
  $getSelection,
  $isRangeSelection,
  $isTextNode,
  $setCompositionKey,
  COMMAND_PRIORITY_HIGH,
  COMPOSITION_START_COMMAND,
  COMPOSITION_START_TAG,
} from "lexical";
import { useEffect } from "react";

export function CompositionReplacementPlugin() {
  const [editor] = useLexicalComposerContext();

  useEffect(
    () =>
      editor.registerCommand(
        COMPOSITION_START_COMMAND,
        () => {
          const selection = $getSelection();
          if (
            editor.isComposing() ||
            !$isRangeSelection(selection) ||
            selection.isCollapsed() ||
            selection.anchor.key !== selection.focus.key
          ) {
            return false;
          }
          const node = selection.anchor.getNode();
          if (!$isTextNode(node) || !node.isSimpleText()) return false;

          // Keep the IME's captured range intact; a placeholder makes it delete unselected text too.
          $setCompositionKey(node.getKey());
          $addUpdateTag(COMPOSITION_START_TAG);
          return true;
        },
        COMMAND_PRIORITY_HIGH,
      ),
    [editor],
  );

  return null;
}
