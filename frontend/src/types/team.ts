// frontend/src/types/team.ts
import type { PersonaStarterPrompt } from "./personaPreset";

export interface TeamMember {
  member_id: string;
  persona_preset_id: string;
  model_id?: string | null;
  role_name: string;
  role_avatar?: string | null;
  role_tags: string[];
  role_instructions: string;
  position: number;
  enabled: boolean;
}

export interface Team {
  id: string;
  owner_user_id: string;
  name: string;
  description: string;
  avatar?: string | null;
  tags: string[];
  members: TeamMember[];
  default_member_id?: string | null;
  team_instructions: string;
  run_in_sandbox: boolean;
  starter_prompts?: PersonaStarterPrompt[];
  visibility: "private";
  is_favorite?: boolean;
  is_pinned?: boolean;
  compatibility_warnings?: string[];
  last_used_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TeamCreateRequest {
  name: string;
  description?: string;
  avatar?: string | null;
  tags?: string[];
  members?: TeamMemberCreateRequest[];
  default_member_id?: string | null;
  team_instructions?: string;
  run_in_sandbox?: boolean;
  starter_prompts?: PersonaStarterPrompt[];
}

export interface TeamMemberCreateRequest {
  member_id?: string;
  persona_preset_id: string;
  model_id?: string | null;
  role_name?: string;
  role_avatar?: string | null;
  role_tags?: string[];
  role_instructions?: string;
  position?: number;
  enabled?: boolean;
}

export interface TeamUpdateRequest {
  name?: string;
  description?: string;
  avatar?: string | null;
  tags?: string[];
  members?: TeamMemberCreateRequest[];
  default_member_id?: string | null;
  team_instructions?: string;
  run_in_sandbox?: boolean;
  starter_prompts?: PersonaStarterPrompt[];
}

export interface TeamPreferenceUpdate {
  is_favorite?: boolean;
  is_pinned?: boolean;
}

export interface TeamListResponse {
  teams: Team[];
  total: number;
  skip: number;
  limit: number;
}

export interface TeamListParams {
  skip?: number;
  limit?: number;
  q?: string;
  tag?: string;
  favorite?: boolean;
  pinned?: boolean;
}
