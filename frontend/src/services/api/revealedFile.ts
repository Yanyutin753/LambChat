import { authFetch } from "./fetch";

export interface RevealedFileItem {
  id: string;
  file_key: string;
  file_name: string;
  file_type: "image" | "video" | "document" | "code" | "project" | "other";
  mime_type: string | null;
  file_size: number;
  url: string | null;
  session_id: string;
  session_name: string | null;
  trace_id: string;
  project_id: string | null;
  user_id: string;
  source: "reveal_file" | "reveal_project";
  description: string | null;
  original_path: string | null;
  created_at: string;
  is_favorite: boolean;
  project_meta?: {
    template:
      | "react"
      | "vue"
      | "vanilla"
      | "static"
      | "angular"
      | "svelte"
      | "solid"
      | "nextjs";
    entry?: string;
    file_count?: number;
    files: Record<
      string,
      {
        url: string;
        size: number;
        is_binary?: boolean;
        content_type?: string;
      }
    >;
  } | null;
}

export interface RevealedFileListResponse {
  items: RevealedFileItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface RevealedFileListParams {
  page?: number;
  page_size?: number;
  file_type?: string;
  session_id?: string;
  project_id?: string;
  search?: string;
  sort_by?: string;
  sort_order?: string;
  favorites_only?: boolean;
}

export interface SessionGroupItem {
  session_id: string;
  session_name: string | null;
  file_count: number;
  files: RevealedFileItem[];
}

export interface RevealedFileGroupedListParams {
  page?: number;
  page_size?: number;
  file_type?: string;
  project_id?: string;
  search?: string;
  sort_by?: string;
  sort_order?: string;
  favorites_only?: boolean;
}

export interface RevealedFileGroupedListResponse {
  sessions: SessionGroupItem[];
  total_sessions: number;
  page: number;
  page_size: number;
}

export const revealedFileApi = {
  async list(
    params: RevealedFileListParams = {},
  ): Promise<RevealedFileListResponse> {
    const sp = new URLSearchParams();
    if (params.page) sp.set("page", String(params.page));
    if (params.page_size) sp.set("page_size", String(params.page_size));
    if (params.file_type) sp.set("file_type", params.file_type);
    if (params.session_id) sp.set("session_id", params.session_id);
    if (params.project_id) sp.set("project_id", params.project_id);
    if (params.search) sp.set("search", params.search);
    if (params.sort_by) sp.set("sort_by", params.sort_by);
    if (params.sort_order) sp.set("sort_order", params.sort_order);
    if (params.favorites_only) sp.set("favorites_only", "true");
    const qs = sp.toString();
    return authFetch<RevealedFileListResponse>(`/api/files/revealed?${qs}`);
  },

  async toggleFavorite(fileId: string): Promise<{ is_favorite: boolean }> {
    return authFetch<{ is_favorite: boolean }>(
      `/api/files/revealed/${fileId}/favorite`,
      {
        method: "PATCH",
      },
    );
  },

  async getStats(): Promise<Record<string, number>> {
    return authFetch<Record<string, number>>("/api/files/revealed/stats");
  },

  async listGrouped(
    params: RevealedFileGroupedListParams = {},
  ): Promise<RevealedFileGroupedListResponse> {
    const sp = new URLSearchParams();
    if (params.page) sp.set("page", String(params.page));
    if (params.page_size) sp.set("page_size", String(params.page_size));
    if (params.file_type) sp.set("file_type", params.file_type);
    if (params.project_id) sp.set("project_id", params.project_id);
    if (params.search) sp.set("search", params.search);
    if (params.sort_by) sp.set("sort_by", params.sort_by);
    if (params.sort_order) sp.set("sort_order", params.sort_order);
    if (params.favorites_only) sp.set("favorites_only", "true");
    const qs = sp.toString();
    return authFetch<RevealedFileGroupedListResponse>(
      `/api/files/revealed/grouped?${qs}`,
    );
  },

  async getSessions(): Promise<
    { session_id: string; session_name: string | null; file_count: number }[]
  > {
    return authFetch<
      { session_id: string; session_name: string | null; file_count: number }[]
    >("/api/files/revealed/sessions");
  },
};
