# File Upload Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement file upload feature with type-based permission control, dynamic proxy URLs, and frontend attachment preview.

**Architecture:**
- Backend: Extend FastAPI upload routes with permission-based file type validation and dynamic proxy endpoint
- Frontend: Add FileUploadButton component, AttachmentPreview for pending files, FileMessage for sent messages
- Storage: Use existing S3 backend with user isolation and presigned URL generation

**Tech Stack:** FastAPI, Pydantic, React, TypeScript, TailwindCSS, S3

---

## Phase 1: Backend - Permission System Extension

### Task 1: Add File Upload Permissions to Backend Types

**Files:**
- Modify: `src/kernel/types.py:56-57`

**Step 1: Add new permission enum values**

```python
# File - add after FILE_UPLOAD
FILE_UPLOAD_IMAGE = "file:upload:image"
FILE_UPLOAD_VIDEO = "file:upload:video"
FILE_UPLOAD_AUDIO = "file:upload:audio"
FILE_UPLOAD_DOCUMENT = "file:upload:document"
```

**Step 2: Run to verify**
Expected: No errors when importing

**Step 3: Commit**
```bash
git add src/kernel/types.py
git commit -m "feat(permissions): add file upload type permissions"
```

---

### Task 2: Add Permission Metadata

**Files:**
- Modify: `src/kernel/schemas/permission.py:130-135`
- Modify: `src/kernel/schemas/permission.py:194-199`

**Step 1: Add permission metadata entries**

```python
# Add to PERMISSION_METADATA dict
Permission.FILE_UPLOAD_IMAGE.value: {
    "label": "上传图片",
    "description": "允许上传图片文件（jpg, png, gif 等）",
},
Permission.FILE_UPLOAD_VIDEO.value: {
    "label": "上传视频",
    "description": "允许上传视频文件（mp4, webm 等）",
},
Permission.FILE_UPLOAD_AUDIO.value: {
    "label": "上传音频",
    "description": "允许上传音频文件（mp3, wav 等）",
},
Permission.FILE_UPLOAD_DOCUMENT.value: {
    "label": "上传文档",
    "description": "允许上传文档文件（pdf, word, excel 等）",
},
```

**Step 2: Add to permission groups config**

```python
{
    "name": "文件上传",
    "permissions": [
        Permission.FILE_UPLOAD.value,
        Permission.FILE_UPLOAD_IMAGE.value,
        Permission.FILE_UPLOAD_VIDEO.value,
        Permission.FILE_UPLOAD_AUDIO.value,
        Permission.FILE_UPLOAD_DOCUMENT.value,
    ],
},
```

**Step 3: Commit**
```bash
git add src/kernel/schemas/permission.py
git commit -m "feat(permissions): add file upload permission metadata"
```

---

## Phase 2: Backend - File Type Utilities

### Task 3: Create File Type Classification Utility

**Files:**
- Create: `src/api/routes/file_type.py`

**Step 1: Write file type classification**

```python
"""File type classification utilities"""

from enum import Enum
from typing import Optional


class FileCategory(str, Enum):
    """File category enum"""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


# File extension mappings
FILE_EXTENSIONS: dict[FileCategory, set[str]] = {
    FileCategory.IMAGE: {"jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "ico"},
    FileCategory.VIDEO: {"mp4", "webm", "mov", "avi", "mkv", "wmv", "flv"},
    FileCategory.AUDIO: {"mp3", "wav", "ogg", "aac", "flac", "m4a", "wma"},
    FileCategory.DOCUMENT: {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "rtf"},
}

# MIME type prefixes
MIME_TYPE_PREFIXES: dict[FileCategory, str] = {
    FileCategory.IMAGE: "image/",
    FileCategory.VIDEO: "video/",
    FileCategory.AUDIO: "audio/",
}


def get_file_category(filename: str, mime_type: Optional[str] = None) -> FileCategory:
    """
    Determine file category from filename and MIME type

    Args:
        filename: Original filename
        mime_type: Optional MIME type from upload

    Returns:
        FileCategory enum value
    """
    # Try MIME type first
    if mime_type:
        for category, prefix in MIME_TYPE_PREFIXES.items():
            if mime_type.startswith(prefix):
                return category
        # Handle specific MIME types
        if mime_type == "application/pdf":
            return FileCategory.DOCUMENT
        if mime_type.startswith("application/msword") or mime_type.startswith("application/vnd."):
            return FileCategory.DOCUMENT

    # Fall back to extension
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    for category, extensions in FILE_EXTENSIONS.items():
        if ext in extensions:
            return category

    return FileCategory.UNKNOWN


def get_permission_for_category(category: FileCategory) -> Optional[str]:
    """Get permission required for a file category"""
    mapping = {
        FileCategory.IMAGE: "file:upload:image",
        FileCategory.VIDEO: "file:upload:video",
        FileCategory.AUDIO: "file:upload:audio",
        FileCategory.DOCUMENT: "file:upload:document",
    }
    return mapping.get(category)
```

**Step 2: Run to verify**
Expected: No import errors

**Step 3: Commit**
```bash
git add src/api/routes/file_type.py
git commit -m "feat(upload): add file type classification utility"
```

---

## Phase 3: Backend - Dynamic Proxy Endpoint

### Task 4: Add Dynamic Proxy Endpoint

**Files:**
- Modify: `src/api/routes/upload.py:512` (end of file)

**Step 1: Add proxy endpoint**

```python
@router.get("/file/{key:path}")
async def get_file_proxy(
    key: str,
    current_user: TokenPayload = Depends(get_current_user_required),
) -> Response:
    """
    Dynamic proxy endpoint for file access

    Generates a short-lived presigned URL and redirects to it.
    This ensures the URL never expires from the user's perspective.

    Args:
        key: S3 object key
        current_user: Current authenticated user

    Returns:
        302 redirect to presigned URL
    """
    if not await get_s3_enabled():
        raise HTTPException(
            status_code=503,
            detail="File storage is not enabled.",
        )

    storage = await get_or_init_storage()

    # Verify file exists
    try:
        exists = await storage.file_exists(key)
        if not exists:
            raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        logger.warning(f"Failed to check file existence for {key}: {e}")
        # Continue anyway - let S3 handle the error

    # Generate short-lived presigned URL (5 minutes)
    try:
        if storage._config.public_bucket:
            url = await storage.get_file_url(key)
        else:
            url = await storage.get_presigned_url(key, 300)  # 5 minutes
    except Exception as e:
        logger.error(f"Failed to generate presigned URL for {key}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate file URL")

    # Redirect to presigned URL
    return Response(
        status_code=302,
        headers={"Location": url},
    )
```

**Step 2: Run to verify**
Expected: No import errors, endpoint registered

**Step 3: Commit**
```bash
git add src/api/routes/upload.py
git commit -m "feat(upload): add dynamic proxy endpoint for permanent URLs"
```

---

## Phase 4: Backend - Upload with Permission Check

### Task 5: Modify Upload Endpoint for Permission Check

**Files:**
- Modify: `src/api/routes/upload.py:133-185`

**Step 1: Update upload_file function**

```python
@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: TokenPayload = Depends(get_current_user_required),
) -> dict:
    """
    Upload a file to S3

    Requires: file:upload:{type} permission based on file type
    Files are stored in folders organized by user_id.

    Args:
        file: File to upload
        current_user: Current authenticated user

    Returns:
        Upload result with URL and metadata
    """
    if not await get_s3_enabled():
        raise HTTPException(
            status_code=503,
            detail="File storage is not enabled. Please configure S3 settings in System Settings.",
        )

    storage = await get_or_init_storage()

    # Read file content first for validation
    content = await file.read()

    # Determine file category
    category = get_file_category(file.filename or "", file.content_type)
    permission = get_permission_for_category(category)

    # Check permission
    from src.infra.auth.rbac import check_permission
    user_permissions = await get_user_permissions(current_user.sub)

    # Allow if has specific permission OR has general file:upload permission
    has_specific = permission and await check_permission(current_user.sub, permission)
    has_general = await check_permission(current_user.sub, Permission.FILE_UPLOAD.value)

    if not (has_specific or has_general):
        category_label = category.value if category != FileCategory.UNKNOWN else "未知"
        raise HTTPException(
            status_code=403,
            detail=f"No permission to upload {category_label} files",
        )

    # Validate file size based on category
    from src.infra.settings.service import get_settings_service
    settings_service = get_settings_service()

    size_limits = {
        FileCategory.IMAGE: await settings_service.get("FILE_UPLOAD_MAX_SIZE_IMAGE") or 10,
        FileCategory.VIDEO: await settings_service.get("FILE_UPLOAD_MAX_SIZE_VIDEO") or 100,
        FileCategory.AUDIO: await settings_service.get("FILE_UPLOAD_MAX_SIZE_AUDIO") or 50,
        FileCategory.DOCUMENT: await settings_service.get("FILE_UPLOAD_MAX_SIZE_DOCUMENT") or 50,
        FileCategory.UNKNOWN: 10,
    }
    max_size_mb = size_limits.get(category, 10)
    max_size_bytes = max_size_mb * 1024 * 1024

    if len(content) > max_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum of {max_size_mb}MB",
        )

    # Validate file extension
    ext = (file.filename or "").lower().split(".")[-1]
    allowed_exts = FILE_EXTENSIONS.get(category, set())
    if category != FileCategory.UNKNOWN and ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '.{ext}' is not allowed for {category.value} files",
        )

    # Reset file position after reading
    await file.seek(0)

    # Upload - use user_id as folder
    try:
        result = await storage.upload_file(
            file=file.file,
            folder=current_user.sub,
            filename=file.filename or "unknown",
            content_type=file.content_type,
            metadata={"uploaded_by": current_user.sub},
        )

        # Return proxy URL instead of direct S3 URL
        proxy_url = f"/api/upload/file/{result.key}"

        return {
            "key": result.key,
            "url": proxy_url,
            "name": file.filename,
            "type": category.value,
            "mimeType": file.content_type,
            "size": result.size,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
```

**Step 2: Add missing imports**

```python
from src.api.routes.file_type import get_file_category, get_permission_for_category, FileCategory
from src.infra.auth.rbac import check_permission
from src.infra.user.storage import get_user_permissions
```

**Step 3: Run to verify**
Expected: No import errors

**Step 4: Commit**
```bash
git add src/api/routes/upload.py
git commit -m "feat(upload): add permission-based file type validation"
```

---

## Phase 5: Backend - Upload Config Endpoint

### Task 6: Extend Config Endpoint

**Files:**
- Modify: `src/api/routes/upload.py:312-329`

**Step 1: Update get_storage_config**

```python
@router.get("/config")
async def get_storage_config() -> dict:
    """
    Get storage configuration status and file upload limits

    Returns:
        Storage configuration and upload limits
    """
    from src.infra.settings.service import get_settings_service

    s3_enabled = await get_s3_enabled()
    settings_service = get_settings_service()

    # Get upload limits from settings
    max_size_image = await settings_service.get("FILE_UPLOAD_MAX_SIZE_IMAGE") or 10
    max_size_video = await settings_service.get("FILE_UPLOAD_MAX_SIZE_VIDEO") or 100
    max_size_audio = await settings_service.get("FILE_UPLOAD_MAX_SIZE_AUDIO") or 50
    max_size_document = await settings_service.get("FILE_UPLOAD_MAX_SIZE_DOCUMENT") or 50
    max_files = await settings_service.get("FILE_UPLOAD_MAX_FILES") or 10

    return {
        "enabled": s3_enabled,
        "provider": settings.S3_PROVIDER if s3_enabled else None,
        "max_file_size": settings.S3_MAX_FILE_SIZE if s3_enabled and settings.S3_MAX_FILE_SIZE else None,
        "uploadLimits": {
            "image": max_size_image,
            "video": max_size_video,
            "audio": max_size_audio,
            "document": max_size_document,
            "maxFiles": max_files,
        },
    }
```

**Step 2: Commit**
```bash
git add src/api/routes/upload.py
git commit -m "feat(upload): extend config endpoint with upload limits"
```

---

## Phase 6: Frontend - Types

### Task 7: Add Frontend File Upload Types

**Files:**
- Modify: `frontend/src/types/index.ts:786` (end of file)

**Step 1: Add types**

```typescript
// ============================================
// File Upload Types
// ============================================

export type FileCategory = "image" | "video" | "audio" | "document";

export interface MessageAttachment {
  id: string;
  key: string;
  name: string;
  type: FileCategory;
  mimeType: string;
  size: number;
  url: string;
}

export interface UploadConfig {
  enabled: boolean;
  provider?: string;
  max_file_size?: number;
  uploadLimits: {
    image: number;
    video: number;
    audio: number;
    document: number;
    maxFiles: number;
  };
}

export interface UploadResult {
  key: string;
  url: string;
  name: string;
  type: FileCategory;
  mimeType: string;
  size: number;
}
```

**Step 2: Add to Permission enum**

```typescript
// File - add to Permission enum
FILE_UPLOAD_IMAGE = "file:upload:image",
FILE_UPLOAD_VIDEO = "file:upload:video",
FILE_UPLOAD_AUDIO = "file:upload:audio",
FILE_UPLOAD_DOCUMENT = "file:upload:document",
```

**Step 3: Commit**
```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add file upload types to frontend"
```

---

## Phase 7: Frontend - API Service

### Task 8: Add Upload API Methods

**Files:**
- Modify: `frontend/src/services/api.ts`

**Step 1: Add upload API methods**

```typescript
// Upload API
export const uploadApi = {
  async uploadFile(file: File): Promise<UploadResult> {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetchWithAuth("/api/upload/upload", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "Upload failed");
    }

    return response.json();
  },

  async getConfig(): Promise<UploadConfig> {
    const response = await fetchWithAuth("/api/upload/config");
    return response.json();
  },

  async getSignedUrl(key: string, expires = 3600): Promise<string> {
    const params = new URLSearchParams({ key, expires: String(expires) });
    const response = await fetchWithAuth(`/api/upload/signed-url/simple?${params}`);
    const data = await response.json();
    return data.url;
  },
};
```

**Step 2: Commit**
```bash
git add frontend/src/services/api.ts
git commit -m "feat(api): add upload API methods to frontend"
```

---

## Phase 8: Frontend - FileUploadButton Component

### Task 9: Create FileUploadButton Component

**Files:**
- Create: `frontend/src/components/chat/FileUploadButton.tsx`

**Step 1: Write component**

```typescript
import { useRef, useState, useCallback, memo } from "react";
import { Paperclip, X, Upload, FileText, Image, Video, Music } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { uploadApi } from "../../services/api";
import { AttachmentPreview } from "./AttachmentPreview";
import type { MessageAttachment, FileCategory, UploadResult } from "../../types";

interface FileUploadButtonProps {
  onAttachmentsChange?: (attachments: MessageAttachment[]) => void;
}

// Permission mapping
const CATEGORY_PERMISSIONS: Record<FileCategory, string> = {
  image: "file:upload:image",
  video: "file:upload:video",
  audio: "file:upload:audio",
  document: "file:upload:document",
};

// Icon mapping
const CATEGORY_ICONS: Record<FileCategory, typeof Image> = {
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
    hasPermission(perm as any)
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
          if (!hasPermission(requiredPerm as any)) {
            alert(t("fileUpload.noPermission", { type: t(`fileUpload.categories.${category}`) }));
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

        const updated = [...attachments, ...newAttachments];
        setAttachments(updated);
        onAttachmentsChange?.(updated);
      } catch (error) {
        console.error("Upload failed:", error);
        alert(t("fileUpload.uploadFailed"));
      } finally {
        setIsUploading(false);
      }
    },
    [attachments, hasPermission, isUploading, onAttachmentsChange, t]
  );

  const handleRemove = useCallback(
    (id: string) => {
      const updated = attachments.filter((a) => a.id !== id);
      setAttachments(updated);
      onAttachmentsChange?.(updated);
    },
    [attachments, onAttachmentsChange]
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
    [handleFileSelect]
  );

  if (!canUpload) return null;

  return (
    <div className="relative">
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
            ? "border-purple-300 bg-purple-50"
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
          className="absolute inset-0 rounded-full border-2 border-dashed border-purple-400 bg-purple-50/80 flex items-center justify-center"
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
```

**Step 2: Commit**
```bash
git add frontend/src/components/chat/FileUploadButton.tsx
git commit -m "feat(chat): add FileUploadButton component"
```

---

## Phase 9: Frontend - AttachmentPreview Component

### Task 10: Create AttachmentPreview Component

**Files:**
- Create: `frontend/src/components/chat/AttachmentPreview.tsx`

**Step 1: Write component**

```typescript
import { memo } from "react";
import { X, FileText, Image, Video, Music, File } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { MessageAttachment } from "../../types";

interface AttachmentPreviewProps {
  attachments: MessageAttachment[];
  onRemove: (id: string) => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const ICON_MAP = {
  image: Image,
  video: Video,
  audio: Music,
  document: FileText,
};

export const AttachmentPreview = memo(function AttachmentPreview({
  attachments,
  onRemove,
}: AttachmentPreviewProps) {
  const { t } = useTranslation();

  return (
    <div className="bg-white dark:bg-stone-800 rounded-lg shadow-lg border border-gray-200 dark:border-stone-700 p-2 space-y-2">
      {attachments.map((attachment) => {
        const Icon = ICON_MAP[attachment.type] || File;

        return (
          <div
            key={attachment.id}
            className="flex items-center gap-2 p-2 rounded-md bg-gray-50 dark:bg-stone-700/50"
          >
            {/* Preview or icon */}
            {attachment.type === "image" && attachment.mimeType.startsWith("image/") ? (
              <div className="w-10 h-10 rounded overflow-hidden bg-gray-200 dark:bg-stone-600 flex-shrink-0">
                <img
                  src={attachment.url}
                  alt={attachment.name}
                  className="w-full h-full object-cover"
                />
              </div>
            ) : (
              <div className="w-10 h-10 rounded bg-gray-200 dark:bg-stone-600 flex items-center justify-center flex-shrink-0">
                <Icon size={18} className="text-stone-500 dark:text-stone-400" />
              </div>
            )}

            {/* File info */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-stone-100 truncate">
                {attachment.name}
              </p>
              <p className="text-xs text-gray-500 dark:text-stone-400">
                {formatFileSize(attachment.size)}
              </p>
            </div>

            {/* Remove button */}
            <button
              type="button"
              onClick={() => onRemove(attachment.id)}
              className="p-1 rounded-full hover:bg-gray-200 dark:hover:bg-stone-600 text-gray-500 dark:text-stone-400"
              title={t("fileUpload.removeAttachment")}
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
});
```

**Step 2: Commit**
```bash
git add frontend/src/components/chat/AttachmentPreview.tsx
git commit -m "feat(chat): add AttachmentPreview component"
```

---

## Phase 10: Frontend - Integrate FileUploadButton

### Task 11: Add FileUploadButton to ChatInput

**Files:**
- Modify: `frontend/src/components/chat/ChatInput.tsx:14`
- Modify: `frontend/src/components/chat/ChatInput.tsx:360-374`

**Step 1: Add import**

```typescript
import { FileUploadButton } from "./FileUploadButton";
```

**Step 2: Add to toolbar (left side, before ToolSelector)**

```typescript
{/* File upload button - before tools */}
<FileUploadButton
  onAttachmentsChange={(attachments) => {
    // TODO: Handle attachments when sending message
  }}
/>
```

**Step 3: Commit**
```bash
git add frontend/src/components/chat/ChatInput.tsx
git commit -m "feat(chat): integrate FileUploadButton into ChatInput"
```

---

## Phase 11: Frontend - i18n Keys

### Task 12: Add Translation Keys

**Files:**
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/zh.json`

**Step 1: Add English translations**

```json
"fileUpload": {
  "title": "Upload file",
  "dragDrop": "Drag and drop files here or click to upload",
  "uploading": "Uploading...",
  "uploadSuccess": "Upload successful",
  "uploadFailed": "Upload failed",
  "noPermission": "No permission to upload {{type}} files",
  "fileTooLarge": "File size exceeds limit",
  "tooManyFiles": "Maximum {{count}} files per upload",
  "removeAttachment": "Remove attachment",
  "categories": {
    "image": "image",
    "video": "video",
    "audio": "audio",
    "document": "document"
  }
}
```

**Step 2: Add Chinese translations**

```json
"fileUpload": {
  "title": "上传文件",
  "dragDrop": "拖拽文件到这里或点击上传",
  "uploading": "上传中...",
  "uploadSuccess": "上传成功",
  "uploadFailed": "上传失败",
  "noPermission": "没有权限上传{{type}}文件",
  "fileTooLarge": "文件大小超过限制",
  "tooManyFiles": "一次最多上传{{count}}个文件",
  "removeAttachment": "移除附件",
  "categories": {
    "image": "图片",
    "video": "视频",
    "audio": "音频",
    "document": "文档"
  }
}
```

**Step 3: Commit**
```bash
git add frontend/src/i18n/locales/en.json frontend/src/i18n/locales/zh.json
git commit -m "i18n: add file upload translation keys"
```

---

## Phase 12: Testing & Verification

### Task 13: Test Upload Flow

**Step 1: Start backend server**
```bash
cd /home/yangyang/LambChat && uvicorn src.api.main:app --reload
```

**Step 2: Test upload endpoint**
```bash
curl -X POST http://localhost:8000/api/upload/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@test.jpg"
```

**Step 3: Test proxy endpoint**
```bash
curl -I http://localhost:8000/api/upload/file/uploads/...
```

**Step 4: Commit**
```bash
git commit -m "test: verify file upload flow"
```
