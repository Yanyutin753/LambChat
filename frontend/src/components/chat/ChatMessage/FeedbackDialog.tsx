import { useEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import {
  ThumbsUp,
  ThumbsDown,
  X,
  Send,
  ImagePlus,
  Loader2,
} from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { useSwipeToClose } from "../../../hooks/useSwipeToClose";
import { useBodyScrollLock } from "../../../hooks/useBodyScrollLock";
import { uploadApi } from "../../../services/api/upload";
import { compressImageFile } from "../../../utils/imageCompression";
import { uuid } from "../../../utils/uuid";
import type { RatingValue } from "../../../types/feedback";
import type { MessageAttachment } from "../../../types/upload";

const MAX_IMAGES = 9;

interface FeedbackDialogProps {
  isOpen: boolean;
  onClose: () => void;
  rating: RatingValue;
  comment: string;
  onCommentChange: (value: string) => void;
  onSubmit: () => void;
  onSkip: () => void;
  isSubmitting: boolean;
  attachments: MessageAttachment[];
  onAttachmentsChange: (attachments: MessageAttachment[]) => void;
}

export function FeedbackDialog({
  isOpen,
  onClose,
  rating,
  comment,
  onCommentChange,
  onSubmit,
  onSkip,
  isSubmitting,
  attachments,
  onAttachmentsChange,
}: FeedbackDialogProps) {
  const { t } = useTranslation();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const swipeRef = useSwipeToClose({ onClose, enabled: isOpen });
  useBodyScrollLock(isOpen);
  const [isUploading, setIsUploading] = useState(false);

  useEffect(() => {
    if (isOpen && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onSubmit();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, onSubmit]);

  const handleImageSelect = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;

      const remaining = MAX_IMAGES - attachments.length;
      if (remaining <= 0) {
        toast.error(t("feedback.imageLimit", "最多上传 9 张图片"));
        return;
      }

      const imageFiles = Array.from(files)
        .filter((f) => f.type.startsWith("image/"))
        .slice(0, remaining);

      if (imageFiles.length === 0) return;

      setIsUploading(true);
      const newAttachments: MessageAttachment[] = [...attachments];

      for (const file of imageFiles) {
        try {
          const compressed = await compressImageFile(file, {
            maxDimension: 1280,
            targetSizeKB: 800,
          });
          const handle = uploadApi.uploadFile(compressed, "feedback");
          const result = await handle.promise;

          newAttachments.push({
            id: uuid(),
            key: result.key,
            name: result.name,
            type: result.type,
            mimeType: result.mimeType,
            size: result.size,
            url: result.url,
          });
          onAttachmentsChange([...newAttachments]);
        } catch (err) {
          console.error("Failed to upload image:", err);
          toast.error(
            err instanceof Error
              ? err.message
              : t("feedback.uploadFailed", "图片上传失败"),
          );
        }
      }

      setIsUploading(false);
    },
    [attachments, onAttachmentsChange, t],
  );

  const handleRemoveAttachment = useCallback(
    (id: string) => {
      onAttachmentsChange(attachments.filter((a) => a.id !== id));
    },
    [attachments, onAttachmentsChange],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      handleImageSelect(e.dataTransfer.files);
    },
    [handleImageSelect],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  if (!isOpen) return null;

  return createPortal(
    <>
      <div className="fixed inset-0 z-[299] bg-black/50" onClick={onClose} />

      <div
        data-yields-sidebar
        className="safe-area-viewport-padding fixed inset-0 z-[300] flex items-end sm:items-center sm:justify-center sm:pointer-events-none"
      >
        <div
          ref={swipeRef as React.RefObject<HTMLDivElement>}
          className="relative z-10 w-full sm:max-w-md sm:mx-4 sm:pointer-events-auto bg-theme-bg-card dark:bg-stone-800 sm:rounded-xl rounded-t-xl shadow-xl border border-stone-200 dark:border-stone-700 overflow-hidden duration-300 animate-slide-up-sheet sm:animate-in sm:fade-in sm:zoom-in-95 sm:duration-200"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-stone-200 dark:border-stone-700">
            <div className="sm:hidden absolute top-2 left-1/2 -translate-x-1/2 w-9 h-1 bg-stone-300 dark:bg-stone-600 rounded-full" />
            <div className="flex items-center gap-2 pt-2 sm:pt-0">
              <span
                className={clsx(
                  "flex h-7 w-7 items-center justify-center rounded-full bg-stone-100 text-stone-600 dark:bg-stone-700 dark:text-stone-300",
                )}
              >
                {rating === "up" ? (
                  <ThumbsUp size={14} />
                ) : (
                  <ThumbsDown size={14} />
                )}
              </span>
              <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                {rating === "up"
                  ? t("feedback.positive")
                  : t("feedback.negative")}
              </h3>
            </div>
            <button
              onClick={onClose}
              className="p-1 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
            >
              <X size={20} className="text-stone-500 dark:text-stone-400" />
            </button>
          </div>

          {/* Content */}
          <div className="p-5">
            {/* Image attachments */}
            {attachments.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-2">
                {attachments.map((attachment) => (
                  <div
                    key={attachment.id}
                    className="relative group/att h-20 w-20 rounded-lg overflow-hidden border border-stone-200 dark:border-stone-700 flex-shrink-0"
                  >
                    <img
                      src={attachment.url}
                      alt={attachment.name}
                      className="h-full w-full object-cover"
                    />
                    <button
                      onClick={() => handleRemoveAttachment(attachment.id)}
                      className="absolute top-0.5 right-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-black/60 text-white opacity-0 group-hover/att:opacity-100 transition-opacity"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
                {attachments.length < MAX_IMAGES && !isUploading && (
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex h-20 w-20 items-center justify-center rounded-lg border border-dashed border-stone-300 dark:border-stone-600 text-stone-400 dark:text-stone-500 hover:border-stone-400 dark:hover:border-stone-500 hover:text-stone-500 dark:hover:text-stone-400 transition-colors flex-shrink-0"
                  >
                    <ImagePlus size={20} />
                  </button>
                )}
              </div>
            )}

            {/* Upload progress indicator */}
            {isUploading && (
              <div className="mb-3 flex items-center gap-2 text-xs text-stone-400 dark:text-stone-500">
                <Loader2 size={14} className="animate-spin" />
                <span>{t("feedback.uploading", "上传中...")}</span>
              </div>
            )}

            {/* Drop zone / add image button (when no attachments) */}
            {attachments.length === 0 && !isUploading && (
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onClick={() => fileInputRef.current?.click()}
                className="mb-3 flex items-center gap-2 rounded-lg border border-dashed border-stone-300 dark:border-stone-600 px-3 py-2 text-stone-400 dark:text-stone-500 hover:border-stone-400 dark:hover:border-stone-500 hover:text-stone-500 dark:hover:text-stone-400 transition-colors cursor-pointer"
              >
                <ImagePlus size={16} />
                <span className="text-sm">
                  {t("feedback.addImage", "添加图片（最多 9 张）")}
                </span>
              </div>
            )}

            <textarea
              ref={textareaRef}
              value={comment}
              onChange={(e) => onCommentChange(e.target.value)}
              placeholder={
                t("feedback.commentPlaceholder") || "What could be improved?"
              }
              className={clsx(
                "w-full resize-none rounded-lg border border-stone-200 p-3 text-sm",
                "bg-stone-50 dark:border-stone-700 dark:bg-stone-900",
                "text-stone-900 dark:text-stone-100",
                "placeholder:text-stone-400 dark:placeholder:text-stone-500",
                "focus:border-stone-400 focus:outline-none focus:ring-1 focus:ring-stone-400",
                "transition-colors",
              )}
              rows={4}
            />
            <div className="mt-2 text-xs text-stone-400 text-right">
              {t("feedback.pressEnter") || "⌘+Enter to send"}
            </div>
          </div>

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => {
              handleImageSelect(e.target.files);
              e.target.value = "";
            }}
          />

          {/* Footer */}
          <div className="safe-area-bottom flex items-center justify-end gap-2 px-5 pt-4 [--safe-area-bottom-extra:1rem] bg-stone-50 dark:bg-stone-900/50 border-t border-stone-100 dark:border-stone-700">
            <button
              onClick={onSkip}
              disabled={isSubmitting || isUploading}
              className="px-4 py-2 text-sm font-medium text-stone-700 dark:text-stone-300 bg-theme-bg-card dark:bg-stone-800 border border-stone-200 dark:border-stone-600 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t("common.skip") || "Skip"}
            </button>
            <button
              onClick={onSubmit}
              disabled={isSubmitting || isUploading}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-stone-900 hover:bg-stone-800 dark:bg-stone-600 dark:hover:bg-stone-500 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <span className="relative h-4 w-4">
                  <span className="absolute inset-0 rounded-full border-2 border-white/30 dark:border-stone-700" />
                  <span className="absolute inset-0 rounded-full border-2 border-transparent border-t-white dark:border-t-stone-300 animate-spin will-change-transform" />
                </span>
              ) : (
                <Send size={14} />
              )}
              <span>{t("feedback.submit") || "Submit"}</span>
            </button>
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
