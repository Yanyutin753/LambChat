import { $isElementNode, $isTextNode, type LexicalNode } from "lexical";

/** Removes an atomic reference and the single spacer inserted after it. */
export function removeReferenceWithSpacer(node: LexicalNode): void {
  const parent = node.getParent();
  const index = node.getIndexWithinParent();
  const trailing = node.getNextSibling();
  node.remove();
  if ($isTextNode(trailing) && trailing.getTextContent() === " ") {
    trailing.remove();
  }
  if ($isElementNode(parent)) parent.select(index, index);
}
