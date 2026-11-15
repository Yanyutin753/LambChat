/**
 * Health API - system health and memory diagnostics
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export interface MemoryOverview {
  status: "stable" | "suspected_leak" | "memory_pressure" | "unavailable";
  rss: string | null;
  vms: string | null;
  growth: string | null;
  threads: number | null;
  open_files: number | null;
  history_size: number | null;
  last_sample_at: string | null;
}

export interface GrowthRow {
  location: string;
  size_diff_bytes: number;
  size_diff: string | null;
  current_size_bytes: number;
}

export interface AllocationRow {
  location: string;
  size_bytes: number;
  size: string | null;
  count: number;
}

export interface ObjectRow {
  type: string;
  count: number;
  label: string;
}

export type MemoryHighlight =
  | {
      kind: "status";
      status: MemoryOverview["status"];
      severity: "info" | "warning";
    }
  | {
      kind: "unavailable";
      reason: string;
    }
  | {
      kind: "top_growth";
      location: string;
      size_diff: string | null;
    }
  | {
      kind: "top_allocation";
      location: string;
      size: string | null;
    }
  | {
      kind: "top_object_type";
      type: string;
      count: number;
    };

export interface MemoryDiagnostics {
  overview: MemoryOverview;
  highlights: MemoryHighlight[];
  top_growth: GrowthRow[];
  top_allocations: AllocationRow[];
  top_objects: ObjectRow[];
  summary: Record<string, unknown>;
}

export const healthApi = {
  async getMemoryDiagnostics(refresh = false): Promise<MemoryDiagnostics> {
    const params = refresh ? "?refresh=true" : "";
    return authFetch<MemoryDiagnostics>(`${API_BASE}/health/memory${params}`);
  },
};
