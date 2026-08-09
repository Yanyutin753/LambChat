import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import {
  $createParagraphNode,
  $getRoot,
  $getSelection,
  $insertNodes,
  $isRangeSelection,
  $nodesOfType,
  COMMAND_PRIORITY_EDITOR,
} from "lexical";
import { useLayoutEffect } from "react";
import {
  $createSkillReferenceNode,
  SkillReferenceNode,
} from "./nodes/SkillReferenceNode";
import { INSERT_SKILL_REFERENCE_COMMAND } from "./nodes/referenceCommands";

export function SkillReferencePlugin() {
  const [editor] = useLexicalComposerContext();

  useLayoutEffect(() => {
    return editor.registerCommand(
      INSERT_SKILL_REFERENCE_COMMAND,
      (descriptor) => {
        const existing = $nodesOfType(SkillReferenceNode).find(
          (node) => node.getDescriptor().skillName === descriptor.skillName,
        );
        if (existing) {
          existing.selectNext();
          return true;
        }
        let selection = $getSelection();
        if (!$isRangeSelection(selection)) {
          const root = $getRoot();
          if (root.getChildrenSize() === 0) root.append($createParagraphNode());
          selection = root.selectEnd();
        }
        $insertNodes([$createSkillReferenceNode(descriptor)]);
        return true;
      },
      COMMAND_PRIORITY_EDITOR,
    );
  }, [editor]);

  return null;
}
