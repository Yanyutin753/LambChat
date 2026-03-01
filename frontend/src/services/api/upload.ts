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

export const uploadApi = {
  /**
   * 上传文件
   */
  async uploadFile(
    file: File,
    folder: string = "uploads",
  ): Promise<UploadResult> {
    const formData = new FormData();
    formData.append("file", file);

    const token = getAccessToken();
    const response = await fetch(
      `${API_BASE}/api/upload/file?folder=${encodeURIComponent(folder)}`,
      {
        method: "POST",
        body: formData,
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
        errorData.detail || `Upload failed: ${response.statusText}`,
      );
    }

    return response.json();
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
