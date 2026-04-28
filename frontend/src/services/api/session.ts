/**
 * Session API - 会话管理
 */

import type {
  SessionEventsResponse,
  RunSummary,
  MessageAttachment,
} from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";

// Backend Session type (matches backend Session schema)
export interface BackendSession {
  id: string;
  user_id?: string;
  agent_id: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
  name?: string;
  metadata: Record<string, unknown>;
  unread_count?: number;
}

// Session list response type
export interface SessionListResponse {
  sessions: BackendSession[];
  total: number;
  skip: number;
  limit: number;
  has_more: boolean;
}

export interface SessionRunsQuery {
  limit?: number;
  trace_id?: string;
}

function getBrowserTimezone(): string | undefined {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return typeof timezone === "string" && timezone.trim() ? timezone : undefined;
}

export function buildSubmitChatBody({
  message,
  sessionId,
  agentOptions,
  attachments,
  projectId,
  disabledSkills,
  disabledMcpTools,
  userTimezone,
}: {
  message: string;
  sessionId?: string;
  agentOptions?: Record<string, boolean | string | number>;
  attachments?: MessageAttachment[];
  projectId?: string;
  disabledSkills?: string[];
  disabledMcpTools?: string[];
  userTimezone?: string;
}): Record<string, unknown> {
  const body: Record<string, unknown> = {
    message,
    session_id: sessionId,
    agent_options: agentOptions,
    attachments,
    disabled_skills: disabledSkills,
    disabled_mcp_tools: disabledMcpTools,
  };

  if (userTimezone) {
    body.user_timezone = userTimezone;
  }
  if (projectId) {
    body.project_id = projectId;
  }
  return body;
}

export function buildSessionRunsUrl(
  sessionId: string,
  options?: SessionRunsQuery,
): string {
  const searchParams = new URLSearchParams();
  if (options?.limit) {
    searchParams.set("limit", String(options.limit));
  }
  if (options?.trace_id) {
    searchParams.set("trace_id", options.trace_id);
  }

  const queryString = searchParams.toString();
  return `${API_BASE}/api/sessions/${sessionId}/runs${
    queryString ? `?${queryString}` : ""
  }`;
}

export const sessionApi = {
  /**
   * List all sessions with pagination
   */
  async list(params?: {
    status?: string;
    limit?: number;
    skip?: number;
    project_id?: string;
    search?: string;
    favorites_only?: boolean;
  }): Promise<SessionListResponse | BackendSession[]> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.skip) searchParams.set("skip", params.skip.toString());
    if (params?.project_id) searchParams.set("project_id", params.project_id);
    if (params?.search) searchParams.set("search", params.search);
    if (params?.favorites_only) searchParams.set("favorites_only", "true");

    const url = `${API_BASE}/api/sessions${
      searchParams.toString() ? `?${searchParams}` : ""
    }`;
    return authFetch<SessionListResponse | BackendSession[]>(url);
  },

  /**
   * Get a session
   */
  async get(sessionId: string): Promise<BackendSession | null> {
    try {
      return await authFetch<BackendSession>(
        `${API_BASE}/api/sessions/${sessionId}`,
      );
    } catch (error) {
      if ((error as Error).message.includes("404")) {
        return null;
      }
      throw error;
    }
  },

  /**
   * Get all session events
   */
  async getEvents(
    sessionId: string,
    options?: {
      event_types?: string[];
      run_id?: string;
      exclude_run_id?: string;
    },
  ): Promise<SessionEventsResponse & { run_id?: string }> {
    const searchParams = new URLSearchParams();
    if (options?.event_types && options.event_types.length > 0) {
      searchParams.set("event_types", options.event_types.join(","));
    }
    if (options?.run_id) {
      searchParams.set("run_id", options.run_id);
    }
    if (options?.exclude_run_id) {
      searchParams.set("exclude_run_id", options.exclude_run_id);
    }

    const url = `${API_BASE}/api/sessions/${sessionId}/events${
      searchParams.toString() ? `?${searchParams}` : ""
    }`;
    return authFetch<SessionEventsResponse & { run_id?: string }>(url);
  },

  /**
   * Get all runs for a session
   */
  async getRuns(
    sessionId: string,
    options?: SessionRunsQuery,
  ): Promise<{ session_id: string; runs: RunSummary[]; count: number }> {
    return authFetch(buildSessionRunsUrl(sessionId, options));
  },

  /**
   * Delete a session
   */
  async delete(sessionId: string) {
    return authFetch(`${API_BASE}/api/sessions/${sessionId}`, {
      method: "DELETE",
    });
  },

  /**
   * Update session status
   */
  async updateStatus(sessionId: string, status: "active" | "archived") {
    return authFetch(
      `${API_BASE}/api/sessions/${sessionId}/status?status=${status}`,
      {
        method: "PATCH",
      },
    );
  },

  /**
   * Clear messages for a session
   */
  async clearMessages(sessionId: string) {
    return authFetch(`${API_BASE}/api/sessions/${sessionId}/clear-messages`, {
      method: "POST",
    });
  },

  /**
   * Generate title for session using LLM
   */
  async generateTitle(
    sessionId: string,
    message: string,
    lang: string = "en",
  ): Promise<{ title: string; session_id: string }> {
    return authFetch(
      `${API_BASE}/api/sessions/${sessionId}/generate-title?message=${encodeURIComponent(
        message,
      )}&lang=${encodeURIComponent(lang)}`,
      {
        method: "POST",
      },
    );
  },

  /**
   * Get session task status
   */
  async getStatus(
    sessionId: string,
    runId?: string,
  ): Promise<{
    session_id: string;
    run_id?: string;
    status: string;
    error?: string;
  }> {
    const params = runId ? `?run_id=${runId}` : "";
    return authFetch(
      `${API_BASE}/api/chat/sessions/${sessionId}/status${params}`,
    );
  },

  /**
   * Cancel running task for a session
   */
  async cancel(sessionId: string): Promise<{
    success: boolean;
    message: string;
  }> {
    return authFetch(`${API_BASE}/api/chat/sessions/${sessionId}/cancel`, {
      method: "POST",
    });
  },

  /**
   * Submit a chat message (returns immediately)
   */
  async submitChat(
    agentId: string,
    message: string,
    sessionId?: string,
    agentOptions?: Record<string, boolean | string | number>,
    attachments?: MessageAttachment[],
    projectId?: string,
    disabledSkills?: string[],
    disabledMcpTools?: string[],
  ): Promise<{
    session_id: string;
    run_id: string;
    trace_id: string;
    status: string;
  }> {
    const body = buildSubmitChatBody({
      message,
      sessionId,
      agentOptions,
      attachments,
      projectId,
      disabledSkills,
      disabledMcpTools,
      userTimezone: getBrowserTimezone(),
    });
    return authFetch(`${API_BASE}/api/chat/stream?agent_id=${agentId}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /**
   * Move session to project
   */
  async moveToProject(
    sessionId: string,
    projectId: string | null,
  ): Promise<{ status: string; session: BackendSession }> {
    return authFetch(`${API_BASE}/api/sessions/${sessionId}/move`, {
      method: "POST",
      body: JSON.stringify({ project_id: projectId }),
    });
  },

  /**
   * Toggle session favorite state
   */
  async toggleFavorite(sessionId: string): Promise<{
    status: string;
    is_favorite: boolean;
    session: BackendSession;
  }> {
    return authFetch(`${API_BASE}/api/sessions/${sessionId}/favorite`, {
      method: "POST",
    });
  },

  /**
   * Update session (including name and metadata)
   */
  async update(
    sessionId: string,
    data: { name?: string; metadata?: Record<string, unknown> },
  ): Promise<{ status: string; session: BackendSession }> {
    return authFetch(`${API_BASE}/api/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  /**
   * Mark session as read (clear unread count)
   */
  async markRead(sessionId: string): Promise<void> {
    await authFetch(`${API_BASE}/api/sessions/${sessionId}/mark-read`, {
      method: "POST",
    });
  },
};
