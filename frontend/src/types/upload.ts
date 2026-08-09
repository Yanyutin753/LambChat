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
  /**
   * Client-only: original text when this attachment was created from long-text conversion.
   * Must be stripped before API submit.
   */
  localOriginalText?: string;
  /**
   * Client-only: marks an attachment created by long-text auto conversion.
   * Must be stripped before API submit.
   */
  fromLongText?: boolean;
  /** Client-only: links an attachment card to an inline composer node. */
  composerReferenceId?: string;
  /** Client-only: keeps a failed upload visible so the user can retry it. */
  uploadError?: string;
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
