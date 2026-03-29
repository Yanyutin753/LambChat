import { useState, useRef, useCallback, memo, useEffect } from "react";
import { Paperclip, Image, Video, Music, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { useAuth } from "../../hooks/useAuth";
import { useFileUpload } from "../../hooks/useFileUpload";
import type { MessageAttachment, FileCategory } from "../../types";
import { Permission } from "../../types";

interface FileUploadButtonProps {
  attachments?: MessageAttachment[];
  onAttachmentsChange?: (
    attachments:
      | MessageAttachment[]
      | ((prev: MessageAttachment[]) => MessageAttachment[]),
  ) => void;
}

// Permission mapping
const CATEGORY_PERMISSIONS: Record<FileCategory, Permission> = {
  image: Permission.FILE_UPLOAD_IMAGE,
  video: Permission.FILE_UPLOAD_VIDEO,
  audio: Permission.FILE_UPLOAD_AUDIO,
  document: Permission.FILE_UPLOAD_DOCUMENT,
};

// Accept filters
const CATEGORY_ACCEPT_MAP: Record<FileCategory, string> = {
  image: "image/*",
  video: "video/*",
  audio: "audio/*",
  document: ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv",
};

// Icons
const CATEGORY_ICONS: Record<FileCategory, React.ElementType> = {
  image: Image,
  video: Video,
  audio: Music,
  document: FileText,
};

export const FileUploadButton = memo(function FileUploadButton({
  attachments = [],
  onAttachmentsChange,
}: FileUploadButtonProps) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<FileCategory | null>(
    null,
  );

  const { uploadLimits, uploadFiles } = useFileUpload({
    attachments,
    onAttachmentsChange: onAttachmentsChange!,
  });

  // Get available categories based on permissions
  const availableCategories = Object.keys(CATEGORY_PERMISSIONS).filter((cat) =>
    hasPermission(CATEGORY_PERMISSIONS[cat as FileCategory]),
  ) as FileCategory[];

  // Check if user has any upload permission
  const canUpload = availableCategories.length > 0;

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Handle file selection from the dropdown or file picker
  const handleFiles = useCallback(
    (files: FileList | null, category?: FileCategory) => {
      if (!files || files.length === 0) return;

      for (const file of Array.from(files)) {
        const fileCategory =
          category || file.type.startsWith("image/")
            ? "image"
            : file.type.startsWith("video/")
              ? "video"
              : file.type.startsWith("audio/")
                ? "audio"
                : "document";

        if (!hasPermission(CATEGORY_PERMISSIONS[fileCategory])) {
          toast.error(
            t("fileUpload.noPermission", {
              type: t(`fileUpload.categories.${fileCategory}`),
            }),
          );
          continue;
        }
      }

      // Delegate count validation + upload to the hook
      uploadFiles(files, category);
    },
    [hasPermission, uploadFiles, t],
  );

  // Handle category selection from dropdown
  const handleCategorySelect = (category: FileCategory) => {
    setSelectedCategory(category);
    setShowDropdown(false);

    // Update file input accept filter and click
    if (fileInputRef.current) {
      fileInputRef.current.accept = CATEGORY_ACCEPT_MAP[category];
      fileInputRef.current.click();
    }
  };

  // Handle file input change
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files, selectedCategory || undefined);
    e.target.value = "";
  };

  if (!canUpload) return null;

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Upload button */}
      <button
        type="button"
        onClick={() => setShowDropdown(!showDropdown)}
        className="flex items-center justify-center rounded-full w-8 h-8 border border-stone-200 dark:border-stone-700 bg-transparent hover:bg-stone-100 dark:hover:bg-stone-700 text-stone-500 dark:text-stone-300 transition-all duration-300"
        title={t("fileUpload.title")}
      >
        <Paperclip size={18} />
      </button>

      {/* Dropdown menu */}
      {showDropdown && (
        <div className="absolute bottom-full left-0 mb-2 z-50 w-52 rounded-xl bg-white dark:bg-stone-800 shadow-lg border border-stone-200/80 dark:border-stone-700/80 overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200">
          {availableCategories.map((category) => {
            const Icon = CATEGORY_ICONS[category];
            return (
              <button
                key={category}
                type="button"
                onClick={() => handleCategorySelect(category)}
                className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-[13px] text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-700/60 transition-colors"
              >
                <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-stone-100 dark:bg-stone-700">
                  <Icon
                    size={14}
                    className="text-stone-500 dark:text-stone-400"
                  />
                </div>
                <span className="flex-1 text-left font-medium">
                  {t(`fileUpload.categories.${category}`)}
                </span>
                {uploadLimits && (
                  <span className="text-[11px] tabular-nums text-stone-400 dark:text-stone-500">
                    {uploadLimits[category]}MB
                  </span>
                )}
              </button>
            );
          })}
          {uploadLimits && (
            <div className="px-3.5 py-2 border-t border-stone-100 dark:border-stone-700/60 text-xs text-stone-400 dark:text-stone-500">
              {t("fileUpload.maxFilesSummary", {
                maxFiles: uploadLimits.maxFiles,
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
});
