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
  $createFileReferenceNode,
  FileReferenceNode,
} from "./nodes/FileReferenceNode";
import {
  INSERT_FILE_REFERENCE_COMMAND,
  REMOVE_FILE_REFERENCE_COMMAND,
  RETRY_FILE_REFERENCE_COMMAND,
  UPDATE_FILE_REFERENCE_COMMAND,
} from "./nodes/referenceCommands";

export function FileReferencePlugin({
  onRetry,
}: {
  onRetry?: (referenceId: string) => void;
}) {
  const [editor] = useLexicalComposerContext();

  useLayoutEffect(() => {
    return editor.registerCommand(
      INSERT_FILE_REFERENCE_COMMAND,
      (descriptor) => {
        const existing = $nodesOfType(FileReferenceNode).find(
          (node) => node.getDescriptor().referenceId === descriptor.referenceId,
        );
        if (existing) {
          existing.updateDescriptor(descriptor);
          existing.selectNext();
          return true;
        }
        let selection = $getSelection();
        if (!$isRangeSelection(selection)) {
          const root = $getRoot();
          if (root.getChildrenSize() === 0) root.append($createParagraphNode());
          selection = root.selectEnd();
        }
        $insertNodes([$createFileReferenceNode(descriptor)]);
        return true;
      },
      COMMAND_PRIORITY_EDITOR,
    );
  }, [editor]);

  useLayoutEffect(() => {
    return editor.registerCommand(
      REMOVE_FILE_REFERENCE_COMMAND,
      (referenceId) => {
        const node = $nodesOfType(FileReferenceNode).find(
          (candidate) => candidate.getDescriptor().referenceId === referenceId,
        );
        node?.remove();
        return node !== undefined;
      },
      COMMAND_PRIORITY_EDITOR,
    );
  }, [editor]);

  useLayoutEffect(() => {
    return editor.registerCommand(
      UPDATE_FILE_REFERENCE_COMMAND,
      (update) => {
        const node = $nodesOfType(FileReferenceNode).find(
          (candidate) =>
            candidate.getDescriptor().referenceId === update.referenceId,
        );
        node?.updateDescriptor(update);
        return node !== undefined;
      },
      COMMAND_PRIORITY_EDITOR,
    );
  }, [editor]);

  useLayoutEffect(() => {
    return editor.registerCommand(
      RETRY_FILE_REFERENCE_COMMAND,
      (referenceId) => {
        onRetry?.(referenceId);
        return onRetry !== undefined;
      },
      COMMAND_PRIORITY_EDITOR,
    );
  }, [editor, onRetry]);

  return null;
}
