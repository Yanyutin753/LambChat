/**
 * Folder API - 文件夹管理
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type { Folder, FolderCreate, FolderUpdate } from "../../types";

export const folderApi = {
  /**
   * List all folders for current user
   */
  async list(): Promise<Folder[]> {
    return authFetch<Folder[]>(`${API_BASE}/api/folders`);
  },

  /**
   * Create a new folder
   */
  async create(data: FolderCreate): Promise<Folder> {
    return authFetch<Folder>(`${API_BASE}/api/folders`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * Update a folder (rename)
   */
  async update(folderId: string, data: FolderUpdate): Promise<Folder> {
    return authFetch<Folder>(`${API_BASE}/api/folders/${folderId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  /**
   * Delete a folder
   */
  async delete(folderId: string): Promise<{ status: string }> {
    return authFetch<{ status: string }>(
      `${API_BASE}/api/folders/${folderId}`,
      {
        method: "DELETE",
      },
    );
  },
};
