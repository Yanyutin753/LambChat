import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { mergeRegister } from "@lexical/utils";
import {
  $getSelection,
  $isElementNode,
  $isNodeSelection,
  $isRangeSelection,
  $isTextNode,
  COMMAND_PRIORITY_HIGH,
  KEY_BACKSPACE_COMMAND,
  KEY_DELETE_COMMAND,
  type LexicalNode,
} from "lexical";
import { useEffect } from "react";
import { $isFileReferenceNode } from "./nodes/FileReferenceNode";
import { $isSkillReferenceNode } from "./nodes/SkillReferenceNode";
import { removeReferenceWithSpacer } from "./referenceNodeRemoval";

function isAtomicReference(node: LexicalNode | null | undefined): boolean {
  return $isFileReferenceNode(node) || $isSkillReferenceNode(node);
}

function getAdjacentNode(direction: "backward" | "forward") {
  const selection = $getSelection();
  if (!$isRangeSelection(selection) || !selection.isCollapsed()) return null;

  const anchor = selection.anchor;
  const anchorNode = anchor.getNode();
  if ($isElementNode(anchorNode)) {
    const child = anchorNode.getChildAtIndex(
      direction === "backward" ? anchor.offset - 1 : anchor.offset,
    );
    if (!$isElementNode(child)) return child;
    return direction === "backward"
      ? child.getLastDescendant()
      : child.getFirstDescendant();
  }
  if ($isTextNode(anchorNode)) {
    if (
      direction === "backward" &&
      anchor.offset === 1 &&
      anchorNode.getTextContent().startsWith(" ") &&
      isAtomicReference(anchorNode.getPreviousSibling())
    ) {
      return anchorNode;
    }
    if (direction === "backward" && anchor.offset === 0) {
      return anchorNode.getPreviousSibling();
    }
    if (
      direction === "forward" &&
      anchor.offset === anchorNode.getTextContentSize()
    ) {
      return anchorNode.getNextSibling();
    }
  }
  return null;
}

function removeReference(
  event: KeyboardEvent | null,
  direction: "backward" | "forward",
) {
  const selection = $getSelection();
  if ($isNodeSelection(selection)) {
    const references = selection.getNodes().filter(isAtomicReference);
    if (references.length === 0) return false;
    event?.preventDefault();
    references.forEach(removeReferenceWithSpacer);
    return true;
  }

  const adjacentNode = getAdjacentNode(direction);
  if (
    direction === "backward" &&
    $isTextNode(adjacentNode) &&
    adjacentNode.getTextContent() === " " &&
    isAtomicReference(adjacentNode.getPreviousSibling())
  ) {
    event?.preventDefault();
    const reference = adjacentNode.getPreviousSibling();
    if (reference) removeReferenceWithSpacer(reference);
    return true;
  }
  if (!isAtomicReference(adjacentNode)) return false;
  event?.preventDefault();
  if (adjacentNode) removeReferenceWithSpacer(adjacentNode);
  return true;
}

export function AtomicReferenceDeletionPlugin() {
  const [editor] = useLexicalComposerContext();

  useEffect(
    () =>
      mergeRegister(
        editor.registerCommand(
          KEY_BACKSPACE_COMMAND,
          (event) => removeReference(event, "backward"),
          COMMAND_PRIORITY_HIGH,
        ),
        editor.registerCommand(
          KEY_DELETE_COMMAND,
          (event) => removeReference(event, "forward"),
          COMMAND_PRIORITY_HIGH,
        ),
      ),
    [editor],
  );

  return null;
}
