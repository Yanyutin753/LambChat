import { useEffect, useRef, useState, useCallback } from "react";
import { ThumbsUp, ThumbsDown, X, Send, ImagePlus } from "lucide-react";
import { Dialog } from "../../common/Dialog";
import { Button } from "../../common";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { ConfigPanelErrorCallout } from "../../panels/ConfigPanelErrorCallout";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { uploadApi, type UploadHandle } from "../../../services/api/upload";
import { compressImageFile } from "../../../utils/imageCompression";
import { uuid } from "../../../utils/uuid";
import type { RatingValue } from "../../../types/feedback";
import type { MessageAttachment } from "../../../types/upload";

const MAX_IMAGES = 9;
const actionClass = "!min-h-11 sm:!min-h-9 [@media(pointer:coarse)]:!min-h-11 [&>span]:!whitespace-normal";
const footerActionClass = `${actionClass} min-w-0 flex-1 self-stretch sm:flex-none`;

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
  error?: string;
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
  error,
}: FeedbackDialogProps) {
  const { t } = useTranslation();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadRequest = useRef<symbol | null>(null);
  const uploadHandle = useRef<UploadHandle | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [failedFiles, setFailedFiles] = useState<File[]>([]);

  useEffect(() => {
    setIsUploading(false);
    setUploadError("");
    setFailedFiles([]);
    if (isOpen) textareaRef.current?.focus();
    return () => {
      uploadRequest.current = null;
      uploadHandle.current?.abort();
      uploadHandle.current = null;
    };
  }, [isOpen]);

  const focusSurface = () =>
    textareaRef.current?.closest<HTMLElement>("[data-modal-surface]")?.focus();
  const submit = () => {
    if (isSubmitting || isUploading) return;
    focusSurface();
    onSubmit();
  };
  const handleImageSelect = useCallback(
    async (files: FileList | File[] | null) => {
      if (!isOpen || isSubmitting || uploadRequest.current || !files?.length)
        return;
      const remaining = MAX_IMAGES - attachments.length;
      if (remaining <= 0) {
        toast.error(t("feedback.imageLimit"));
        return;
      }
      const imageFiles = Array.from(files)
        .filter((file) => file.type.startsWith("image/"))
        .slice(0, remaining);
      if (!imageFiles.length) return;
      const request = Symbol("feedback-upload");
      uploadRequest.current = request;
      textareaRef.current
        ?.closest<HTMLElement>("[data-modal-surface]")
        ?.focus();
      setIsUploading(true);
      setUploadError("");
      setFailedFiles([]);
      const next = [...attachments];
      const failed: File[] = [];
      for (const file of imageFiles) {
        try {
          const compressed = await compressImageFile(file, {
            maxDimension: 1280,
            targetSizeKB: 800,
          });
          if (uploadRequest.current !== request) return;
          const handle = uploadApi.uploadFile(compressed, "feedback");
          uploadHandle.current = handle;
          const result = await handle.promise;
          if (uploadRequest.current !== request) return;
          uploadHandle.current = null;
          next.push({ id: uuid(), ...result });
          onAttachmentsChange([...next]);
        } catch (cause) {
          if (uploadRequest.current !== request) return;
          uploadHandle.current = null;
          failed.push(file);
          setUploadError(
            cause instanceof Error ? cause.message : t("feedback.uploadFailed"),
          );
        }
      }
      if (uploadRequest.current !== request) return;
      uploadRequest.current = null;
      setFailedFiles(failed);
      setIsUploading(false);
    },
    [attachments, isOpen, isSubmitting, onAttachmentsChange, t],
  );

  const title =
    rating === "up" ? t("feedback.positive") : t("feedback.negative");
  return (
    <Dialog
      open={isOpen}
      onClose={onClose}
      dismissible={!isSubmitting}
      size="md"
      title={<span className="font-serif">{title}</span>}
      icon={
        rating === "up" ? (
          <ThumbsUp size={16} className="text-theme-text-secondary" />
        ) : (
          <ThumbsDown size={16} className="text-theme-text-secondary" />
        )
      }
      footer={
        <>
          <Button
            variant="secondary"
            className={footerActionClass}
            disabled={isSubmitting || isUploading}
            onClick={() => {
              focusSurface();
              onSkip();
            }}
          >
            {t("feedback.skipAndSubmit")}
          </Button>
          <Button
            variant="primary"
            className={footerActionClass}
            disabled={isUploading}
            loading={isSubmitting}
            leftIcon={<Send size={14} />}
            onClick={submit}
          >
            {error ? t("common.retry") : t("feedback.submit")}
          </Button>
        </>
      }
    >
      <div
        className="space-y-3"
        aria-busy={isSubmitting || isUploading || undefined}
      >
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {attachments.map((attachment) => (
              <div
                key={attachment.id}
                className="group/att relative size-20 shrink-0 overflow-hidden rounded-lg border border-theme-border"
              >
                <img
                  src={attachment.url}
                  alt={attachment.name}
                  className="size-full object-cover"
                />
                <button
                  type="button"
                  aria-label={`${t("common.remove")}: ${attachment.name}`}
                  disabled={isSubmitting || isUploading}
                  onClick={() => {
                    textareaRef.current?.focus();
                    onAttachmentsChange(
                      attachments.filter((item) => item.id !== attachment.id),
                    );
                  }}
                  className="absolute right-0 top-0 flex size-11 items-center justify-center opacity-100 transition-opacity sm:size-7 sm:opacity-0 sm:group-hover/att:opacity-100 sm:focus-visible:opacity-100 [@media(pointer:coarse)]:size-11 [@media(pointer:coarse)]:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-theme-ring disabled:opacity-50"
                >
                  <span className="flex size-5 items-center justify-center rounded-full bg-black/60 text-white">
                    <X size={12} />
                  </span>
                </button>
              </div>
            ))}
          </div>
        )}
        {attachments.length < MAX_IMAGES && (
          <Button
            aria-label={t("feedback.addImage")}
            variant="ghost"
            className={`w-full !justify-start !px-3 !border !border-dashed !border-theme-border ${actionClass}`}
            disabled={isSubmitting || isUploading}
            leftIcon={<ImagePlus size={16} />}
            onClick={() => fileInputRef.current?.click()}
            onDrop={(event) => {
              event.preventDefault();
              void handleImageSelect(event.dataTransfer.files);
            }}
            onDragOver={(event) => event.preventDefault()}
          >
            {t("feedback.addImage")}
          </Button>
        )}
        {isUploading && (
          <div
            role="status"
            className="flex items-center gap-2 text-12 text-theme-text-secondary"
          >
            <LoadingSpinner size="sm" />
            {t("feedback.uploading")}
          </div>
        )}
        {uploadError && (
          <div className="space-y-2">
            <ConfigPanelErrorCallout message={uploadError} />
            <Button
              className={actionClass}
              disabled={isSubmitting || isUploading}
              onClick={() => void handleImageSelect(failedFiles)}
            >
              {t("common.retry")}
            </Button>
          </div>
        )}
        <textarea
          ref={textareaRef}
          aria-label={t("feedback.commentLabel")}
          disabled={isSubmitting}
          value={comment}
          onChange={(event) => onCommentChange(event.target.value)}
          placeholder={t("feedback.commentPlaceholder")}
          className="ui-textarea w-full resize-none !text-16 sm:!text-14 [@media(pointer:coarse)]:!text-16"
          rows={4}
          onKeyDown={(event) => {
            if (
              event.key !== "Enter" ||
              !(event.metaKey || event.ctrlKey) ||
              event.nativeEvent.isComposing ||
              event.keyCode === 229
            )
              return;
            event.preventDefault();
            submit();
          }}
        />
        <p className="hidden text-right text-12 text-theme-text-secondary sm:block">
          {t("feedback.pressEnter")}
        </p>
        {error && <ConfigPanelErrorCallout message={error} />}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          hidden
          disabled={isSubmitting || isUploading}
          onChange={(event) => {
            void handleImageSelect(event.target.files);
            event.target.value = "";
          }}
        />
      </div>
    </Dialog>
  );
}
