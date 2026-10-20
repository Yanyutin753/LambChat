/**
 * Memory API - 记忆空间
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import { uuid } from "../../utils/uuid";

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
  scope?: "user" | "project" | "reference";
  project_id?: string | null;
  source_refs?: Array<{ session_id: string; run_id: string }>;
  origin_session_ids?: string[];
  content_truncated?: boolean;
  content_original_chars?: number;
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

  async importAll(
    data: unknown,
    onProgress?: (progress: MemoryImportProgress) => void,
  ): Promise<MemoryImportResponse> {
    const preflight = (batch: MemoryImportRequest) =>
      authFetch<MemoryImportPreflight>(
        `${API_BASE}/api/memory/import?validate_only=true`,
        { method: "POST", body: JSON.stringify(batch) },
      );
    const { limits } = await preflight({ memories: [] });
    const batches = prepareImportBatches(data, limits);
    const total = batches.reduce(
      (sum, batch) => sum + batch.memories.length,
      0,
    );
    let checked = 0;
    onProgress?.({ phase: "checking", processed: 0, total });
    for (const batch of batches) {
      const result = await preflight(batch);
      if (!result.success || result.validated !== batch.memories.length)
        throw new Error("Memory preflight failed");
      checked += result.validated;
      onProgress?.({ phase: "checking", processed: checked, total });
    }
    const confirmed: MemoryImportResponse = {
      success: true,
      imported: 0,
      created: 0,
      overwritten: 0,
    };
    onProgress?.({ phase: "importing", processed: 0, total });
    for (const batch of batches) {
      try {
        const result = await memoryApi.import(batch);
        if (
          !result.success ||
          ![result.imported, result.created, result.overwritten].every(
            (count) => Number.isSafeInteger(count) && count >= 0,
          ) ||
          result.imported !== batch.memories.length ||
          result.created + result.overwritten !== result.imported
        )
          throw new Error("Incomplete memory import response");
        confirmed.imported += result.imported;
        confirmed.created += result.created;
        confirmed.overwritten += result.overwritten;
      } catch (cause) {
        throw new MemoryImportError({ ...confirmed }, cause);
      }
      onProgress?.({
        phase: "importing",
        processed: confirmed.imported,
        total,
      });
    }
    return confirmed;
  },
};

export interface MemoryImportProgress {
  phase: "checking" | "importing";
  processed: number;
  total: number;
}

export class MemoryImportError extends Error {
  constructor(
    readonly confirmed: MemoryImportResponse,
    cause: unknown,
  ) {
    super("Memory import stopped with an unconfirmed batch", { cause });
  }
}

interface MemoryImportLimits {
  max_records: number;
  max_origin_sessions?: number;
  max_content_chars: number;
  max_total_content_chars: number;
}

interface MemoryImportPreflight {
  success: boolean;
  validated: number;
  limits: MemoryImportLimits;
}

function prepareImportBatches(
  data: unknown,
  limits: MemoryImportLimits,
): MemoryImportRequest[] {
  if (
    !data ||
    typeof data !== "object" ||
    !("memories" in data) ||
    !Array.isArray(data.memories)
  ) {
    throw new Error("Invalid memory backup");
  }
  if (
    !Object.values(limits).every(
      (value) => Number.isSafeInteger(value) && value > 0,
    )
  ) {
    throw new Error("Invalid memory import limits");
  }
  const batches: MemoryImportRequest[] = [];
  let batch: MemoryImportRequest = { memories: [] };
  let characters = 0;
  let origins = 0;
  const maxOrigins = limits.max_origin_sessions ?? 50_000;
  for (const raw of data.memories) {
    if (
      !raw ||
      typeof raw !== "object" ||
      typeof raw.content !== "string" ||
      raw.content_truncated === true
    ) {
      throw new Error("Invalid or incomplete memory content");
    }
    const length = [...raw.content.trim()].length;
    const sourceIds =
      raw.origin_session_ids === undefined ? [] : raw.origin_session_ids;
    if (
      !Array.isArray(sourceIds) ||
      sourceIds.some(
        (id: unknown) =>
          typeof id !== "string" || !id.trim() || [...id].length > 1024,
      ) ||
      sourceIds.length > maxOrigins
    )
      throw new Error("Invalid memory source sessions");
    if (
      length < 5 ||
      length > limits.max_content_chars ||
      length > limits.max_total_content_chars
    ) {
      throw new Error("Memory content exceeds import limits");
    }
    if (
      batch.memories.length >= limits.max_records ||
      characters + length > limits.max_total_content_chars ||
      origins + sourceIds.length > maxOrigins
    ) {
      batches.push(batch);
      batch = { memories: [] };
      characters = 0;
      origins = 0;
    }
    batch.memories.push({
      ...raw,
      memory_id:
        typeof raw.memory_id === "string" && raw.memory_id.trim()
          ? raw.memory_id.trim()
          : uuid().replaceAll("-", ""),
    });
    characters += length;
    origins += sourceIds.length;
  }
  if (batch.memories.length) batches.push(batch);
  return batches;
}
