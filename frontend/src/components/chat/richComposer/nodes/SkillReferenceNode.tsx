import type { ReactNode } from "react";
import {
  $applyNodeReplacement,
  $createTextNode,
  DecoratorNode,
  type LexicalNode,
  type NodeKey,
  type SerializedLexicalNode,
  type Spread,
} from "lexical";
import { SkillChip } from "../../SkillChip";
import type { SkillReferenceDescriptor } from "../composerTypes";

export type SerializedSkillReferenceNode = Spread<
  SkillReferenceDescriptor,
  SerializedLexicalNode
>;

export class SkillReferenceNode extends DecoratorNode<ReactNode> {
  __skillName: string;
  __tags: string[];

  static getType(): string {
    return "skill-reference";
  }

  static clone(node: SkillReferenceNode): SkillReferenceNode {
    return new SkillReferenceNode(node.getDescriptor(), node.__key);
  }

  static importJSON(
    serializedNode: SerializedLexicalNode & Record<string, unknown>,
  ): LexicalNode {
    const descriptor = serializedNode as Partial<SerializedSkillReferenceNode>;
    if (descriptor.version !== 1) {
      return $createTextNode(descriptor.skillName || "Skill");
    }
    return $createSkillReferenceNode({
      skillName: descriptor.skillName ?? "Skill",
      tags: descriptor.tags ?? [],
    });
  }

  constructor(
    descriptor: SkillReferenceDescriptor = { skillName: "", tags: [] },
    key?: NodeKey,
  ) {
    super(key);
    this.__skillName = descriptor.skillName;
    this.__tags = [...descriptor.tags];
  }

  createDOM(): HTMLElement {
    const element = document.createElement("span");
    element.className = "composer-reference-node";
    return element;
  }

  updateDOM(): false {
    return false;
  }

  exportJSON(): SerializedSkillReferenceNode {
    const descriptor = this.getDescriptor();
    return {
      ...super.exportJSON(),
      ...descriptor,
      type: "skill-reference",
      version: 1,
    };
  }

  getTextContent(): string {
    return "";
  }

  getDescriptor(): SkillReferenceDescriptor {
    const self = this.getLatest();
    return { skillName: self.__skillName, tags: [...self.__tags] };
  }

  decorate(): ReactNode {
    const { skillName, tags } = this.getDescriptor();
    return (
      <span
        className="composer-skill-reference"
        role="button"
        tabIndex={0}
        aria-label={`Skill ${skillName}`}
        contentEditable={false}
      >
        <SkillChip name={skillName} tags={tags} />
      </span>
    );
  }
}

export function $createSkillReferenceNode(
  descriptor: SkillReferenceDescriptor,
): SkillReferenceNode {
  return $applyNodeReplacement(new SkillReferenceNode(descriptor));
}

export function $isSkillReferenceNode(
  node: LexicalNode | null | undefined,
): node is SkillReferenceNode {
  return node instanceof SkillReferenceNode;
}
