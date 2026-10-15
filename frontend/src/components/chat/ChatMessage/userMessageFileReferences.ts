import type { MessageAttachment } from "../../../types";
import type { Element, ElementContent, Root } from "hast";

export interface UserMessageReferences {
  attachments?: readonly MessageAttachment[];
  enabledSkills?: readonly string[];
}

export type UserMessageInlineSegment =
  | { kind: "text"; value: string }
  | { kind: "skill"; skillName: string }
  | {
      kind: "file";
      fileName: string;
      referenceNumber: number;
      attachment: MessageAttachment;
    };

const REFERENCE_PATTERN = /\[引用(文件|技能)：([^\]\n]+)\]/g;

/**
 * Restore references in document order, only when attached or explicitly enabled.
 */
export function splitUserMessageFileReferences(
  content: string,
  attachments: readonly MessageAttachment[] = [],
  enabledSkills: readonly string[] = [],
): UserMessageInlineSegment[] {
  const attachmentsByName = new Map(
    attachments.map((attachment) => [attachment.name, attachment]),
  );
  const segments: UserMessageInlineSegment[] = [];
  let textStart = 0;
  let referenceNumber = 0;

  for (const match of content.matchAll(REFERENCE_PATTERN)) {
    const matchStart = match.index ?? 0;
    const marker = match[0];
    const name = match[2];
    const attachment = match[1] === "文件" ? attachmentsByName.get(name) : undefined;
    const isSkill = match[1] === "技能" && enabledSkills.includes(name);
    if (!attachment && !isSkill) continue;

    if (matchStart > textStart) {
      segments.push({
        kind: "text",
        value: content.slice(textStart, matchStart),
      });
    }
    if (isSkill) {
      segments.push({ kind: "skill", skillName: name });
    } else if (attachment) {
      referenceNumber += 1;
      segments.push({ kind: "file", fileName: name, referenceNumber, attachment });
    }
    textStart = matchStart + marker.length;
  }

  if (textStart < content.length) {
    segments.push({ kind: "text", value: content.slice(textStart) });
  }

  return segments.length > 0 ? segments : [{ kind: "text", value: content }];
}

/** Replace references inside parsed Markdown so paragraphs, lists and emphasis stay intact. */
export function rehypeUserMessageReferences(options: UserMessageReferences) {
  return (tree: Root) => {
    let referenceNumber = 0;
    function visit(node: Root | Element) {
      for (let i = 0; i < node.children.length; i++) {
        const child = node.children[i];
        if (child.type === "element") {
          if (!["code", "pre", "a"].includes(child.tagName)) visit(child);
        } else if (child.type === "text") {
          const segments = splitUserMessageFileReferences(child.value, options.attachments, options.enabledSkills);
          if (segments.every(segment => segment.kind === "text")) continue;
          const replacement: ElementContent[] = segments.map(segment => {
            if (segment.kind === "text") return { type: "text", value: segment.value };
            return {
              type: "element", tagName: "span",
              properties: segment.kind === "skill"
                ? { dataSkillName: segment.skillName }
                : { dataFileId: segment.attachment.id, dataReferenceNumber: ++referenceNumber },
              children: [],
            };
          });
          node.children.splice(i, 1, ...replacement);
          i += replacement.length - 1;
        }
      }
    }
    visit(tree);
  };
}
