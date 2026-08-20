import type { MessageAttachment } from "../../types";

/** Only completed, server-addressable attachments may enter a message request. */
export function isAttachmentSendable(attachment: MessageAttachment): boolean {
  return Boolean(
    attachment.id.trim() &&
      attachment.key.trim() &&
      attachment.name.trim() &&
      attachment.mimeType.trim() &&
      Number.isFinite(attachment.size) &&
      attachment.size > 0 &&
      !attachment.isUploading &&
      !attachment.uploadError,
  );
}

export function areAttachmentsSendable(attachments: MessageAttachment[]): boolean {
  return attachments.every(isAttachmentSendable);
}
