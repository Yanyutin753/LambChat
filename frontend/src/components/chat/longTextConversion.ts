import type { MessageAttachment } from "../../types";
import { PASTE_TEXT_THRESHOLD } from "./chatInputConstants";

/** Shared threshold for paste/input long-text conversion. */
export const LONG_TEXT_THRESHOLD = PASTE_TEXT_THRESHOLD;

export function shouldConvertLongText(
  text: string,
  threshold: number = LONG_TEXT_THRESHOLD,
): boolean {
  return text.length > threshold;
}

export function buildLongTextFileName(date: Date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  const stamp = [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ].join("");
  return `long-text-${stamp}.txt`;
}

export function createLongTextFile(
  text: string,
  name: string = buildLongTextFileName(),
): File {
  return new File([text], name, { type: "text/plain" });
}

export function isLongTextAttachment(
  attachment: MessageAttachment | null | undefined,
): boolean {
  return Boolean(attachment?.fromLongText);
}

export function canRestoreLongTextAttachment(
  attachment: MessageAttachment | null | undefined,
): boolean {
  return Boolean(
    attachment?.fromLongText &&
      typeof attachment.localOriginalText === "string" &&
      attachment.localOriginalText.length > 0,
  );
}

export function restoreInputFromLongTextAttachment(
  attachment: MessageAttachment,
): string {
  return attachment.localOriginalText ?? "";
}

export function stripLocalAttachmentFields(
  attachments: MessageAttachment[] | undefined,
): MessageAttachment[] | undefined {
  if (!attachments) return attachments;
  return attachments.map((attachment) => {
    const cleaned = { ...attachment };
    delete cleaned.localOriginalText;
    delete cleaned.fromLongText;
    delete cleaned.uploadProgress;
    delete cleaned.isUploading;
    delete cleaned.composerReferenceId;
    delete cleaned.uploadError;
    return cleaned;
  });
}

export function prepareLongTextSubmit({
  message,
  attachments,
}: {
  message: string;
  attachments?: MessageAttachment[];
}): {
  message: string;
  attachments?: MessageAttachment[];
} {
  return {
    message: message.trim(),
    attachments: stripLocalAttachmentFields(attachments),
  };
}

export function shouldSkipLongTextConversion({
  text,
  allowOversizedText,
  expanded,
}: {
  text: string;
  allowOversizedText: boolean;
  expanded: boolean;
}): boolean {
  if (!shouldConvertLongText(text)) return true;
  if (allowOversizedText) return true;
  if (expanded) return true;
  return false;
}

export function buildLongTextClientMeta(
  originalText: string,
  composerReferenceId?: string,
): Pick<
  MessageAttachment,
  "fromLongText" | "localOriginalText" | "composerReferenceId"
> {
  return {
    fromLongText: true,
    localOriginalText: originalText,
    composerReferenceId,
  };
}
