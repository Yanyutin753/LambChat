import { InteractiveIcon } from "./InteractiveIcon";
import { LoadingSpinner } from "./LoadingSpinner";
import { memo, useMemo } from "react";
import { AlertCircle, RotateCcw, Type, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import type { MessageAttachment } from "../../types";
import { ImageWithSkeleton } from "../chat/ChatMessage/ImageWithSkeleton";
import { ExcalidrawThumbnail } from "./ExcalidrawThumbnail";
import {
  getFileTypeInfo,
  formatFileSize as formatFileSizeUtil,
  isExcalidrawFile,
} from "../documents/utils";
import { getFullUrl } from "../../services/api";
import {
  buildChatThumbUrl,
  buildFileCoverUrl,
  isChatCoverableFile,
} from "../../utils/chatThumbs";

// Re-export formatFileSize for external use
// eslint-disable-next-line react-refresh/only-export-components
export const formatFileSize = formatFileSizeUtil;

// Re-export for backward compatibility
// eslint-disable-next-line react-refresh/only-export-components
export function getAttachmentIconInfo(
  mimeType: string,
  fileName?: string,
): {
  icon: React.ElementType;
  bgColor: string;
  iconColor: string;
  label: string;
} {
  const info = getFileTypeInfo(fileName || "", mimeType);
  return {
    icon: info.icon,
    bgColor: info.bg,
    iconColor: info.color,
    label: info.label,
  };
}

export interface AttachmentCardProps {
  attachment: MessageAttachment;
  /** 点击卡片时的回调（预览） */
  onClick?: () => void;
  /** 删除按钮点击回调 */
  onRemove?: () => void;
  /** 取消上传按钮点击回调 */
  onCancel?: () => void;
  /** 显示模式：editable 显示删除按钮，preview 显示预览指示器 */
  variant?: "editable" | "preview";
  /** 尺寸：compact 更紧凑，适合输入框区域 */
  size?: "default" | "compact";
  /** Whether upload is in progress */
  isUploading?: boolean;
  /** Restore long-text attachment back to composer input */
  onSendAsText?: () => void;
  /** Retry a failed upload without discarding the local file resource. */
  onRetry?: () => void;
}

export const AttachmentCard = memo(function AttachmentCard({
  attachment,
  onClick,
  onRemove,
  onCancel,
  variant = "preview",
  size = "default",
  isUploading = false,
  onSendAsText,
  onRetry,
}: AttachmentCardProps) {
  const { t } = useTranslation();
  const {
    icon: FileIcon,
    bgColor,
    iconColor,
    label,
  } = getAttachmentIconInfo(attachment.mimeType, attachment.name);
  const displayLabel = t(label, label);
  const attachmentUrl = attachment.url
    ? getFullUrl(attachment.url) ?? attachment.url
    : "";
  const isImage =
    attachment.mimeType?.startsWith("image/") && Boolean(attachmentUrl);
  const fileExt = useMemo(() => {
    const idx = attachment.name?.lastIndexOf(".");
    return idx != null && idx > 0
      ? attachment.name!.slice(idx + 1).toLowerCase()
      : "";
  }, [attachment.name]);
  const isExcalidraw = isExcalidrawFile(fileExt) && Boolean(attachmentUrl);
  // 服务端封面：PDF 首页/表格前几行/视频首帧，失败回退文件图标（零流量）
  const coverUrl =
    !isImage &&
    !isExcalidraw &&
    Boolean(attachmentUrl) &&
    isChatCoverableFile(fileExt)
      ? buildFileCoverUrl(attachmentUrl)
      : undefined;
  const isThumbnail = isImage || isExcalidraw || Boolean(coverUrl);
  const isCompact = size === "compact";
  const isFailed = Boolean(attachment.uploadError);
  const processingProgress = attachment.uploadProcessingProgress;
  const uploadStatusLabel =
    attachment.uploadStage === "preparing"
      ? t("fileUpload.preparing", "Preparing upload…")
      : attachment.uploadStage === "processing"
        ? `${t("fileUpload.serverProcessing", "Processing on server…")}${
            processingProgress === undefined ? "" : ` ${processingProgress}%`
          }`
        : `${Math.min(99, attachment.uploadProgress ?? 0)}%`;

  const handleClick = () => {
    onClick?.();
  };

  const handleRemove = (e: React.MouseEvent) => {
    e.stopPropagation();
    onRemove?.();
  };

  // 紧凑模式样式（用于 ChatInput）
  if (isCompact) {
    return (
      <div
        className={clsx(
          "attachment-card attachment-card--compact attachment-card-enter",
          "group relative flex items-center gap-2.5 px-3 py-2 select-none",
          isFailed && "attachment-card--failed",
        )}
      >
        <button
          type="button"
          className="attachment-card__preview absolute inset-0 rounded-[inherit]"
          aria-label={attachment.name}
          title={attachment.name}
          onClick={handleClick}
          disabled={isUploading || !onClick}
        />
        {/* 图标/图片 */}
        <div
          className={clsx(
            "pointer-events-none relative shrink-0 flex items-center justify-center rounded-lg overflow-hidden",
            isThumbnail
              ? "size-10 relative overflow-hidden"
              : clsx("size-10", bgColor),
          )}
        >
          {isUploading ? (
            <LoadingSpinner
              color="text-current"
              size={18}
              className={clsx(iconColor, "")}
            />
          ) : isFailed ? (
            <AlertCircle size={18} className="text-red-500" />
          ) : isImage ? (
            <ImageWithSkeleton
              src={attachmentUrl}
              thumbSrc={buildChatThumbUrl(attachmentUrl)}
              alt={attachment.name}
              skipUrlResolve
              inline
            />
          ) : isExcalidraw ? (
            <ExcalidrawThumbnail url={attachmentUrl} alt={attachment.name} />
          ) : coverUrl ? (
            <ImageWithSkeleton
              src={coverUrl}
              alt={attachment.name}
              skipUrlResolve
              inline
              errorFallback={<FileIcon size={18} className={iconColor} />}
            />
          ) : (
            <FileIcon size={18} className={iconColor} />
          )}
        </div>

        {/* 文件信息与操作独立，避免按钮高度撑大文字间距 */}
        <div className="pointer-events-none relative flex flex-col min-w-0 flex-1">
          <span className="text-13 font-medium text-theme-text truncate leading-tight">
            {attachment.name}
          </span>
          <span className="mt-0.5 text-12 text-theme-text-secondary truncate">
            {isUploading
              ? uploadStatusLabel
              : isFailed
                ? t("fileUpload.composerUploadFailed", "Upload failed")
                : formatFileSize(attachment.size)}
          </span>
        </div>

        {/* 仍以文本发送 / 删除/取消 */}
        {variant === "editable" && (
          <div className="attachment-card__actions pointer-events-auto relative flex items-center gap-1 shrink-0">
            {onSendAsText && !isUploading && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onSendAsText();
                }}
                className={clsx(
                  "h-5 px-1.5 rounded-md flex items-center gap-1",
                  "text-theme-text-secondary",
                  "transition-all duration-200 text-10 font-medium",
                  "hover:bg-[color-mix(in_srgb,var(--theme-primary)_12%,transparent)]",
                  "hover:text-[var(--theme-primary)]",
                )}
                title={t("chat.sendLongTextAsText", "仍以文本发送")}
              >
                <InteractiveIcon>
                  <Type size={12} strokeWidth={2.25} />
                </InteractiveIcon>
                <span className="hidden sm:inline">
                  {t("chat.sendLongTextAsText", "仍以文本发送")}
                </span>
              </button>
            )}
            {isUploading && onCancel ? (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onCancel();
                }}
                className={clsx(
                  "size-5 rounded-md flex items-center justify-center",
                  "text-red-500 dark:text-red-400",
                  "opacity-100",
                  "transition-all duration-200",
                  "hover:bg-red-100/80 dark:hover:bg-red-900/40",
                )}
                title={t("fileUpload.cancelUpload")}
              >
                <InteractiveIcon>
                  <X size={12} />
                </InteractiveIcon>
              </button>
            ) : (
              <>
                {isFailed && onRetry ? (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRetry();
                    }}
                    className={clsx(
                      "h-5 px-1.5 rounded-md flex items-center gap-1",
                      "text-red-500 dark:text-red-400 text-10 font-medium",
                      "hover:bg-red-100/80 dark:hover:bg-red-900/40",
                    )}
                    title={t("fileUpload.composerRetry", "Retry")}
                  >
                    <InteractiveIcon>
                      <RotateCcw size={11} />
                    </InteractiveIcon>
                    <span>{t("fileUpload.composerRetry", "Retry")}</span>
                  </button>
                ) : null}
                {onRemove ? (
                  <button
                    type="button"
                    onClick={handleRemove}
                    aria-label={t("common.remove")}
                    className={clsx(
                      "size-5 rounded-md flex items-center justify-center",
                      "text-theme-text-secondary",
                      "transition-all duration-200",
                      "hover:bg-red-100/80 dark:hover:bg-red-900/40",
                      "hover:text-red-500 dark:hover:text-red-400",
                    )}
                  >
                    <InteractiveIcon>
                      <X size={12} />
                    </InteractiveIcon>
                  </button>
                ) : null}
              </>
            )}
          </div>
        )}
      </div>
    );
  }

  // 默认模式样式（用于 ChatMessage）
  return (
    <button
      onClick={handleClick}
      className={clsx(
        "attachment-card group relative flex items-center overflow-hidden",
        "h-14 min-w-0 w-[280px] max-w-full sm:w-[320px]",
        "text-left select-none",
        isUploading && "pointer-events-none",
      )}
      type="button"
      title={attachment.name}
      disabled={isUploading || !onClick}
    >
      {/* 左侧图标/图片区域 */}
      <div
        className={clsx(
          "ml-2 shrink-0 flex items-center justify-center",
          isThumbnail
            ? "size-10 rounded-lg overflow-hidden"
            : clsx("size-10 rounded-lg", bgColor),
        )}
      >
        {isUploading ? (
          <LoadingSpinner
            color="text-current"
            size={18}
            className={clsx(iconColor, "")}
          />
        ) : isImage ? (
          <ImageWithSkeleton
            src={attachmentUrl}
            thumbSrc={buildChatThumbUrl(attachmentUrl)}
            alt={attachment.name}
            skipUrlResolve
            inline
            className="w-full h-full object-cover"
          />
        ) : isExcalidraw ? (
          <ExcalidrawThumbnail
            url={attachmentUrl}
            alt={attachment.name}
            className="w-full h-full object-cover"
          />
        ) : coverUrl ? (
          <ImageWithSkeleton
            src={coverUrl}
            alt={attachment.name}
            skipUrlResolve
            inline
            className="w-full h-full object-cover"
            errorFallback={<FileIcon size={18} className={iconColor} />}
          />
        ) : (
          <FileIcon size={18} className={iconColor} />
        )}
      </div>

      {/* 文件信息 */}
      <div className="flex flex-col justify-center px-3 sm:px-3.5 py-2 min-w-0 flex-1">
        <div className="text-13 sm:text-14 font-medium truncate text-theme-text leading-tight">
          {attachment.name}
        </div>
        <div className="flex items-center justify-between mt-0.5 sm:mt-1 text-11 sm:text-12 text-theme-text-secondary">
          <span className="capitalize truncate">{displayLabel}</span>
          <span className="shrink-0 ml-2">
            {isUploading
              ? t("fileUpload.uploading")
              : formatFileSize(attachment.size)}
          </span>
        </div>
      </div>
    </button>
  );
});
