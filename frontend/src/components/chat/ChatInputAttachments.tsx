import { useCallback } from "react";
import { uploadApi } from "../../services/api";
import { AttachmentCard } from "../common/AttachmentCard";
import { getFullUrl } from "../../services/api";
import { openAttachmentPreview } from "./attachmentPreviewStore";
import { canRestoreLongTextAttachment } from "./longTextConversion";
import type { MessageAttachment } from "../../types";

interface ChatInputAttachmentsProps {
  attachments: MessageAttachment[];
  onAttachmentsChange: (
    attachments:
      | MessageAttachment[]
      | ((prev: MessageAttachment[]) => MessageAttachment[]),
  ) => void;
  onCancelUpload: (id: string) => void;
  onImageViewerOpen: (url: string) => void;
  /** Optional: max files allowed */
  maxFiles?: number;
  /** Optional: callback to open file picker */
  onAddMore?: () => void;
  /** Restore a long-text attachment back into the composer input. */
  onRestoreLongText?: (attachment: MessageAttachment) => void;
  onRemoveReference?: (referenceId: string) => void;
  onRetryUpload?: (attachment: MessageAttachment) => void;
}

export function ChatInputAttachments({
  attachments,
  onAttachmentsChange,
  onCancelUpload,
  onImageViewerOpen,
  onRestoreLongText,
  onRemoveReference,
  onRetryUpload,
}: ChatInputAttachmentsProps) {
  const handleRemove = useCallback(
    (attachment: MessageAttachment) => {
      if (attachment.composerReferenceId) {
        onRemoveReference?.(attachment.composerReferenceId);
      }
      onAttachmentsChange((prev) => prev.filter((a) => a.id !== attachment.id));
      if (attachment.key && !attachment.isUploading) {
        uploadApi.deleteFile(attachment.key).catch((error) => {
          console.error("Failed to delete file from server:", error);
        });
      }
    },
    [onAttachmentsChange, onRemoveReference],
  );

  if (attachments.length === 0) return null;

  return (
    <div className="mx-3 mt-2.5 -mb-1 flex gap-3 overflow-x-auto attachment-scroll pb-1">
      {attachments.map((attachment) => {
        const isImage =
          attachment.mimeType?.startsWith("image/") && attachment.url;

        return (
          <AttachmentCard
            key={attachment.id}
            attachment={attachment}
            variant="editable"
            size="compact"
            isUploading={attachment.isUploading}
            onClick={() => {
              if (isImage && attachment.url) {
                onImageViewerOpen(getFullUrl(attachment.url) ?? "");
              } else {
                openAttachmentPreview(attachment, "chat-input");
              }
            }}
            onRemove={() => handleRemove(attachment)}
            onCancel={
              attachment.isUploading
                ? () => onCancelUpload(attachment.id)
                : undefined
            }
            onRetry={
              attachment.uploadError && onRetryUpload
                ? () => onRetryUpload(attachment)
                : undefined
            }
            onSendAsText={
              onRestoreLongText && canRestoreLongTextAttachment(attachment)
                ? () => onRestoreLongText(attachment)
                : undefined
            }
          />
        );
      })}
    </div>
  );
}
