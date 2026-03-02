# Upload Progress & File Type Selection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add upload modal with file type selection, drag-drop support, and progress display in attachment cards.

**Architecture:** Create UploadModal component for type selection + drag-drop, modify upload API to support progress callbacks via XMLHttpRequest, extend AttachmentCard to show progress bar.

**Tech Stack:** React, TypeScript, XMLHttpRequest (for progress), i18n

---

## Task 1: Add Progress Support to Upload API

**Files:**
- Modify: `frontend/src/services/api/upload.ts`

**Step 1: Add progress callback type and modify uploadFile**

```typescript
// Add at the top of upload.ts
export interface UploadOptions {
  folder?: string;
  onProgress?: (progress: number, loaded: number, total: number) => void;
}

// Replace the uploadFile method with:
async uploadFile(
  file: File,
  options?: UploadOptions,
): Promise<UploadResult> {
  const folder = options?.folder || "uploads";
  const onProgress = options?.onProgress;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    const token = getAccessToken();
    xhr.open("POST", `${API_BASE}/api/upload/file?folder=${encodeURIComponent(folder)}`);

    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }

    xhr.withCredentials = true;

    // Track upload progress
    if (onProgress) {
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
          const progress = Math.round((event.loaded / event.total) * 100);
          onProgress(progress, event.loaded, event.total);
        }
      });
    }

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error("Invalid response format"));
        }
      } else {
        try {
          const errorData = JSON.parse(xhr.responseText);
          reject(new Error(errorData.detail || `Upload failed: ${xhr.statusText}`));
        } catch {
          reject(new Error(`Upload failed: ${xhr.statusText}`));
        }
      }
    });

    xhr.addEventListener("error", () => {
      reject(new Error("Network error during upload"));
    });

    xhr.addEventListener("abort", () => {
      reject(new Error("Upload cancelled"));
    });

    xhr.send(formData);
  });
},
```

**Step 2: Verify the changes compile**

Run: `cd /home/yangyang/LambChat/frontend && npm run build 2>&1 | head -50`
Expected: No TypeScript errors

**Step 3: Commit**

```bash
git add frontend/src/services/api/upload.ts
git commit -m "feat(api): add progress callback support to uploadFile"
```

---

## Task 2: Add Upload State Type and i18n Keys

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/en.json`

**Step 1: Add UploadState type to types/index.ts**

Add after `MessageAttachment` interface:

```typescript
// Upload state for tracking progress
export interface UploadState {
  id: string;
  file: File;
  progress: number;
  loaded: number;
  total: number;
  status: "pending" | "uploading" | "completed" | "error";
  attachment?: MessageAttachment;
  error?: string;
}
```

**Step 2: Add i18n keys to zh.json**

Add inside `fileUpload` object (after `"uploading"`):

```json
"selectType": "选择文件类型",
"selectFile": "选择文件",
"dragDropHint": "拖放文件到此处",
"dragDropOr": "或点击下方按钮选择",
"uploadComplete": "上传完成",
"uploadError": "上传失败"
```

**Step 3: Add i18n keys to en.json**

Add inside `fileUpload` object (after `"uploading"`):

```json
"selectType": "Select file type",
"selectFile": "Select file",
"dragDropHint": "Drag and drop files here",
"dragDropOr": "or click button below to select",
"uploadComplete": "Upload complete",
"uploadError": "Upload failed"
```

**Step 4: Verify changes**

Run: `cd /home/yangyang/LambChat/frontend && npm run build 2>&1 | head -50`
Expected: No errors

**Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/i18n/locales/zh.json frontend/src/i18n/locales/en.json
git commit -m "feat(types,i18n): add UploadState type and upload modal i18n keys"
```

---

## Task 3: Create UploadModal Component

**Files:**
- Create: `frontend/src/components/chat/UploadModal.tsx`

**Step 1: Create UploadModal.tsx**

```tsx
import { useState, useRef, useCallback, memo, useEffect } from "react";
import { X, Upload, Image, Video, Music, FileText, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { useAuth } from "../../hooks/useAuth";
import { uploadApi } from "../../services/api";
import type { MessageAttachment, FileCategory, UploadState } from "../../types";

const CATEGORY_ACCEPT_MAP: Record<FileCategory, string> = {
  image: "image/*",
  video: "video/*",
  audio: "audio/*",
  document: ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv",
};

const CATEGORY_PERMISSIONS: Record<FileCategory, string> = {
  image: "file_upload_image",
  video: "file_upload_video",
  audio: "file_upload_audio",
  document: "file_upload_document",
};

const CATEGORY_ICONS: Record<FileCategory, React.ElementType> = {
  image: Image,
  video: Video,
  audio: Music,
  document: FileText,
};

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (attachments: MessageAttachment[]) => void;
}

function getFileCategory(file: File): FileCategory {
  const type = file.type.toLowerCase();
  if (type.startsWith("image/")) return "image";
  if (type.startsWith("video/")) return "video";
  if (type.startsWith("audio/")) return "audio";
  return "document";
}

export const UploadModal = memo(function UploadModal({
  isOpen,
  onClose,
  onUpload,
}: UploadModalProps) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedType, setSelectedType] = useState<FileCategory>("image");
  const [showTypeDropdown, setShowTypeDropdown] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploads, setUploads] = useState<UploadState[]>([]);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowTypeDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Prevent body scroll when open
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

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;

      const fileArray = Array.from(files);
      const newUploads: UploadState[] = fileArray.map((file) => ({
        id: crypto.randomUUID(),
        file,
        progress: 0,
        loaded: 0,
        total: file.size,
        status: "pending" as const,
      }));

      setUploads((prev) => [...prev, ...newUploads]);

      // Upload files sequentially
      const completedAttachments: MessageAttachment[] = [];

      for (const upload of newUploads) {
        const category = getFileCategory(upload.file);
        const permKey = CATEGORY_PERMISSIONS[category];

        if (!hasPermission({ file_upload_image: permKey } as any)) {
          setUploads((prev) =>
            prev.map((u) =>
              u.id === upload.id
                ? { ...u, status: "error" as const, error: t("fileUpload.noPermission", { type: t(`fileUpload.categories.${category}`) }) }
                : u,
            ),
          );
          continue;
        }

        // Update status to uploading
        setUploads((prev) =>
          prev.map((u) => (u.id === upload.id ? { ...u, status: "uploading" as const } : u)),
        );

        try {
          const result = await uploadApi.uploadFile(upload.file, {
            onProgress: (progress, loaded, total) => {
              setUploads((prev) =>
                prev.map((u) =>
                  u.id === upload.id ? { ...u, progress, loaded, total } : u,
                ),
              );
            },
          });

          const attachment: MessageAttachment = {
            id: crypto.randomUUID(),
            key: result.key,
            name: result.name || upload.file.name,
            type: result.type as FileCategory,
            mimeType: result.mimeType,
            size: result.size,
            url: result.url,
          };

          setUploads((prev) =>
            prev.map((u) =>
              u.id === upload.id
                ? { ...u, status: "completed" as const, progress: 100, attachment }
                : u,
            ),
          );

          completedAttachments.push(attachment);
        } catch (error) {
          setUploads((prev) =>
            prev.map((u) =>
              u.id === upload.id
                ? {
                    ...u,
                    status: "error" as const,
                    error: error instanceof Error ? error.message : t("fileUpload.uploadError"),
                  }
                : u,
            ),
          );
        }
      }

      // Callback with completed attachments
      if (completedAttachments.length > 0) {
        onUpload(completedAttachments);
      }
    },
    [hasPermission, onUpload, t],
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
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  const handleSelectFile = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files);
    e.target.value = "";
  };

  const removeUpload = (id: string) => {
    setUploads((prev) => prev.filter((u) => u.id !== id));
  };

  const handleClose = () => {
    // Only allow close if no uploads in progress
    const hasUploading = uploads.some((u) => u.status === "uploading");
    if (!hasUploading) {
      setUploads([]);
      onClose();
    }
  };

  if (!isOpen) return null;

  const SelectedIcon = CATEGORY_ICONS[selectedType];
  const hasUploading = uploads.some((u) => u.status === "uploading");
  const allCompleted = uploads.length > 0 && uploads.every((u) => u.status === "completed");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={hasUploading ? undefined : handleClose}
      />

      {/* Modal */}
      <div className="relative z-10 w-full max-w-md mx-4 bg-white dark:bg-stone-800 rounded-xl shadow-xl border border-gray-200 dark:border-stone-700 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-stone-700">
          <h3 className="text-base font-semibold text-gray-900 dark:text-stone-100">
            {t("fileUpload.title")}
          </h3>
          <button
            type="button"
            onClick={handleClose}
            disabled={hasUploading}
            className={clsx(
              "p-1.5 rounded-full transition-colors",
              hasUploading
                ? "text-gray-300 dark:text-stone-600 cursor-not-allowed"
                : "text-gray-400 hover:text-gray-600 dark:text-stone-500 dark:hover:text-stone-300 hover:bg-gray-100 dark:hover:bg-stone-700",
            )}
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-4">
          {/* Drop zone */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={clsx(
              "relative flex flex-col items-center justify-center py-8 px-4 rounded-xl border-2 border-dashed transition-all cursor-pointer",
              isDragging
                ? "border-purple-400 bg-purple-50 dark:bg-purple-900/20"
                : "border-gray-200 dark:border-stone-600 hover:border-purple-300 dark:hover:border-purple-500",
            )}
            onClick={handleSelectFile}
          >
            <Upload
              size={32}
              className={clsx(
                "mb-3 transition-colors",
                isDragging
                  ? "text-purple-500"
                  : "text-gray-400 dark:text-stone-500",
              )}
            />
            <p className="text-sm text-gray-600 dark:text-stone-300 text-center">
              {t("fileUpload.dragDropHint")}
            </p>
            <p className="text-xs text-gray-400 dark:text-stone-500 mt-1">
              {t("fileUpload.dragDropOr")}
            </p>
          </div>

          {/* Type selector */}
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-600 dark:text-stone-300">
              {t("fileUpload.selectType")}:
            </span>
            <div className="relative" ref={dropdownRef}>
              <button
                type="button"
                onClick={() => setShowTypeDropdown(!showTypeDropdown)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-stone-600 bg-white dark:bg-stone-700 text-sm text-gray-700 dark:text-stone-200 hover:bg-gray-50 dark:hover:bg-stone-600 transition-colors"
              >
                <SelectedIcon size={16} />
                <span>{t(`fileUpload.categories.${selectedType}`)}</span>
                <ChevronDown size={14} />
              </button>

              {showTypeDropdown && (
                <div className="absolute top-full left-0 mt-1 z-20 min-w-[140px] rounded-lg bg-white dark:bg-stone-700 shadow-lg border border-gray-200 dark:border-stone-600 overflow-hidden">
                  {(Object.keys(CATEGORY_ICONS) as FileCategory[]).map((cat) => {
                    const Icon = CATEGORY_ICONS[cat];
                    return (
                      <button
                        key={cat}
                        type="button"
                        onClick={() => {
                          setSelectedType(cat);
                          setShowTypeDropdown(false);
                        }}
                        className={clsx(
                          "w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors",
                          selectedType === cat
                            ? "bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-300"
                            : "text-gray-700 dark:text-stone-200 hover:bg-gray-50 dark:hover:bg-stone-600",
                        )}
                      >
                        <Icon size={16} />
                        {t(`fileUpload.categories.${cat}`)}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={CATEGORY_ACCEPT_MAP[selectedType]}
            onChange={handleFileChange}
            className="hidden"
          />

          {/* Upload list */}
          {uploads.length > 0 && (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {uploads.map((upload) => (
                <div
                  key={upload.id}
                  className="flex items-center gap-3 p-2 rounded-lg bg-gray-50 dark:bg-stone-700/50"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-700 dark:text-stone-200 truncate">
                      {upload.file.name}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      {upload.status === "uploading" && (
                        <>
                          <div className="flex-1 h-1.5 bg-gray-200 dark:bg-stone-600 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-purple-500 rounded-full transition-all duration-300"
                              style={{ width: `${upload.progress}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-500 dark:text-stone-400">
                            {upload.progress}%
                          </span>
                        </>
                      )}
                      {upload.status === "completed" && (
                        <span className="text-xs text-green-500">{t("fileUpload.uploadComplete")}</span>
                      )}
                      {upload.status === "error" && (
                        <span className="text-xs text-red-500">{upload.error || t("fileUpload.uploadError")}</span>
                      )}
                    </div>
                  </div>
                  {upload.status !== "uploading" && (
                    <button
                      type="button"
                      onClick={() => removeUpload(upload.id)}
                      className="p-1 rounded-full text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 bg-gray-50 dark:bg-stone-900/50 border-t border-gray-100 dark:border-stone-700">
          <button
            type="button"
            onClick={handleClose}
            disabled={hasUploading}
            className={clsx(
              "px-4 py-2 text-sm font-medium rounded-lg transition-colors",
              hasUploading
                ? "text-gray-400 dark:text-stone-600 cursor-not-allowed"
                : "text-gray-700 dark:text-stone-300 bg-white dark:bg-stone-800 border border-gray-200 dark:border-stone-600 hover:bg-gray-50 dark:hover:bg-stone-700",
            )}
          >
            {allCompleted ? t("common.close") : t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={handleSelectFile}
            disabled={hasUploading}
            className={clsx(
              "px-4 py-2 text-sm font-medium rounded-lg transition-colors",
              hasUploading
                ? "bg-gray-300 dark:bg-stone-600 text-gray-500 dark:text-stone-400 cursor-not-allowed"
                : "bg-purple-500 hover:bg-purple-600 text-white",
            )}
          >
            {t("fileUpload.selectFile")}
          </button>
        </div>
      </div>
    </div>
  );
});
```

**Step 2: Verify component compiles**

Run: `cd /home/yangyang/LambChat/frontend && npm run build 2>&1 | head -50`
Expected: No TypeScript errors

**Step 3: Commit**

```bash
git add frontend/src/components/chat/UploadModal.tsx
git commit -m "feat(chat): add UploadModal component with type selection and progress"
```

---

## Task 4: Modify FileUploadButton to Open Modal

**Files:**
- Modify: `frontend/src/components/chat/FileUploadButton.tsx`

**Step 1: Simplify FileUploadButton to use UploadModal**

Replace the entire FileUploadButton.tsx content with:

```tsx
import { useState, memo } from "react";
import { Paperclip, Upload } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import type { MessageAttachment, Permission } from "../../types";
import { UploadModal } from "./UploadModal";

interface FileUploadButtonProps {
  attachments?: MessageAttachment[];
  onAttachmentsChange?: (attachments: MessageAttachment[]) => void;
}

// Permission mapping
const CATEGORY_PERMISSIONS: Record<string, Permission> = {
  image: Permission.FILE_UPLOAD_IMAGE,
  video: Permission.FILE_UPLOAD_VIDEO,
  audio: Permission.FILE_UPLOAD_AUDIO,
  document: Permission.FILE_UPLOAD_DOCUMENT,
};

export const FileUploadButton = memo(function FileUploadButton({
  attachments: externalAttachments = [],
  onAttachmentsChange,
}: FileUploadButtonProps) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Check if user has any upload permission
  const canUpload = Object.values(CATEGORY_PERMISSIONS).some((perm) =>
    hasPermission(perm),
  );

  const handleUpload = (newAttachments: MessageAttachment[]) => {
    const updated = [...externalAttachments, ...newAttachments];
    onAttachmentsChange?.(updated);
  };

  if (!canUpload) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setIsModalOpen(true)}
        className="flex items-center justify-center rounded-full p-2 border border-gray-200 dark:border-stone-700 bg-transparent hover:bg-gray-100 dark:hover:bg-stone-700 text-stone-500 dark:text-stone-300 transition-all duration-300"
        title={t("fileUpload.title")}
      >
        <Paperclip size={18} />
      </button>

      <UploadModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onUpload={handleUpload}
      />
    </>
  );
});
```

**Step 2: Verify changes compile**

Run: `cd /home/yangyang/LambChat/frontend && npm run build 2>&1 | head -50`
Expected: No TypeScript errors

**Step 3: Commit**

```bash
git add frontend/src/components/chat/FileUploadButton.tsx
git commit -m "refactor(chat): simplify FileUploadButton to use UploadModal"
```

---

## Task 5: Add Progress Support to AttachmentCard

**Files:**
- Modify: `frontend/src/components/common/AttachmentCard.tsx`

**Step 1: Add progress props and UI to AttachmentCard**

Update the interface and add progress bar rendering:

```tsx
// Update AttachmentCardProps interface (around line 34-44)
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
  /** 上传进度 0-100 */
  uploadProgress?: number;
  /** 是否正在上传 */
  isUploading?: boolean;
}
```

**Step 2: Update component to show progress**

In the compact mode section (around line 72-136), add progress bar after file info:

```tsx
// Add after the file info div and before the remove button in compact mode
{/* Progress bar */}
{isUploading && uploadProgress !== undefined && (
  <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-200 dark:bg-stone-600 rounded-b-xl overflow-hidden">
    <div
      className="h-full bg-purple-500 transition-all duration-300"
      style={{ width: `${uploadProgress}%` }}
    />
  </div>
)}
```

Also add `uploadProgress, isUploading` to the component props destructuring.

**Step 3: Full modified component**

See the full implementation with progress support in the component.

**Step 4: Verify changes compile**

Run: `cd /home/yangyang/LambChat/frontend && npm run build 2>&1 | head -50`
Expected: No TypeScript errors

**Step 5: Commit**

```bash
git add frontend/src/components/common/AttachmentCard.tsx
git commit -m "feat(ui): add upload progress display to AttachmentCard"
```

---

## Task 6: Final Integration Test

**Step 1: Build and verify**

Run: `cd /home/yangyang/LambChat/frontend && npm run build`
Expected: Build succeeds with no errors

**Step 2: Manual test checklist**

- [ ] Click upload button → modal opens
- [ ] Modal shows drop zone, type selector, and select button
- [ ] Drag file to drop zone → upload starts
- [ ] Progress bar shows during upload
- [ ] Click select button → file dialog opens with correct accept filter
- [ ] Select multiple files → all upload with progress
- [ ] After upload → attachments appear in ChatInput
- [ ] Close modal → modal closes (only when no uploads in progress)
- [ ] Remove attachment → attachment removed from list

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat(upload): complete upload modal with progress support"
```

---

## Summary

This plan implements:
1. **Upload API with progress** - XMLHttpRequest-based upload with progress callback
2. **UploadModal component** - File type selector + drag-drop + progress display
3. **FileUploadButton refactor** - Opens modal instead of direct file selection
4. **AttachmentCard progress** - Visual progress bar during upload
5. **i18n support** - Chinese and English translations
