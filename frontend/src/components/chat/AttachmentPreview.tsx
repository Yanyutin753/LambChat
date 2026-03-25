import { memo } from "react";
import { X, FileText, Image, Video, Music, File } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { MessageAttachment } from "../../types";

interface AttachmentPreviewProps {
  attachments: MessageAttachment[];
  onRemove: (id: string) => void;
  onCancel?: (id: string) => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const ICON_MAP = {
  image: Image,
  video: Video,
  audio: Music,
  document: FileText,
};

export const AttachmentPreview = memo(function AttachmentPreview({
  attachments,
  onRemove,
  onCancel,
}: AttachmentPreviewProps) {
  const { t } = useTranslation();

  return (
    <div className="bg-white dark:bg-stone-800 rounded-lg shadow-lg border border-stone-200 dark:border-stone-700 p-2 space-y-2">
      {attachments.map((attachment) => {
        const Icon = ICON_MAP[attachment.type] || File;
        const isUploading = !!attachment.isUploading;

        return (
          <div
            key={attachment.id}
            className="flex items-center gap-2 p-2 rounded-md bg-stone-50 dark:bg-stone-700/50 relative overflow-hidden"
          >
            {/* Progress bar */}
            {isUploading && (
              <div
                className="absolute inset-y-0 left-0 bg-blue-400/20 dark:bg-blue-500/20 transition-all duration-200"
                style={{
                  width: `${attachment.uploadProgress ?? 0}%`,
                }}
              />
            )}

            {/* Preview or icon */}
            {attachment.type === "image" &&
            attachment.mimeType.startsWith("image/") ? (
              <div className="w-10 h-10 rounded overflow-hidden bg-stone-200 dark:bg-stone-600 flex-shrink-0 relative z-[1]">
                <img
                  src={attachment.url}
                  alt={attachment.name}
                  className="w-full h-full object-cover"
                />
              </div>
            ) : (
              <div className="w-10 h-10 rounded bg-stone-200 dark:bg-stone-600 flex items-center justify-center flex-shrink-0 relative z-[1]">
                <Icon
                  size={18}
                  className="text-stone-500 dark:text-stone-400"
                />
              </div>
            )}

            {/* File info */}
            <div className="flex-1 min-w-0 relative z-[1]">
              <p className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">
                {attachment.name}
              </p>
              <p className="text-xs text-stone-500 dark:text-stone-400">
                {isUploading
                  ? `${attachment.uploadProgress ?? 0}%`
                  : formatFileSize(attachment.size)}
              </p>
            </div>

            {/* Remove / Cancel button */}
            <button
              type="button"
              onClick={() =>
                isUploading && onCancel
                  ? onCancel(attachment.id)
                  : onRemove(attachment.id)
              }
              className="p-1 rounded-full hover:bg-stone-200 dark:hover:bg-stone-600 text-stone-500 dark:text-stone-400 relative z-[1]"
              title={
                isUploading
                  ? t("fileUpload.cancelUpload")
                  : t("fileUpload.removeAttachment")
              }
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
});
