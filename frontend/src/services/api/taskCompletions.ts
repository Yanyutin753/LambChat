import { authFetch } from "./fetch";
import { API_BASE } from "./config";

export interface TaskCompletionEvent {
  id: string;
  created_at: string;
  session_id: string;
  run_id: string;
  status: string;
  dedupe_key: string;
  notification_kind: string;
  parent_session_id?: string;
  goal_status?: string;
  message?: string;
  unread_count?: number;
  project_id?: string | null;
  scheduled_task_id?: string | null;
  is_favorite?: boolean;
}
export interface TaskCompletionPage {
  items: TaskCompletionEvent[];
  cursor: string | null;
  next_cursor: string | null;
}
export function getTaskCompletions(
  cursor: string | null,
  since?: string,
): Promise<TaskCompletionPage> {
  const query = new URLSearchParams({ limit: "50" });
  if (cursor) query.set("cursor", cursor);
  if (since) query.set("since", since);
  return authFetch<TaskCompletionPage>(
    `${API_BASE}/api/task-completions?${query}`,
  );
}
