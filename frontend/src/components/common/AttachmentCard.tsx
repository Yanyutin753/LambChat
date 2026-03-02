import { memo } from "react";
import { X, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import type { MessageAttachment } from "../../types";
import {
  getFileTypeInfo,
  formatFileSize as formatFileSizeUtil,
} from "../documents/utils";

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
  /** 显示模式：editable 显示删除按钮，preview 显示预览指示器 */
  variant?: "editable" | "preview";
  /** 尺寸：compact 更紧凑，适合输入框区域 */
  size?: "default" | "compact";
  /** Whether upload is in progress */
  isUploading?: boolean;
}

export const AttachmentCard = memo(function AttachmentCard({
  attachment,
  onClick,
  onRemove,
  variant = "preview",
  size = "default",
  isUploading = false,
}: AttachmentCardProps) {
  const { t } = useTranslation();
  const {
    icon: FileIcon,
    bgColor,
    iconColor,
    label,
  } = getAttachmentIconInfo(attachment.mimeType, attachment.name);
  const isImage = attachment.mimeType?.startsWith("image/") && attachment.url;
  const isCompact = size === "compact";

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
        onClick={handleClick}
        className={clsx(
          "group relative flex items-center gap-2.5 px-3 py-2",
          "rounded-xl border border-gray-200/60 dark:border-stone-700/60",
          "bg-gradient-to-br from-white to-gray-50/80 dark:from-stone-800 dark:to-stone-850",
          "shadow-sm backdrop-blur-sm cursor-pointer select-none",
          "transition-all duration-200 ease-out",
          "hover:shadow-md hover:shadow-gray-200/40 dark:hover:shadow-stone-900/40",
          "hover:border-gray-300/70 dark:hover:border-stone-600/70",
          "hover:-translate-y-0.5",
          "active:scale-[0.98]",
          isUploading && "pointer-events-none",
        )}
      >
        {/* 图标/图片 */}
        <div
          className={clsx(
            "shrink-0 flex items-center justify-center rounded-lg overflow-hidden",
            "transition-transform duration-200",
            !isUploading && "group-hover:scale-105",
            isImage ? "size-10" : clsx("size-10", bgColor),
          )}
        >
          {isUploading ? (
            <Loader2 size={18} className={clsx(iconColor, "animate-spin")} />
          ) : isImage ? (
            <img
              src={attachment.url}
              alt={attachment.name}
              className="w-full h-full object-cover"
            />
          ) : (
            <FileIcon size={18} className={iconColor} />
          )}
        </div>

        {/* 文件信息 */}
        <div className="flex flex-col min-w-0 flex-1">
          <span className="text-[13px] font-medium text-gray-800 dark:text-stone-100 truncate max-w-[120px] sm:max-w-[160px] leading-tight">
            {attachment.name}
          </span>
          <span className="text-[11px] text-gray-400 dark:text-stone-500 mt-0.5">
            {isUploading
              ? t("fileUpload.uploading")
              : formatFileSize(attachment.size)}
          </span>
        </div>

        {/* 删除按钮 */}
        {variant === "editable" && onRemove && !isUploading && (
          <button
            type="button"
            onClick={handleRemove}
            className={clsx(
              "shrink-0 size-6 rounded-full flex items-center justify-center",
              "bg-gray-100/80 dark:bg-stone-700/80",
              "text-gray-400 dark:text-stone-500",
              "opacity-0 group-hover:opacity-100",
              "transition-all duration-200",
              "hover:bg-red-100 dark:hover:bg-red-900/30",
              "hover:text-red-500 dark:hover:text-red-400",
            )}
          >
            <X size={12} />
          </button>
        )}
      </div>
    );
  }

  // 默认模式样式（用于 ChatMessage）
  return (
    <button
      onClick={handleClick}
      className={clsx(
        "group relative flex items-center overflow-hidden",
        "h-12 sm:h-14 min-w-[200px] max-w-[280px] sm:min-w-[240px] sm:max-w-[320px]",
        "bg-gradient-to-br from-white to-gray-50/80",
        "dark:from-stone-800 dark:to-stone-850",
        "rounded-2xl sm:rounded-xl",
        "border border-gray-200/60 dark:border-stone-700/60",
        "shadow-sm backdrop-blur-sm",
        "text-left cursor-pointer select-none",
        "transition-all duration-300 ease-out",
        "hover:shadow-lg hover:shadow-gray-200/50 dark:hover:shadow-stone-900/50",
        "hover:border-gray-300/80 dark:hover:border-stone-600/80",
        "hover:-translate-y-0.5 hover:scale-[1.02]",
        "active:scale-[0.98] active:shadow-sm",
        isUploading && "pointer-events-none",
      )}
      type="button"
    >
      {/* 左侧图标/图片区域 */}
      <div
        className={clsx(
          "shrink-0 flex items-center justify-center",
          "transition-transform duration-300",
          !isUploading && "group-hover:scale-105",
          isImage
            ? "size-12 sm:size-14 rounded-l-2xl sm:rounded-l-xl overflow-hidden"
            : clsx("size-12 sm:size-14 rounded-l-2xl sm:rounded-l-xl", bgColor),
        )}
      >
        {isUploading ? (
          <Loader2 size={18} className={clsx(iconColor, "animate-spin")} />
        ) : isImage ? (
          <>
            <img
              src={attachment.url}
              alt={attachment.name}
              className="w-full h-full object-cover"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
          </>
        ) : (
          <FileIcon
            size={18}
            className={clsx(
              iconColor,
              "transition-transform duration-300 group-hover:scale-110",
            )}
          />
        )}
      </div>

      {/* 文件信息 */}
      <div className="flex flex-col justify-center px-3 sm:px-3.5 py-2 min-w-0 flex-1">
        <div className="text-[13px] sm:text-sm font-medium truncate text-gray-800 dark:text-stone-100 leading-tight">
          {attachment.name}
        </div>
        <div className="flex items-center justify-between mt-0.5 sm:mt-1 text-[11px] sm:text-xs text-gray-400 dark:text-stone-500">
          <span className="capitalize truncate">{label}</span>
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
