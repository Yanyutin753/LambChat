import { computeFileHash } from "../../utils/fileHash";
import { getAccessToken } from "./token";
import { isCurrentFileAccount } from "./uploadFileUrl";
import {
  getFileExtension,
  isImageFile,
} from "../../components/documents/utils/fileTypeChecks";
/**
 * Upload API - 文件上传
 */

import type { FileCheckResult, UploadConfig, UploadResult } from "../../types";
import { API_BASE, getFullUrl } from "./config";
import { authFetch } from "./fetch";
import { uploadDirect } from "./directUpload";
import { authenticatedRequest } from "./authenticatedRequest";
import {
  getValidAccessToken,
  redirectToLogin,
  refreshAccessToken,
} from "./tokenManager";
import { getRefreshToken } from "./token";
import i18n from "i18next";
import { parseErrorDetail, translateApiError } from "../../utils/backendErrors";

interface SignedUrlItem {
  key: string;
  url: string | null;
  error?: string;
}

export interface UploadOptions {
  folder?: string;
  onProgress?: (progress: number, loaded: number, total: number) => void;
  onProcessingProgress?: (progress: number) => void;
}

export interface UploadHandle {
  promise: Promise<UploadResult>;
  abort: () => void;
}

let _configPromise: Promise<UploadConfig> | null = null;

async function findExistingUpload(
  file: File,
  signal: AbortSignal,
): Promise<FileCheckResult> {
  const preparation = new AbortController();
  let abort!: () => void;
  const cancelled = new Promise<never>((_resolve, reject) => {
    abort = () => {
      preparation.abort();
      reject(new DOMException("Upload preparation was aborted", "AbortError"));
    };
  });
  // Hashing and dedup are optional; share one budget before sending the file.
  const timer = setTimeout(abort, 3000);
  signal.addEventListener("abort", abort, { once: true });
  if (signal.aborted) abort();
  try {
    return await Promise.race([
      (async () => {
        const hash = await computeFileHash(file, preparation.signal);
        if (preparation.signal.aborted)
          throw new DOMException("Aborted", "AbortError");
        return uploadApi.checkFile(
          hash,
          file.size,
          file.name,
          file.type,
          preparation.signal,
        );
      })(),
      cancelled,
    ]);
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", abort);
  }
}

function uploadViaBackend(
  file: File,
  folderOrOptions: string | UploadOptions = "uploads",
): UploadHandle {
  // Handle backward compatibility: string folder or options object
  const options: UploadOptions =
    typeof folderOrOptions === "string"
      ? { folder: folderOrOptions }
      : folderOrOptions;

  const folder = options.folder || "uploads";
  const { onProgress } = options;
  const account = getAccessToken();

  let xhr = new XMLHttpRequest();
  let aborted = false;

  const promise = new Promise<UploadResult>((resolve, reject) => {
    const uploadOnce = async (retried: boolean) => {
      const formData = new FormData();
      formData.append("file", file);

      const token = await getValidAccessToken();
      if (aborted || !isCurrentFileAccount(account)) {
        reject(new DOMException("Upload was aborted", "AbortError"));
        return;
      }

      xhr = new XMLHttpRequest();

      if (onProgress) {
        xhr.upload.addEventListener("progress", (event) => {
          if (event.lengthComputable) {
            const progress = Math.round((event.loaded / event.total) * 100);
            onProgress(progress, event.loaded, event.total);
          }
        });
      }

      xhr.addEventListener("load", async () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const raw = JSON.parse(xhr.responseText);
            const result: UploadResult = {
              key: raw.key,
              url: raw.url,
              name: raw.name,
              type: raw.type,
              mimeType: raw.mimeType ?? raw.mime_type ?? "",
              size: raw.size,
            };
            resolve(result);
          } catch {
            reject(new Error("Failed to parse upload response"));
          }
          return;
        }

        if (xhr.status === 401 && !retried && getRefreshToken()) {
          try {
            await refreshAccessToken();
            await uploadOnce(true);
            return;
          } catch (error) {
            if ((error as Error & { status?: number })?.status === 401)
              redirectToLogin();
            reject(error);
            return;
          }
        }

        try {
          const errorData = JSON.parse(xhr.responseText);
          const { code, message, args } = parseErrorDetail(errorData);
          const error = new Error(
            translateApiError(
              code,
              message || `Upload failed: ${xhr.statusText}`,
              args,
              i18n.t.bind(i18n),
            ),
          ) as Error & { status?: number; code?: string };
          error.status = xhr.status;
          error.code = code;
          reject(error);
        } catch {
          reject(new Error(`Upload failed: ${xhr.statusText}`));
        }
      });

      xhr.addEventListener("error", () => {
        reject(new Error("Network error during upload"));
      });

      xhr.addEventListener("abort", () => {
        aborted = true;
        reject(new DOMException("Upload was aborted", "AbortError"));
      });

      const path = `/api/upload/file?folder=${encodeURIComponent(folder)}`;
      xhr.open("POST", getFullUrl(path) || path);
      xhr.withCredentials = true;

      if (token) {
        xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      }

      xhr.send(formData);
    };

    void uploadOnce(false).catch(reject);
  });

  return {
    promise,
    abort: () => {
      aborted = true;
      xhr.abort();
    },
  };
}

export const uploadApi = {
  uploadFile(
    file: File,
    folderOrOptions: string | UploadOptions = "uploads",
  ): UploadHandle {
    const options =
      typeof folderOrOptions === "string"
        ? { folder: folderOrOptions }
        : folderOrOptions;
    const controller = new AbortController();
    const account = getAccessToken();
    let upload: UploadHandle | undefined;
    const assertActive = () => {
      if (controller.signal.aborted || !isCurrentFileAccount(account))
        throw new DOMException("Upload was aborted", "AbortError");
    };
    const promise = (async (): Promise<UploadResult> => {
      let existing: FileCheckResult | undefined;
      try {
        existing = await findExistingUpload(file, controller.signal);
      } catch (error) {
        if ([401, 403].includes((error as { status?: number })?.status ?? 0))
          throw error;
        // Failed optional preparation falls back to server-verified upload.
      }
      assertActive();
      if (existing?.exists && existing.key) {
        options.onProgress?.(100, file.size, file.size);
        const url = existing.url || `/api/upload/file/${existing.key}`;
        return {
          key: existing.key,
          url: getFullUrl(url) || url,
          name: file.name,
          type: existing.type!,
          mimeType: existing.mimeType || file.type,
          size: existing.size ?? file.size,
        };
      }
      const extension = getFileExtension(file.name);
      const mime = file.type.split(";", 1)[0].trim().toLowerCase();
      const cloudImage =
        (mime.startsWith("image/") || isImageFile(extension)) &&
        !["gif", "svg"].includes(extension) &&
        !["image/gif", "image/svg+xml"].includes(mime);
      // Raster images use cloud preparation; avoid a redundant direct-upload handshake.
      upload = cloudImage
        ? uploadViaBackend(file, options)
        : uploadDirect(file, options, () => uploadViaBackend(file, options));
      const result = await upload.promise;
      assertActive();
      return result;
    })();
    return {
      promise,
      abort: () => {
        controller.abort();
        upload?.abort();
      },
    };
  },

  /**
   * Check if file already exists by hash (for deduplication)
   */
  async checkFile(
    hash: string,
    size: number,
    name: string,
    mimeType: string,
    signal?: AbortSignal,
  ): Promise<FileCheckResult> {
    const path = "/api/upload/check";
    const res = await authenticatedRequest(getFullUrl(path) || path, {
      signal,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({ hash, size, name, mime_type: mimeType }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      const { code, message, args } = parseErrorDetail(detail);
      throw Object.assign(
        new Error(
          translateApiError(
            code,
            message || `Check failed: ${res.status}`,
            args,
            i18n.t.bind(i18n),
          ),
        ),
        { status: res.status, code },
      );
    }
    const data = await res.json();
    if (!data.exists) {
      return { exists: false };
    }
    return {
      ...data,
      mimeType: data.mime_type || data.mimeType,
    };
  },

  /**
   * 上传头像
   */
  async uploadAvatar(file: File): Promise<UploadResult> {
    const formData = new FormData();
    formData.append("file", file);

    const response = await authenticatedRequest(
      `${API_BASE}/api/upload/avatar`,
      {
        method: "POST",
        body: formData,
        credentials: "include",
      },
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Upload failed: ${response.statusText}`,
      );
    }

    return response.json();
  },

  /**
   * 删除头像
   */
  async deleteAvatar(): Promise<{ deleted: boolean }> {
    const response = await authenticatedRequest(
      `${API_BASE}/api/upload/avatar`,
      {
        method: "DELETE",
        credentials: "include",
      },
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Delete failed: ${response.statusText}`,
      );
    }

    return response.json();
  },

  /**
   * 获取存储配置
   */
  async getConfig(): Promise<UploadConfig> {
    if (!_configPromise) {
      _configPromise = authFetch<UploadConfig>(`${API_BASE}/api/upload/config`);
    }
    return _configPromise;
  },

  /**
   * 获取 S3 签名 URL（用于访问私有文件）
   */
  async getSignedUrl(key: string, expires: number = 3600): Promise<string> {
    const result = await authFetch<SignedUrlItem>(
      `${API_BASE}/api/upload/signed-url?key=${encodeURIComponent(
        key,
      )}&expires=${expires}`,
    );
    if (result.error || !result.url) {
      throw new Error(result.error || "Failed to get signed URL");
    }
    return getFullUrl(result.url) || result.url;
  },

  /**
   * 批量获取 S3 签名 URL
   */
  async getSignedUrls(
    keys: string[],
    expires: number = 3600,
  ): Promise<{ urls: SignedUrlItem[]; expires_in: number }> {
    const result = await authFetch<{
      urls: SignedUrlItem[];
      expires_in: number;
    }>(`${API_BASE}/api/upload/signed-urls`, {
      method: "POST",
      body: JSON.stringify({ keys, expires }),
    });
    return {
      ...result,
      urls: result.urls.map((item) => ({
        ...item,
        url: item.url ? getFullUrl(item.url) || item.url : item.url,
      })),
    };
  },

  /**
   * 删除上传的文件
   */
  async deleteFile(key: string): Promise<{ deleted: boolean; key: string }> {
    const response = await authenticatedRequest(
      `${API_BASE}/api/upload/${encodeURIComponent(key)}`,
      {
        method: "DELETE",
        credentials: "include",
      },
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Delete failed: ${response.statusText}`,
      );
    }

    return response.json();
  },
};
