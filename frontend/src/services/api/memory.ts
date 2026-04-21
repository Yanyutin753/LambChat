/**
 * Memory API - 记忆空间
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export interface MemoryItem {
  memory_id: string;
  title: string;
  summary: string;
  memory_type: string;
  tags: string[];
  content: string;
  source: string;
  created_at: string | null;
  updated_at: string | null;
  access_count: number;
  has_full_content: boolean;
}

export interface MemoryListResponse {
  memories: MemoryItem[];
  total: number;
}

export const memoryApi = {
  async list(params?: {
    memory_type?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }): Promise<MemoryListResponse> {
    const query = new URLSearchParams();
    if (params?.memory_type) query.set("memory_type", params.memory_type);
    if (params?.search) query.set("search", params.search);
    if (params?.limit !== undefined) query.set("limit", String(params.limit));
    if (params?.offset !== undefined)
      query.set("offset", String(params.offset));
    const qs = query.toString();
    const url = `${API_BASE}/api/memory/${qs ? `?${qs}` : ""}`;
    return authFetch<MemoryListResponse>(url);
  },

  async get(memory_id: string): Promise<MemoryItem> {
    return authFetch<MemoryItem>(`${API_BASE}/api/memory/${memory_id}`);
  },

  async delete(
    memory_id: string,
  ): Promise<{ success: boolean; message: string }> {
    return authFetch<{ success: boolean; message: string }>(
      `${API_BASE}/api/memory/${memory_id}`,
      { method: "DELETE" },
    );
  },

  async batchDelete(
    memory_ids: string[],
  ): Promise<{ success: boolean; deleted: number }> {
    return authFetch<{ success: boolean; deleted: number }>(
      `${API_BASE}/api/memory/batch-delete`,
      { method: "POST", body: JSON.stringify({ memory_ids }) },
    );
  },
};
