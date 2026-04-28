export type AssistantScope = "public" | "private";
export type AssistantListScope = "public" | "mine" | "all";

export interface Assistant {
  assistant_id: string;
  name: string;
  description: string;
  system_prompt: string;
  scope: AssistantScope;
  created_by?: string | null;
  is_active: boolean;
  tags: string[];
  category?: string;
  avatar_url?: string | null;
  cloned_from_assistant_id?: string | null;
  version: string;
  bound_skill_names: string[];
  default_model?: string | null;
  default_agent_options: Record<string, unknown>;
  default_disabled_tools: string[];
  default_disabled_skills: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AssistantCreate {
  name: string;
  description?: string;
  system_prompt: string;
  tags?: string[];
  category?: string;
  avatar_url?: string | null;
  version?: string;
}

export interface AssistantUpdate {
  name?: string;
  description?: string;
  system_prompt?: string;
  tags?: string[];
  category?: string;
  avatar_url?: string | null;
  is_active?: boolean;
  version?: string;
}

export interface AssistantSelection {
  assistantId: string;
  assistantName: string;
  assistantPromptSnapshot: string;
  avatarUrl?: string | null;
}

export const EMPTY_ASSISTANT_SELECTION: AssistantSelection = {
  assistantId: "",
  assistantName: "",
  assistantPromptSnapshot: "",
  avatarUrl: null,
};
