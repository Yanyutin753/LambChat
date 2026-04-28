import type {
  Assistant,
  AssistantCreate,
  AssistantListScope,
  AssistantUpdate,
} from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";

const ASSISTANTS_API = `${API_BASE}/api/assistants`;

export interface AssistantListParams {
  scope?: AssistantListScope;
  search?: string;
  tags?: string[];
  category?: string;
}

export function buildAssistantListUrl(params?: AssistantListParams): string {
  const searchParams = new URLSearchParams();
  if (params?.scope && params.scope !== "public") {
    searchParams.set("scope", params.scope);
  }
  if (params?.search) {
    searchParams.set("search", params.search);
  }
  if (params?.tags && params.tags.length > 0) {
    searchParams.set("tags", params.tags.join(","));
  }
  if (params?.category) {
    searchParams.set("category", params.category);
  }

  const query = searchParams.toString();
  return `${ASSISTANTS_API}${query ? `?${query}` : ""}`;
}

export function buildAssistantDetailUrl(assistantId: string): string {
  return `${ASSISTANTS_API}/${encodeURIComponent(assistantId)}`;
}

export function buildAssistantCloneUrl(assistantId: string): string {
  return `${buildAssistantDetailUrl(assistantId)}/clone`;
}

export function buildAssistantSelectUrl(assistantId: string): string {
  return `${buildAssistantDetailUrl(assistantId)}/select`;
}

export const assistantApi = {
  async list(params?: AssistantListParams): Promise<Assistant[]> {
    return authFetch<Assistant[]>(buildAssistantListUrl(params));
  },

  async get(assistantId: string): Promise<Assistant> {
    return authFetch<Assistant>(buildAssistantDetailUrl(assistantId));
  },

  async create(data: AssistantCreate): Promise<Assistant> {
    return authFetch<Assistant>(ASSISTANTS_API, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async update(assistantId: string, data: AssistantUpdate): Promise<Assistant> {
    return authFetch<Assistant>(buildAssistantDetailUrl(assistantId), {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  async delete(assistantId: string): Promise<{ status: string }> {
    return authFetch<{ status: string }>(buildAssistantDetailUrl(assistantId), {
      method: "DELETE",
    });
  },

  async clone(assistantId: string): Promise<Assistant> {
    return authFetch<Assistant>(buildAssistantCloneUrl(assistantId), {
      method: "POST",
    });
  },
};
