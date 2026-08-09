import type { ReactNode } from "react";
import {
  $applyNodeReplacement,
  $createTextNode,
  DecoratorNode,
  type LexicalEditor,
  type LexicalNode,
  type NodeKey,
  type SerializedLexicalNode,
  type Spread,
} from "lexical";
import { FileReferenceChip } from "../FileReferenceChip";
import type {
  FileReferenceDescriptor,
  FileReferenceStatus,
} from "../composerTypes";

export type SerializedFileReferenceNode = Spread<
  FileReferenceDescriptor,
  SerializedLexicalNode
>;

export class FileReferenceNode extends DecoratorNode<ReactNode> {
  __referenceId: string;
  __fileName: string;
  __category: "document";
  __status: FileReferenceStatus;

  static getType(): string {
    return "file-reference";
  }

  static clone(node: FileReferenceNode): FileReferenceNode {
    return new FileReferenceNode(node.getDescriptor(), node.__key);
  }

  static importJSON(
    serializedNode: SerializedLexicalNode & Record<string, unknown>,
  ): LexicalNode {
    const descriptor = serializedNode as Partial<SerializedFileReferenceNode>;
    if (descriptor.version !== 1) {
      return $createTextNode(`[引用文件：${descriptor.fileName || "文件"}]`);
    }
    return $createFileReferenceNode({
      referenceId: descriptor.referenceId ?? "",
      fileName: descriptor.fileName ?? "文件",
      category: "document",
      status: descriptor.status ?? "ready",
    });
  }

  constructor(
    descriptor: FileReferenceDescriptor = {
      referenceId: "",
      fileName: "",
      category: "document",
      status: "ready",
    },
    key?: NodeKey,
  ) {
    super(key);
    this.__referenceId = descriptor.referenceId;
    this.__fileName = descriptor.fileName;
    this.__category = descriptor.category;
    this.__status = descriptor.status;
  }

  createDOM(): HTMLElement {
    const element = document.createElement("span");
    element.className = "composer-reference-node";
    return element;
  }

  updateDOM(): false {
    return false;
  }

  exportJSON(): SerializedFileReferenceNode {
    const descriptor = this.getDescriptor();
    return {
      ...super.exportJSON(),
      ...descriptor,
      type: "file-reference",
      version: 1,
    };
  }

  getTextContent(): string {
    return `[引用文件：${this.getLatest().__fileName}]`;
  }

  getDescriptor(): FileReferenceDescriptor {
    const self = this.getLatest();
    return {
      referenceId: self.__referenceId,
      fileName: self.__fileName,
      category: self.__category,
      status: self.__status,
    };
  }

  updateDescriptor(update: {
    status: FileReferenceStatus;
    fileName?: string;
  }): void {
    const self = this.getWritable();
    self.__status = update.status;
    if (update.fileName !== undefined) {
      self.__fileName = update.fileName;
    }
  }

  decorate(editor: LexicalEditor): ReactNode {
    const descriptor = this.getDescriptor();
    return (
      <FileReferenceChip
        {...descriptor}
        onRemove={() => {
          editor.update(() => this.getLatest().remove(), { discrete: true });
        }}
      />
    );
  }
}

export function $createFileReferenceNode(
  descriptor: FileReferenceDescriptor,
): FileReferenceNode {
  return $applyNodeReplacement(new FileReferenceNode(descriptor));
}

export function $isFileReferenceNode(
  node: LexicalNode | null | undefined,
): node is FileReferenceNode {
  return node instanceof FileReferenceNode;
}
