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
  url?: string;
  /** Upload progress (0-100) */
  uploadProgress?: number;
  /** Whether upload is in progress */
  isUploading?: boolean;
}

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

export interface UploadConfig {
  enabled: boolean;
  provider?: string;
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

export interface FileCheckResult {
  exists: boolean;
  key?: string;
  url?: string;
  name?: string;
  type?: FileCategory;
  mimeType?: string;
  size?: number;
}
