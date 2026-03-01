import { memo } from "react";
import { X, FileText, Image, Video, Music, File } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { MessageAttachment } from "../../types";

interface AttachmentPreviewProps {
  attachments: MessageAttachment[];
  onRemove: (id: string) => void;
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
}: AttachmentPreviewProps) {
  const { t } = useTranslation();

  return (
    <div className="bg-white dark:bg-stone-800 rounded-lg shadow-lg border border-gray-200 dark:border-stone-700 p-2 space-y-2">
      {attachments.map((attachment) => {
        const Icon = ICON_MAP[attachment.type] || File;

        return (
          <div
            key={attachment.id}
            className="flex items-center gap-2 p-2 rounded-md bg-gray-50 dark:bg-stone-700/50"
          >
            {/* Preview or icon */}
            {attachment.type === "image" &&
            attachment.mimeType.startsWith("image/") ? (
              <div className="w-10 h-10 rounded overflow-hidden bg-gray-200 dark:bg-stone-600 flex-shrink-0">
                <img
                  src={attachment.url}
                  alt={attachment.name}
                  className="w-full h-full object-cover"
                />
              </div>
            ) : (
              <div className="w-10 h-10 rounded bg-gray-200 dark:bg-stone-600 flex items-center justify-center flex-shrink-0">
                <Icon
                  size={18}
                  className="text-stone-500 dark:text-stone-400"
                />
              </div>
            )}

            {/* File info */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-stone-100 truncate">
                {attachment.name}
              </p>
              <p className="text-xs text-gray-500 dark:text-stone-400">
                {formatFileSize(attachment.size)}
              </p>
            </div>

            {/* Remove button */}
            <button
              type="button"
              onClick={() => onRemove(attachment.id)}
              className="p-1 rounded-full hover:bg-gray-200 dark:hover:bg-stone-600 text-gray-500 dark:text-stone-400"
              title={t("fileUpload.removeAttachment")}
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
});
