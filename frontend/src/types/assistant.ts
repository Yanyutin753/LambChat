import type { Project } from "./index";
import type { PersonaStarterPrompt } from "./personaPreset";

export interface AssistantConfiguration {
  kind?: "assistant" | "group" | "chief";
  member_ids?: string[];
  leader_id?: string | null;
  name: string;
  description?: string;
  avatar?: string | null;
  starter_prompts?: PersonaStarterPrompt[];
  instructions: string;
  model_id: string | null;
  persona_preset_id: string | null;
  team_id: string | null;
  project_id: string | null;
  memory_mode: "private" | "project";
  sandbox: "local" | "cloud" | null;
  workspace: Project["workspace"];
}

export type AssistantStatus = "active" | "paused" | "archived";

export interface AssistantActivity {
  state:
    | "waiting_human"
    | "running"
    | "starting"
    | "pending"
    | "queued"
    | "recovering"
    | "cancelling"
    | "completed"
    | "failed"
    | "cancelled"
    | "expired";
  session_id: string;
  preview?: string | null;
  updated_at: string;
  unread_count: number;
}

export interface Assistant extends AssistantConfiguration {
  activity?: AssistantActivity | null;
  context_kind?: "conversation" | "task";
  context_session_id?: string | null;
  context_task_id?: string | null;
  id: string;
  user_id: string;
  session_id: string;
  revision: number;
  status: AssistantStatus;
  created_at: string;
  updated_at: string;
}

export interface AssistantTask {
  id: string;
  assistant_id?: string | null;
  source_session_id?: string | null;
  source_assistant_id?: string | null;
  description: string;
  session_id: string | null;
  run_id: string;
  state: string;
  admission_state: string;
  authorization?: { kind: "user" | "conversation" | "rule" };
  environment?: "local" | "cloud" | null;
  notification?: {
    recorded_at: string;
    status: string;
    accepted_transports: string[];
  } | null;
  execution_mode: string;
  created_at: string;
  timeout_seconds: number | null;
  started_at: string;
  deadline_at: string | null;
  authorized_turns: number;
  recovery_attempts: number;
  review_revision: number;
  error_code: string | null;
}

export function assistantConfiguration(
  value?: Assistant,
): AssistantConfiguration {
  return {
    kind: value?.kind ?? "assistant",
    member_ids: value?.member_ids ?? [],
    leader_id: value?.leader_id ?? null,
    name: value?.name ?? "",
    description: value?.description ?? "",
    avatar: value?.avatar ?? null,
    starter_prompts: value?.starter_prompts ?? [],
    instructions: value?.instructions ?? "",
    model_id: value?.model_id ?? null,
    persona_preset_id: value?.persona_preset_id ?? null,
    team_id: value?.team_id ?? null,
    memory_mode: value?.memory_mode ?? "private",
    project_id: value?.project_id ?? null,
    sandbox: value?.sandbox ?? null,
    workspace: value?.workspace ?? null,
  };
}

export interface AssistantDiscussion {
  session_id: string;
  channel_type: string;
  chat_id: string;
  created_at: string | null;
  available: boolean;
}

export type AssistantRuleMode = "off" | "observe" | "auto";
export interface AssistantRuleCreate {
  name: string;
  instructions: string;
  mode: AssistantRuleMode;
  interval_seconds: number;
  event_task_id?: string | null;
  timeout_seconds: number;
  max_wakeups: number;
}
export interface AssistantRule {
  id: string;
  name: string;
  enabled: boolean;
  status: string;
  input_payload: {
    message: string;
    assistant_rule: Omit<
      AssistantRuleCreate,
      "name" | "instructions" | "interval_seconds"
    > & { assistant_id: string };
  };
  trigger_type: string;
  trigger_config: { seconds?: number };
  assistant_rule_wakeups?: number;
  assistant_rule_last_claim?: {
    run_id: string;
    mode: AssistantRuleMode;
    status: string;
    at: string;
  };
}

export function assistantActivityPath(assistant: Assistant) {
  const base = `/assistants/${encodeURIComponent(assistant.id)}`;
  return assistant.activity?.session_id
    ? `${base}/chat/${encodeURIComponent(assistant.activity.session_id)}`
    : base;
}
