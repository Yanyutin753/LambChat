/**
 * Upload API - 文件上传
 */

import type { UploadConfig, UploadResult } from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import { getAccessToken } from "./token";

interface SignedUrlItem {
  key: string;
  url: string | null;
  error?: string;
}

export interface UploadOptions {
  folder?: string;
  onProgress?: (progress: number, loaded: number, total: number) => void;
}

export const uploadApi = {
  /**
   * 上传文件
   * @param file - The file to upload
   * @param folderOrOptions - Either a folder string (for backward compatibility) or UploadOptions object
   */
  async uploadFile(
    file: File,
    folderOrOptions: string | UploadOptions = "uploads",
  ): Promise<UploadResult> {
    // Handle backward compatibility: string folder or options object
    const options: UploadOptions =
      typeof folderOrOptions === "string"
        ? { folder: folderOrOptions }
        : folderOrOptions;

    const folder = options.folder || "uploads";
    const { onProgress } = options;

    return new Promise((resolve, reject) => {
      const formData = new FormData();
      formData.append("file", file);

      const xhr = new XMLHttpRequest();

      // Track upload progress
      if (onProgress) {
        xhr.upload.addEventListener("progress", (event) => {
          if (event.lengthComputable) {
            const progress = Math.round((event.loaded / event.total) * 100);
            onProgress(progress, event.loaded, event.total);
          }
        });
      }

      // Handle successful completion
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const result = JSON.parse(xhr.responseText) as UploadResult;
            resolve(result);
          } catch {
            reject(new Error("Failed to parse upload response"));
          }
        } else {
          // Handle HTTP errors
          try {
            const errorData = JSON.parse(xhr.responseText);
            reject(
              new Error(errorData.detail || `Upload failed: ${xhr.statusText}`),
            );
          } catch {
            reject(new Error(`Upload failed: ${xhr.statusText}`));
          }
        }
      });

      // Handle network errors
      xhr.addEventListener("error", () => {
        reject(new Error("Network error during upload"));
      });

      // Handle abort
      xhr.addEventListener("abort", () => {
        reject(new Error("Upload was aborted"));
      });

      // Set up and send the request
      const url = `${API_BASE}/api/upload/file?folder=${encodeURIComponent(
        folder,
      )}`;
      xhr.open("POST", url);
      xhr.withCredentials = true;

      // Set authorization header if token exists
      const token = getAccessToken();
      if (token) {
        xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      }

      xhr.send(formData);
    });
  },

  /**
   * 上传头像
   */
  async uploadAvatar(file: File): Promise<UploadResult> {
    const formData = new FormData();
    formData.append("file", file);

    const token = getAccessToken();
    const response = await fetch(`${API_BASE}/api/upload/avatar`, {
      method: "POST",
      body: formData,
      headers: token
        ? {
            Authorization: `Bearer ${token}`,
          }
        : {},
      credentials: "include",
    });

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
    const token = getAccessToken();
    const response = await fetch(`${API_BASE}/api/upload/avatar`, {
      method: "DELETE",
      headers: token
        ? {
            Authorization: `Bearer ${token}`,
          }
        : {},
      credentials: "include",
    });

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
    return authFetch<UploadConfig>(`${API_BASE}/api/upload/config`);
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
    return result.url;
  },

  /**
   * 批量获取 S3 签名 URL
   */
  async getSignedUrls(
    keys: string[],
    expires: number = 3600,
  ): Promise<{ urls: SignedUrlItem[]; expires_in: number }> {
    return authFetch(`${API_BASE}/api/upload/signed-urls`, {
      method: "POST",
      body: JSON.stringify({ keys, expires }),
    });
  },

  /**
   * 删除上传的文件
   */
  async deleteFile(key: string): Promise<{ deleted: boolean; key: string }> {
    const token = getAccessToken();
    const response = await fetch(
      `${API_BASE}/api/upload/${encodeURIComponent(key)}`,
      {
        method: "DELETE",
        headers: token
          ? {
              Authorization: `Bearer ${token}`,
            }
          : {},
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
