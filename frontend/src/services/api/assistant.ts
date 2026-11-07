import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type { BackendSession } from "./session";
import type {
  Assistant,
  AssistantConfiguration,
  AssistantStatus,
  AssistantTask,
  AssistantDiscussion,
  AssistantRule,
  AssistantRuleCreate,
} from "../../types/assistant";

const endpoint = `${API_BASE}/api/assistants`;
const resource = (id: string) => `${endpoint}/${encodeURIComponent(id)}`;

export const assistantApi = {
  chief() {
    return authFetch<Assistant>(`${endpoint}/chief`, { method: "POST" });
  },
  members(id: string) {
    return authFetch<{
      members: {
        id: string;
        name: string;
        status: string;
        avatar?: string | null;
      }[];
    }>(`${resource(id)}/members`);
  },
  forConversation(sessionId: string) {
    return authFetch<Assistant | null>(
      `${endpoint}/conversation/${encodeURIComponent(sessionId)}`,
    );
  },
  list(skip = 0, limit = 20, archived = false) {
    return authFetch<{
      assistants: Assistant[];
      total: number;
      skip: number;
      limit: number;
    }>(
      `${endpoint}?${new URLSearchParams({
        skip: String(skip),
        limit: String(limit),
        archived: String(archived),
      })}`,
    );
  },
  get(id: string) {
    return authFetch<Assistant>(resource(id));
  },
  create(data: AssistantConfiguration) {
    return authFetch<Assistant>(endpoint, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
  update(
    id: string,
    data: AssistantConfiguration & {
      revision: number;
      status: AssistantStatus;
    },
  ) {
    return authFetch<Assistant>(resource(id), {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },
  openConversation(id: string) {
    return authFetch<BackendSession>(`${resource(id)}/conversation`, {
      method: "POST",
    });
  },
  rules(id: string, skip = 0, limit = 10) {
    return authFetch<{ rules: AssistantRule[]; total: number }>(
      `${resource(id)}/rules?${new URLSearchParams({
        skip: String(skip),
        limit: String(limit),
      })}`,
    );
  },
  createRule(id: string, data: AssistantRuleCreate) {
    return authFetch<{ id: string }>(`${resource(id)}/rules`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
  discussions(id: string, skip = 0, limit = 10) {
    return authFetch<{ discussions: AssistantDiscussion[]; total: number }>(
      `${resource(id)}/discussions?${new URLSearchParams({
        skip: String(skip),
        limit: String(limit),
      })}`,
    );
  },
  tasks(id: string, skip = 0, limit = 10) {
    return authFetch<{ tasks: AssistantTask[]; total: number }>(
      `${resource(id)}/tasks?${new URLSearchParams({
        skip: String(skip),
        limit: String(limit),
      })}`,
    );
  },
  task(id: string, taskId: string) {
    return authFetch<AssistantTask>(
      `${resource(id)}/tasks/${encodeURIComponent(taskId)}`,
    );
  },
  createTask(
    id: string,
    data: { description: string; request_id: string; timeout_seconds: number },
  ) {
    return authFetch<{ task_id: string; session_id: string; status: string }>(
      `${resource(id)}/tasks`,
      { method: "POST", body: JSON.stringify(data) },
    );
  },
  reviewTask(
    id: string,
    taskId: string,
    data: { run_id: string; revision: number; accepted: boolean },
  ) {
    return authFetch<AssistantTask>(
      `${resource(id)}/tasks/${encodeURIComponent(taskId)}/review`,
      { method: "PUT", body: JSON.stringify(data) },
    );
  },
};
