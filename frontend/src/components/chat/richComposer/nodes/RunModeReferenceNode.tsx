import type { ReactNode } from "react";
import {
  $applyNodeReplacement,
  $createParagraphNode,
  $createTextNode,
  $getRoot,
  $isElementNode,
  $nodesOfType,
  DecoratorNode,
  type ElementNode,
  type LexicalEditor,
  type LexicalNode,
  type NodeKey,
  type SerializedLexicalNode,
  type Spread,
} from "lexical";
import { RunModeChip } from "../RunModeChip";
import type { RunModeKey } from "../composerTypes";
import { removeReferenceWithSpacer } from "../referenceNodeRemoval";
import { TOGGLE_RUN_MODE_COMMAND } from "./referenceCommands";

export type SerializedRunModeReferenceNode = Spread<
  { modeKey: RunModeKey },
  SerializedLexicalNode
>;

export class RunModeReferenceNode extends DecoratorNode<ReactNode> {
  __modeKey: RunModeKey;

  static getType(): string {
    return "run-mode-reference";
  }

  static clone(node: RunModeReferenceNode): RunModeReferenceNode {
    return new RunModeReferenceNode(node.__modeKey, node.__key);
  }

  static importJSON(
    serializedNode: SerializedLexicalNode & Record<string, unknown>,
  ): LexicalNode {
    const descriptor =
      serializedNode as Partial<SerializedRunModeReferenceNode>;
    if (descriptor.version !== 1) {
      return $createTextNode("");
    }
    return $createRunModeReferenceNode(
      descriptor.modeKey === "goal" ? "goal" : "auto",
    );
  }

  constructor(modeKey: RunModeKey = "auto", key?: NodeKey) {
    super(key);
    this.__modeKey = modeKey;
  }

  createDOM(): HTMLElement {
    const element = document.createElement("span");
    element.className = "composer-reference-node";
    return element;
  }

  updateDOM(): false {
    return false;
  }

  exportJSON(): SerializedRunModeReferenceNode {
    return {
      ...super.exportJSON(),
      modeKey: this.getModeKey(),
      type: "run-mode-reference",
      version: 1,
    };
  }

  getTextContent(): string {
    return "";
  }

  getModeKey(): RunModeKey {
    return this.getLatest().__modeKey;
  }

  decorate(editor: LexicalEditor): ReactNode {
    const modeKey = this.getModeKey();
    return (
      <RunModeChip
        modeKey={modeKey}
        onClick={() => editor.dispatchCommand(TOGGLE_RUN_MODE_COMMAND, modeKey)}
      />
    );
  }
}

const RUN_MODE_ORDER: readonly RunModeKey[] = ["auto", "goal"];

/**
 * Keeps the leading run-mode chips in sync with the enabled modes: inserts
 * missing chips at the start of the document and removes stale ones. Called
 * inside editor.update() after mode changes and draft replacements.
 */
export function $reconcileRunModeChips(enabled: {
  auto: boolean;
  goal: boolean;
}): void {
  const desired = RUN_MODE_ORDER.filter((key) => enabled[key]);
  const existing = $nodesOfType(RunModeReferenceNode);
  const existingKeys = existing.map((node) => node.getModeKey());
  if (
    existingKeys.length === desired.length &&
    existingKeys.every((key, index) => key === desired[index])
  ) {
    return;
  }
  for (const node of existing) {
    removeReferenceWithSpacer(node);
  }
  if (desired.length === 0) return;

  const root = $getRoot();
  const firstChild = root.getFirstChild();
  let paragraph: ElementNode | null = null;
  if ($isElementNode(firstChild)) paragraph = firstChild;
  if (paragraph === null) {
    paragraph = $createParagraphNode();
    root.append(paragraph);
  }
  const anchor = paragraph.getFirstChild();
  for (const key of desired) {
    const chip = $createRunModeReferenceNode(key);
    const spacer = $createTextNode(" ");
    if (anchor) {
      anchor.insertBefore(chip);
      chip.insertAfter(spacer);
    } else {
      paragraph.append(chip, spacer);
    }
  }
  if (!anchor) {
    // Inserting into an empty draft: park the caret after the chips so
    // typing/Backspace behave like a freshly inserted reference.
    paragraph.selectEnd();
  }
}

export function $createRunModeReferenceNode(
  modeKey: RunModeKey,
): RunModeReferenceNode {
  return $applyNodeReplacement(new RunModeReferenceNode(modeKey));
}

export function $isRunModeReferenceNode(
  node: LexicalNode | null | undefined,
): node is RunModeReferenceNode {
  return node instanceof RunModeReferenceNode;
}
