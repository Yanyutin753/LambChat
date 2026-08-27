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

export interface MemoryExportItem extends Omit<MemoryItem, "has_full_content"> {
  context: string;
  accessed_at: string | null;
}

export interface MemoryExportResponse {
  version: number;
  exported_at: string;
  memories: MemoryExportItem[];
}

export interface MemoryImportRequest {
  version?: number;
  memories: Array<Partial<MemoryExportItem> & { content: string }>;
}

export interface MemoryImportResponse {
  success: boolean;
  imported: number;
  created: number;
  overwritten: number;
}

export interface MemoryCreateRequest {
  title?: string;
  content: string;
  summary?: string;
  memory_type?: string;
  tags?: string[];
  context?: string;
}

export interface MemoryUpdateRequest {
  title?: string;
  content?: string;
  summary?: string;
  memory_type?: string;
  tags?: string[];
  source?: string;
}

export interface MemoryCreateResponse {
  success: boolean;
  memory_id: string;
  title: string;
  summary: string;
  memory_type: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface MemoryUpdateResponse {
  success: boolean;
  memory_id: string;
}

export const memoryApi = {
  async list(params?: {
    memory_type?: string;
    source?: string;
    search?: string;
    context?: string;
    limit?: number;
    offset?: number;
  }): Promise<MemoryListResponse> {
    const query = new URLSearchParams();
    if (params?.memory_type) query.set("memory_type", params.memory_type);
    if (params?.source) query.set("source", params.source);
    if (params?.search) query.set("search", params.search);
    if (params?.context) query.set("context", params.context);
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

  async create(data: MemoryCreateRequest): Promise<MemoryCreateResponse> {
    return authFetch<MemoryCreateResponse>(`${API_BASE}/api/memory/`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async update(
    memory_id: string,
    data: MemoryUpdateRequest,
  ): Promise<MemoryUpdateResponse> {
    return authFetch<MemoryUpdateResponse>(
      `${API_BASE}/api/memory/${memory_id}`,
      { method: "PUT", body: JSON.stringify(data) },
    );
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

  async export(): Promise<MemoryExportResponse> {
    return authFetch<MemoryExportResponse>(`${API_BASE}/api/memory/export`);
  },

  async import(data: MemoryImportRequest): Promise<MemoryImportResponse> {
    return authFetch<MemoryImportResponse>(`${API_BASE}/api/memory/import`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
};
