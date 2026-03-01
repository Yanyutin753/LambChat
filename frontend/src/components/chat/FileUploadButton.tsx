import { useRef, useState, useCallback, memo } from "react";
import { Paperclip, Upload } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { uploadApi } from "../../services/api";
import { AttachmentPreview } from "./AttachmentPreview";
import type {
  MessageAttachment,
  FileCategory,
  UploadResult,
  Permission,
} from "../../types";

interface FileUploadButtonProps {
  onAttachmentsChange?: (attachments: MessageAttachment[]) => void;
}

// Permission mapping
const CATEGORY_PERMISSIONS: Record<FileCategory, Permission> = {
  image: Permission.FILE_UPLOAD_IMAGE,
  video: Permission.FILE_UPLOAD_VIDEO,
  audio: Permission.FILE_UPLOAD_AUDIO,
  document: Permission.FILE_UPLOAD_DOCUMENT,
};

function getFileCategory(file: File): FileCategory {
  const type = file.type.toLowerCase();
  if (type.startsWith("image/")) return "image";
  if (type.startsWith("video/")) return "video";
  if (type.startsWith("audio/")) return "audio";
  return "document";
}

export const FileUploadButton = memo(function FileUploadButton({
  onAttachmentsChange,
}: FileUploadButtonProps) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [attachments, setAttachments] = useState<MessageAttachment[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  // Check if user has any upload permission
  const canUpload = Object.values(CATEGORY_PERMISSIONS).some((perm) =>
    hasPermission(perm),
  );

  const handleFileSelect = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0 || isUploading) return;

      setIsUploading(true);
      const newAttachments: MessageAttachment[] = [];

      try {
        for (const file of Array.from(files)) {
          const category = getFileCategory(file);

          // Check permission
          const requiredPerm = CATEGORY_PERMISSIONS[category];
          if (!hasPermission(requiredPerm)) {
            alert(
              t("fileUpload.noPermission", {
                type: t(`fileUpload.categories.${category}`),
              }),
            );
            continue;
          }

          // Upload file
          const result: UploadResult = await uploadApi.uploadFile(file);

          newAttachments.push({
            id: crypto.randomUUID(),
            key: result.key,
            name: result.name || file.name,
            type: result.type as FileCategory,
            mimeType: result.mimeType,
            size: result.size,
            url: result.url,
          });
        }

        setAttachments((prev) => {
          const updated = [...prev, ...newAttachments];
          onAttachmentsChange?.(updated);
          return updated;
        });
      } catch (error) {
        console.error("Upload failed:", error);
        alert(t("fileUpload.uploadFailed"));
      } finally {
        setIsUploading(false);
      }
    },
    [hasPermission, isUploading, onAttachmentsChange, t],
  );

  const handleRemove = useCallback(
    (id: string) => {
      setAttachments((prev) => {
        const updated = prev.filter((a) => a.id !== id);
        onAttachmentsChange?.(updated);
        return updated;
      });
    },
    [onAttachmentsChange],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      handleFileSelect(e.dataTransfer.files);
    },
    [handleFileSelect],
  );

  if (!canUpload) return null;

  return (
    <div
      className="relative"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv"
        onChange={(e) => handleFileSelect(e.target.files)}
      />

      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={isUploading}
        className={`flex items-center justify-center rounded-full p-2 border transition-all duration-300 ${
          isDragging
            ? "border-purple-500 bg-purple-50 dark:border-purple-700 dark:bg-purple-900/30"
            : "border-gray-200 dark:border-stone-700 bg-transparent hover:bg-gray-100 dark:hover:bg-stone-700"
        } text-stone-500 dark:text-stone-300`}
        title={t("fileUpload.title")}
      >
        {isUploading ? (
          <Upload size={18} className="animate-pulse" />
        ) : (
          <Paperclip size={18} />
        )}
      </button>

      {/* Drag overlay */}
      {isDragging && (
        <div
          className="absolute inset-0 rounded-full border-2 border-dashed border-purple-400 bg-purple-50/80 dark:bg-purple-900/30 flex items-center justify-center -m-1"
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <Paperclip size={18} className="text-purple-500" />
        </div>
      )}

      {/* Attachment preview */}
      {attachments.length > 0 && (
        <div className="absolute bottom-full left-0 mb-2 w-64">
          <AttachmentPreview
            attachments={attachments}
            onRemove={handleRemove}
          />
        </div>
      )}
    </div>
  );
});
