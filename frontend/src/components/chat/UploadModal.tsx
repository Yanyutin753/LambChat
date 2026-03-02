import { useRef, useState, useCallback, useEffect, memo } from "react";
import {
  X,
  Upload,
  FileText,
  Image,
  Video,
  Music,
  File,
  ChevronDown,
  Loader2,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { useAuth } from "../../hooks/useAuth";
import { uploadApi, type UploadOptions } from "../../services/api/upload";
import {
  MessageAttachment,
  FileCategory,
  Permission,
  UploadState,
} from "../../types";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (attachments: MessageAttachment[]) => void;
}

// Accept filters for each file category
const CATEGORY_ACCEPT_MAP: Record<FileCategory, string> = {
  image: "image/*",
  video: "video/*",
  audio: "audio/*",
  document: ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv",
};

// Permission mapping for each category
const CATEGORY_PERMISSIONS: Record<FileCategory, Permission> = {
  image: Permission.FILE_UPLOAD_IMAGE,
  video: Permission.FILE_UPLOAD_VIDEO,
  audio: Permission.FILE_UPLOAD_AUDIO,
  document: Permission.FILE_UPLOAD_DOCUMENT,
};

// Icon mapping for each category
const CATEGORY_ICONS: Record<FileCategory, typeof Image> = {
  image: Image,
  video: Video,
  audio: Music,
  document: FileText,
};

// Helper to detect file category from MIME type
function detectFileCategory(file: File): FileCategory {
  const type = file.type.toLowerCase();
  if (type.startsWith("image/")) return "image";
  if (type.startsWith("video/")) return "video";
  if (type.startsWith("audio/")) return "audio";
  return "document";
}

// Helper to format file size
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const UploadModal = memo(function UploadModal({
  isOpen,
  onClose,
  onUpload,
}: UploadModalProps) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // State
  const [selectedCategory, setSelectedCategory] =
    useState<FileCategory>("image");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploads, setUploads] = useState<UploadState[]>([]);

  // Get available categories based on permissions
  const availableCategories = Object.keys(CATEGORY_PERMISSIONS).filter((cat) =>
    hasPermission(CATEGORY_PERMISSIONS[cat as FileCategory]),
  ) as FileCategory[];

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setUploads([]);
      // Set first available category as default
      if (availableCategories.length > 0) {
        setSelectedCategory(availableCategories[0]);
      }
    }
  }, [isOpen, availableCategories]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Upload a single file
  const uploadFile = useCallback(
    async (file: File, category?: FileCategory) => {
      const fileCategory = category || detectFileCategory(file);

      // Check permission
      if (!hasPermission(CATEGORY_PERMISSIONS[fileCategory])) {
        setUploads((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            file,
            progress: 0,
            loaded: 0,
            total: file.size,
            status: "error",
            error: t("fileUpload.noPermission", {
              type: t(`fileUpload.categories.${fileCategory}`),
            }),
          },
        ]);
        return;
      }

      const uploadId = crypto.randomUUID();

      // Add pending upload
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
        const options: UploadOptions = {
          folder: fileCategory,
          onProgress: (progress, loaded, total) => {
            setUploads((prev) =>
              prev.map((u) =>
                u.id === uploadId ? { ...u, progress, loaded, total } : u,
              ),
            );
          },
        };

        const result = await uploadApi.uploadFile(file, options);

        // Update with completed status
        setUploads((prev) =>
          prev.map((u) =>
            u.id === uploadId
              ? {
                  ...u,
                  status: "completed",
                  progress: 100,
                  attachment: {
                    id: crypto.randomUUID(),
                    key: result.key,
                    name: result.name || file.name,
                    type: result.type as FileCategory,
                    mimeType: result.mimeType,
                    size: result.size,
                    url: result.url,
                  },
                }
              : u,
          ),
        );
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : t("fileUpload.uploadError");
        setUploads((prev) =>
          prev.map((u) =>
            u.id === uploadId
              ? { ...u, status: "error", error: errorMessage }
              : u,
          ),
        );
      }
    },
    [hasPermission, t],
  );

  // Handle file selection
  const handleFileSelect = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;

      Array.from(files).forEach((file) => {
        uploadFile(file, selectedCategory);
      });
    },
    [selectedCategory, uploadFile],
  );

  // Handle drag events
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

  // Get completed attachments
  const completedAttachments = uploads
    .filter((u) => u.status === "completed" && u.attachment)
    .map((u) => u.attachment!);

  // Check if any uploads are in progress
  const isUploading = uploads.some((u) => u.status === "uploading");

  // Handle confirm - pass completed attachments to parent
  const handleConfirm = useCallback(() => {
    if (completedAttachments.length > 0) {
      onUpload(completedAttachments);
    }
    onClose();
  }, [completedAttachments, onUpload, onClose]);

  // Get status icon
  const getStatusIcon = (status: UploadState["status"]) => {
    switch (status) {
      case "uploading":
        return <Loader2 size={14} className="animate-spin text-blue-500" />;
      case "completed":
        return <CheckCircle size={14} className="text-green-500" />;
      case "error":
        return <AlertCircle size={14} className="text-red-500" />;
      default:
        return null;
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative z-10 w-full max-w-lg mx-4 bg-white dark:bg-stone-800 rounded-xl shadow-xl border border-gray-200 dark:border-stone-700 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-stone-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-stone-100">
            {t("fileUpload.title")}
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-stone-700 text-gray-500 dark:text-stone-400 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4">
          {/* Type selector dropdown */}
          <div className="relative">
            <label className="block text-sm font-medium text-gray-700 dark:text-stone-300 mb-1.5">
              {t("fileUpload.selectType")}
            </label>
            <button
              type="button"
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className="w-full flex items-center justify-between px-3 py-2.5 bg-white dark:bg-stone-900 border border-gray-200 dark:border-stone-600 rounded-lg text-left hover:border-gray-300 dark:hover:border-stone-500 transition-colors"
            >
              <div className="flex items-center gap-2">
                {(() => {
                  const Icon = CATEGORY_ICONS[selectedCategory];
                  return (
                    <Icon
                      size={18}
                      className="text-gray-500 dark:text-stone-400"
                    />
                  );
                })()}
                <span className="text-gray-900 dark:text-stone-100">
                  {t(`fileUpload.categories.${selectedCategory}`)}
                </span>
              </div>
              <ChevronDown
                size={18}
                className={clsx(
                  "text-gray-400 transition-transform",
                  isDropdownOpen && "rotate-180",
                )}
              />
            </button>

            {/* Dropdown menu */}
            {isDropdownOpen && (
              <div className="absolute z-20 w-full mt-1 bg-white dark:bg-stone-900 border border-gray-200 dark:border-stone-600 rounded-lg shadow-lg overflow-hidden">
                {availableCategories.map((category) => {
                  const Icon = CATEGORY_ICONS[category];
                  return (
                    <button
                      key={category}
                      type="button"
                      onClick={() => {
                        setSelectedCategory(category);
                        setIsDropdownOpen(false);
                      }}
                      className={clsx(
                        "w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-stone-800 transition-colors",
                        selectedCategory === category &&
                          "bg-gray-50 dark:bg-stone-800",
                      )}
                    >
                      <Icon
                        size={18}
                        className="text-gray-500 dark:text-stone-400"
                      />
                      <span className="text-gray-900 dark:text-stone-100">
                        {t(`fileUpload.categories.${category}`)}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            accept={CATEGORY_ACCEPT_MAP[selectedCategory]}
            onChange={(e) => {
              handleFileSelect(e.target.files);
              e.target.value = "";
            }}
          />

          {/* Drop zone */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={clsx(
              "relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all",
              isDragging
                ? "border-purple-500 bg-purple-50 dark:border-purple-400 dark:bg-purple-900/20"
                : "border-gray-200 dark:border-stone-600 hover:border-gray-300 dark:hover:border-stone-500 bg-gray-50 dark:bg-stone-900/50",
            )}
          >
            <div className="flex flex-col items-center gap-3">
              <div
                className={clsx(
                  "w-12 h-12 rounded-full flex items-center justify-center",
                  isDragging
                    ? "bg-purple-100 dark:bg-purple-900/40"
                    : "bg-gray-100 dark:bg-stone-700",
                )}
              >
                <Upload
                  size={24}
                  className={clsx(
                    isDragging
                      ? "text-purple-500 dark:text-purple-400"
                      : "text-gray-400 dark:text-stone-500",
                  )}
                />
              </div>
              <div>
                <p className="text-sm text-gray-600 dark:text-stone-300">
                  {t("fileUpload.dragDropHint")}
                </p>
                <p className="text-xs text-gray-400 dark:text-stone-500 mt-1">
                  {t("fileUpload.dragDropOr")}
                </p>
              </div>
            </div>
          </div>

          {/* Upload list */}
          {uploads.length > 0 && (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {uploads.map((upload) => {
                const Icon =
                  CATEGORY_ICONS[detectFileCategory(upload.file)] || File;
                return (
                  <div
                    key={upload.id}
                    className="flex items-center gap-3 p-2.5 bg-gray-50 dark:bg-stone-900/50 rounded-lg"
                  >
                    {/* File icon */}
                    <div className="w-8 h-8 rounded bg-gray-200 dark:bg-stone-700 flex items-center justify-center flex-shrink-0">
                      <Icon
                        size={16}
                        className="text-gray-500 dark:text-stone-400"
                      />
                    </div>

                    {/* File info and progress */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-medium text-gray-900 dark:text-stone-100 truncate">
                          {upload.file.name}
                        </p>
                        {getStatusIcon(upload.status)}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        {/* Progress bar */}
                        {upload.status === "uploading" && (
                          <div className="flex-1 h-1.5 bg-gray-200 dark:bg-stone-700 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-blue-500 rounded-full transition-all duration-300"
                              style={{ width: `${upload.progress}%` }}
                            />
                          </div>
                        )}
                        <span className="text-xs text-gray-500 dark:text-stone-400 whitespace-nowrap">
                          {upload.status === "uploading"
                            ? `${upload.progress}%`
                            : upload.status === "completed"
                              ? t("fileUpload.uploadComplete")
                              : upload.status === "error"
                                ? upload.error
                                : formatFileSize(upload.file.size)}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 bg-gray-50 dark:bg-stone-900/50 border-t border-gray-100 dark:border-stone-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-stone-300 bg-white dark:bg-stone-800 border border-gray-200 dark:border-stone-600 rounded-lg hover:bg-gray-50 dark:hover:bg-stone-700 transition-colors"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={handleConfirm}
            disabled={completedAttachments.length === 0 || isUploading}
            className={clsx(
              "px-4 py-2 text-sm font-medium rounded-lg transition-colors",
              completedAttachments.length > 0 && !isUploading
                ? "bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 text-white"
                : "bg-gray-200 dark:bg-stone-700 text-gray-400 dark:text-stone-500 cursor-not-allowed",
            )}
          >
            {t("common.confirm")}
            {completedAttachments.length > 0 && (
              <span className="ml-1.5">({completedAttachments.length})</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
});
