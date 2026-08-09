import type { MessageAttachment } from "../../../types";

export type UserMessageInlineSegment =
  | { kind: "text"; value: string }
  | {
      kind: "file";
      fileName: string;
      referenceNumber: number;
      attachment: MessageAttachment;
    };

const FILE_REFERENCE_PATTERN = /\[引用文件：([^\]\n]+)\]/g;

/**
 * Turns composer file markers back into visual references after send.
 * A marker is only promoted when a matching attachment exists, so ordinary
 * user-authored bracket text keeps rendering as text.
 */
export function splitUserMessageFileReferences(
  content: string,
  attachments: readonly MessageAttachment[] = [],
): UserMessageInlineSegment[] {
  const attachmentsByName = new Map(
    attachments.map((attachment) => [attachment.name, attachment]),
  );
  const segments: UserMessageInlineSegment[] = [];
  let textStart = 0;
  let referenceNumber = 0;

  for (const match of content.matchAll(FILE_REFERENCE_PATTERN)) {
    const matchStart = match.index ?? 0;
    const marker = match[0];
    const fileName = match[1];
    const attachment = attachmentsByName.get(fileName);
    if (!attachment) continue;

    if (matchStart > textStart) {
      segments.push({
        kind: "text",
        value: content.slice(textStart, matchStart),
      });
    }
    referenceNumber += 1;
    segments.push({
      kind: "file",
      fileName,
      referenceNumber,
      attachment,
    });
    textStart = matchStart + marker.length;
  }

  if (textStart < content.length) {
    segments.push({ kind: "text", value: content.slice(textStart) });
  }

  return segments.length > 0 ? segments : [{ kind: "text", value: content }];
}
