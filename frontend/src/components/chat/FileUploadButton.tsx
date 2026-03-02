import { useState, useRef, useCallback, memo, useEffect } from "react";
import { Paperclip, Image, Video, Music, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { uploadApi } from "../../services/api";
import type { MessageAttachment, FileCategory, UploadState } from "../../types";
import { Permission } from "../../types";

interface FileUploadButtonProps {
  attachments?: MessageAttachment[];
  onAttachmentsChange?: (attachments: MessageAttachment[]) => void;
  onUploadStateChange?: (uploads: UploadState[]) => void;
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

function getFileCategory(file: File): FileCategory {
  const type = file.type.toLowerCase();
  if (type.startsWith("image/")) return "image";
  if (type.startsWith("video/")) return "video";
  if (type.startsWith("audio/")) return "audio";
  return "document";
}

export const FileUploadButton = memo(function FileUploadButton({
  attachments: externalAttachments = [],
  onAttachmentsChange,
  onUploadStateChange,
}: FileUploadButtonProps) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<FileCategory | null>(
    null,
  );
  const [uploads, setUploads] = useState<UploadState[]>([]);

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

  // Sync upload state to parent
  useEffect(() => {
    onUploadStateChange?.(uploads);
  }, [uploads, onUploadStateChange]);

  // Handle file selection
  const handleFiles = useCallback(
    async (files: FileList | null, category?: FileCategory) => {
      if (!files || files.length === 0) return;

      const fileArray = Array.from(files);

      for (const file of fileArray) {
        const fileCategory = category || getFileCategory(file);
        const perm = CATEGORY_PERMISSIONS[fileCategory];

        if (!hasPermission(perm)) {
          console.warn(`No permission to upload ${fileCategory} files`);
          continue;
        }

        const uploadId = crypto.randomUUID();

        // Add to uploads with pending status
        setUploads((prev) => [
          ...prev,
          {
            id: uploadId,
            file,
            progress: 0,
            loaded: 0,
            total: file.size,
            status: "uploading",
          },
        ]);

        try {
          const result = await uploadApi.uploadFile(file, {
            onProgress: (progress, loaded, total) => {
              setUploads((prev) =>
                prev.map((u) =>
                  u.id === uploadId ? { ...u, progress, loaded, total } : u,
                ),
              );
            },
          });

          const attachment: MessageAttachment = {
            id: crypto.randomUUID(),
            key: result.key,
            name: result.name || file.name,
            type: result.type as FileCategory,
            mimeType: result.mimeType,
            size: result.size,
            url: result.url,
          };

          // Update upload status to completed
          setUploads((prev) =>
            prev.map((u) =>
              u.id === uploadId ? { ...u, status: "completed", attachment } : u,
            ),
          );

          // Add to external attachments
          onAttachmentsChange?.([...externalAttachments, attachment]);
        } catch (error) {
          setUploads((prev) =>
            prev.map((u) =>
              u.id === uploadId
                ? {
                    ...u,
                    status: "error",
                    error:
                      error instanceof Error ? error.message : "Upload failed",
                  }
                : u,
            ),
          );
        }
      }
    },
    [externalAttachments, hasPermission, onAttachmentsChange],
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
        className="flex items-center justify-center rounded-full p-2 border border-gray-200 dark:border-stone-700 bg-transparent hover:bg-gray-100 dark:hover:bg-stone-700 text-stone-500 dark:text-stone-300 transition-all duration-300"
        title={t("fileUpload.title")}
      >
        <Paperclip size={18} />
      </button>

      {/* Dropdown menu */}
      {showDropdown && (
        <div className="absolute bottom-full left-0 mb-2 z-50 min-w-[140px] rounded-xl bg-white dark:bg-stone-800 shadow-lg border border-gray-200 dark:border-stone-700 overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200">
          <div className="py-1">
            {availableCategories.map((category) => {
              const Icon = CATEGORY_ICONS[category];
              return (
                <button
                  key={category}
                  type="button"
                  onClick={() => handleCategorySelect(category)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-stone-200 hover:bg-gray-50 dark:hover:bg-stone-700 transition-colors"
                >
                  <Icon size={16} />
                  {t(`fileUpload.categories.${category}`)}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Upload progress indicators - shown near button */}
      {uploads.filter((u) => u.status === "uploading").length > 0 && (
        <div className="absolute bottom-full left-0 mb-2 z-40 pointer-events-none">
          <div className="flex items-center gap-1 px-2 py-1 bg-purple-500 text-white text-xs rounded-full animate-pulse">
            <span>
              {t("fileUpload.uploading")}{" "}
              {uploads.filter((u) => u.status === "uploading").length}
            </span>
          </div>
        </div>
      )}
    </div>
  );
});
