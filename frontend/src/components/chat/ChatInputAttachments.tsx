import { useCallback } from "react";
import { getFullUrl, uploadApi } from "../../services/api";
import { AttachmentCard } from "../common/AttachmentCard";
import { openAttachmentPreview } from "./attachmentPreviewStore";
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
}

export function ChatInputAttachments({
  attachments,
  onAttachmentsChange,
  onCancelUpload,
  onImageViewerOpen,
}: ChatInputAttachmentsProps) {
  const handleRemove = useCallback(
    (attachment: MessageAttachment) => {
      onAttachmentsChange((prev) => prev.filter((a) => a.id !== attachment.id));
      if (attachment.key && !attachment.isUploading) {
        uploadApi.deleteFile(attachment.key).catch((error) => {
          console.error("Failed to delete file from server:", error);
        });
      }
    },
    [onAttachmentsChange],
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
          />
        );
      })}
    </div>
  );
}
