import { useState, useRef, useCallback, memo, useEffect } from "react";
import { createPortal } from "react-dom";
import { Paperclip, Image, Video, Music, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { useAuth } from "../../hooks/useAuth";
import { useFileUpload } from "../../hooks/useFileUpload";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import { getFileUploadDropdownStyle } from "./fileUploadDropdownStyle";
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
  image:
    "image/*,.heic,.heif,.avif,.webp,.bmp,.ico,.tiff,.tif,.svg,.psd,.eps,.tga,.pcx,.jxl,.dng",
  video:
    "video/*,.mkv,.flv,.wmv,.avi,.mov,.m4v,.mpeg,.mpg,.3gp,.3g2,.ogv,.ts,.mts,.m2ts,.vob,.divx,.rm,.rmvb,.f4v",
  audio:
    "audio/*,.m4a,.mp3,.wav,.ogg,.aac,.flac,.wma,.opus,.aiff,.caf,.amr,.mid,.midi,.ape,.alac,.wv",
  document:
    ".pdf,.doc,.docx,.dot,.dotx,.docm,.xls,.xlsx,.xlsm,.csv,.xlt,.ods,.ppt,.pptx,.potx,.ppsx,.pptm,.odp,.txt,.md,.csv,.rtf,.odt,.epub,.dxf,.dwg,.log,.json,.xml,.html,.htm,.yaml,.yml,.toml,.ini,.cfg,.tex,.diff,.patch,.py,.js,.ts,.jsx,.tsx,.vue,.svelte,.go,.rs,.rb,.php,.java,.c,.cpp,.h,.cs,.swift,.kt,.scala,.dart,.lua,.r,.pl,.sql,.sh,.bash,.zsh,.fish,.ps1,.bat,.cmd,.properties,.gradle,.cmake,.env,.graphql,.proto,.zip,.rar,.7z,.tar,.gz,.bz2,.xz,.tgz",
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
  const triggerRef = useRef<HTMLButtonElement>(null);
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
    if (!showDropdown) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (triggerRef.current?.contains(e.target as Node)) return;
      if (dropdownRef.current?.contains(e.target as Node)) return;
      setShowDropdown(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showDropdown]);

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

  const dropdownStyle = useStickyDropdownPosition(
    triggerRef,
    showDropdown,
    (rect) =>
      getFileUploadDropdownStyle(rect, {
        viewportWidth: window.visualViewport?.width ?? window.innerWidth,
        viewportHeight: window.visualViewport?.height ?? window.innerHeight,
      }),
  );

  if (!canUpload) return null;

  return (
    <>
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
        ref={triggerRef}
        type="button"
        onClick={() => setShowDropdown(!showDropdown)}
        className="chat-tool-btn"
        title={t("fileUpload.title")}
      >
        <Paperclip size={18} />
      </button>

      {/* Dropdown menu via portal */}
      {showDropdown &&
        createPortal(
          <div
            ref={dropdownRef}
            className="w-52 rounded-xl shadow-lg border overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200"
            style={{
              ...dropdownStyle,
              background: "var(--theme-bg-card)",
              borderColor: "var(--theme-border)",
            }}
          >
            {availableCategories.map((category) => {
              const Icon = CATEGORY_ICONS[category];
              return (
                <button
                  key={category}
                  type="button"
                  onClick={() => handleCategorySelect(category)}
                  className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-[13px] transition-colors hover:bg-[var(--theme-bg-subtle)] active:bg-[var(--theme-bg-subtle)]"
                  style={{ color: "var(--theme-text)" }}
                >
                  <div
                    className="flex items-center justify-center w-7 h-7 rounded-lg"
                    style={{ background: "var(--theme-primary-light)" }}
                  >
                    <Icon
                      size={14}
                      style={{ color: "var(--theme-text-secondary)" }}
                    />
                  </div>
                  <span className="flex-1 text-left font-medium">
                    {t(`fileUpload.categories.${category}`)}
                  </span>
                  {uploadLimits && (
                    <span
                      className="text-[11px] tabular-nums"
                      style={{ color: "var(--theme-text-secondary)" }}
                    >
                      {uploadLimits[category]}MB
                    </span>
                  )}
                </button>
              );
            })}
            {uploadLimits && (
              <div
                className="px-3.5 py-2 border-t text-xs"
                style={{
                  borderColor: "var(--theme-border)",
                  color: "var(--theme-text-secondary)",
                }}
              >
                {t("fileUpload.maxFilesSummary", {
                  maxFiles: uploadLimits.maxFiles,
                })}
              </div>
            )}
          </div>,
          document.body,
        )}
    </>
  );
});
