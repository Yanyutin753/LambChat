// ============================================
// Scheduled Task Types
// ============================================

export type TriggerType = "interval" | "cron" | "date";
export type ScheduledTaskStatus = "active" | "paused" | "deleted";
export type ScheduledTaskCreatedBy = "user" | "agent" | "api";
export type RunStatus =
  | "pending"
  | "running"
  | "success"
  | "failed"
  | "skipped"
  | "timeout";

// Trigger configs
export interface IntervalTriggerConfig {
  seconds: number;
}

export interface CronTriggerConfig {
  year?: string | null;
  month?: string | null;
  day?: string | null;
  week?: string | null;
  day_of_week?: string | null;
  hour?: string | null;
  minute?: string | null;
  second?: string | null;
}

export interface DateTriggerConfig {
  run_date: string;
}

// Scheduled task (full response)
export interface ScheduledTask {
  execution_mode?: "conversation" | "standalone";
  target_session_id?: string | null;
  notification_policy?: "always" | "meaningful_changes";
  id: string;
  name: string;
  description: string | null;
  agent_id: string;
  trigger_type: TriggerType;
  trigger_config: IntervalTriggerConfig | CronTriggerConfig | DateTriggerConfig;
  timezone: string;
  input_payload: Record<string, unknown>;
  status: ScheduledTaskStatus;
  enabled: boolean;
  run_on_start: boolean;
  max_retries: number;
  timeout_seconds: number;
  owner_id: string;
  source_session_id: string | null;
  source_run_id: string | null;
  created_by: ScheduledTaskCreatedBy;
  last_run_at: string | null;
  last_run_status: RunStatus | null;
  last_run_id: string | null;
  total_runs: number;
  unread_count: number;
  created_at: string | null;
  updated_at: string | null;
}

// Create request
export interface ScheduledTaskCreate {
  execution_mode?: "conversation" | "standalone";
  target_session_id?: string | null;
  notification_policy?: "always" | "meaningful_changes";
  name: string;
  agent_id: string;
  trigger_type: TriggerType;
  trigger_config: Record<string, unknown>;
  timezone?: string;
  input_payload?: Record<string, unknown>;
  description?: string | null;
  enabled?: boolean;
  run_on_start?: boolean;
  max_retries?: number;
  timeout_seconds?: number;
  source_session_id?: string | null;
  source_run_id?: string | null;
  created_by?: ScheduledTaskCreatedBy;
}

// Update request
export interface ScheduledTaskUpdate {
  execution_mode?: "conversation" | "standalone";
  target_session_id?: string | null;
  notification_policy?: "always" | "meaningful_changes";
  name?: string;
  agent_id?: string;
  trigger_type?: TriggerType;
  trigger_config?: Record<string, unknown>;
  timezone?: string;
  input_payload?: Record<string, unknown>;
  description?: string | null;
  enabled?: boolean;
  run_on_start?: boolean;
  max_retries?: number;
  timeout_seconds?: number;
}

// Task run
export interface TaskRun {
  id: string;
  task_id: string;
  agent_id: string;
  trigger_type: string;
  status: RunStatus;
  session_id: string | null;
  trace_id: string | null;
  input_snapshot: Record<string, unknown>;
  output_result: unknown;
  error_message: string | null;
  retry_count: number;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  created_at: string | null;
}

// Paginated responses
export interface ScheduledTaskListResponse {
  items: ScheduledTask[];
  total: number;
}

export interface TaskRunListResponse {
  items: TaskRun[];
  total: number;
}

// Task session (lightweight session from scheduled task)
export interface TaskSession {
  id: string;
  name: string | null;
  agent_id: string;
  created_at: string | null;
  updated_at: string | null;
  is_active: boolean;
  metadata: Record<string, unknown>;
  unread_count: number;
}

// Paginated session list response
export interface TaskSessionListResponse {
  items: TaskSession[];
  total: number;
}
