import { authFetch } from "./fetch";
import type {
  ScheduledTask,
  ScheduledTaskCreatedBy,
  ScheduledTaskCreate,
  ScheduledTaskListResponse,
  ScheduledTaskStatus,
  ScheduledTaskUpdate,
  TaskRunListResponse,
  TaskSessionListResponse,
} from "../../types/scheduledTask";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export const scheduledTaskApi = {
  async list(
    skip: number = 0,
    limit: number = 20,
    status?: ScheduledTaskStatus,
    options?: {
      sourceSessionId?: string;
      createdBy?: ScheduledTaskCreatedBy;
      search?: string;
    },
  ): Promise<ScheduledTaskListResponse> {
    const params = new URLSearchParams({
      skip: skip.toString(),
      limit: limit.toString(),
    });
    if (status) {
      params.set("status", status);
    }
    if (options?.search?.trim()) {
      params.set("search", options.search.trim());
    }
    if (options?.sourceSessionId) {
      params.set("source_session_id", options.sourceSessionId);
    }
    if (options?.createdBy) {
      params.set("created_by", options.createdBy);
    }
    return authFetch<ScheduledTaskListResponse>(
      `${API_BASE}/api/scheduled-tasks/?${params}`,
    );
  },

  async listBySession(
    sessionId: string,
    skip: number = 0,
    limit: number = 20,
  ): Promise<ScheduledTaskListResponse> {
    return this.list(skip, limit, undefined, {
      sourceSessionId: sessionId,
      createdBy: "agent",
    });
  },

  async get(id: string): Promise<ScheduledTask> {
    return authFetch<ScheduledTask>(`${API_BASE}/api/scheduled-tasks/${id}`);
  },

  async create(data: ScheduledTaskCreate): Promise<ScheduledTask> {
    return authFetch<ScheduledTask>(`${API_BASE}/api/scheduled-tasks/`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async update(id: string, data: ScheduledTaskUpdate): Promise<ScheduledTask> {
    return authFetch<ScheduledTask>(`${API_BASE}/api/scheduled-tasks/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async pause(id: string): Promise<ScheduledTask> {
    return authFetch<ScheduledTask>(
      `${API_BASE}/api/scheduled-tasks/${id}/pause`,
      { method: "POST" },
    );
  },

  async resume(id: string): Promise<ScheduledTask> {
    return authFetch<ScheduledTask>(
      `${API_BASE}/api/scheduled-tasks/${id}/resume`,
      { method: "POST" },
    );
  },

  async delete(id: string): Promise<void> {
    return authFetch(`${API_BASE}/api/scheduled-tasks/${id}`, {
      method: "DELETE",
    });
  },

  async runNow(id: string): Promise<Record<string, unknown>> {
    return authFetch(`${API_BASE}/api/scheduled-tasks/${id}/run`, {
      method: "POST",
    });
  },

  async getRuns(
    id: string,
    limit: number = 20,
    offset: number = 0,
  ): Promise<TaskRunListResponse> {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
    });
    return authFetch<TaskRunListResponse>(
      `${API_BASE}/api/scheduled-tasks/${id}/runs?${params}`,
    );
  },

  async getSessions(
    id: string,
    skip: number = 0,
    limit: number = 20,
  ): Promise<TaskSessionListResponse> {
    const params = new URLSearchParams({
      skip: skip.toString(),
      limit: limit.toString(),
    });
    return authFetch<TaskSessionListResponse>(
      `${API_BASE}/api/scheduled-tasks/${id}/sessions?${params}`,
    );
  },
};
