export type PersonaPresetScope = "global" | "user";
export type PersonaPresetVisibility = "public" | "private";
export type PersonaPresetStatus = "draft" | "published" | "archived";

export interface PersonaPreset {
  id: string;
  scope: PersonaPresetScope;
  owner_user_id?: string | null;
  name: string;
  description: string;
  avatar?: string | null;
  tags: string[];
  system_prompt: string;
  skill_names: string[];
  visibility: PersonaPresetVisibility;
  status: PersonaPresetStatus;
  source_preset_id?: string | null;
  copied_from_version?: number | null;
  version: number;
  usage_count: number;
  created_by?: string | null;
  updated_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PersonaPresetCreate {
  name: string;
  description?: string;
  avatar?: string | null;
  tags?: string[];
  system_prompt: string;
  skill_names?: string[];
  scope?: PersonaPresetScope;
  visibility?: PersonaPresetVisibility;
  status?: PersonaPresetStatus;
}

export interface PersonaPresetUpdate {
  name?: string;
  description?: string;
  avatar?: string | null;
  tags?: string[];
  system_prompt?: string;
  skill_names?: string[];
  visibility?: PersonaPresetVisibility;
  status?: PersonaPresetStatus;
}

export interface PersonaPresetSnapshot {
  preset_id: string;
  name: string;
  system_prompt: string;
  skill_names: string[];
  missing_skill_names: string[];
  version: number;
  avatar?: string | null;
}

export interface PersonaPresetListResponse {
  presets: PersonaPreset[];
  total: number;
  skip: number;
  limit: number;
}

export interface PersonaPresetListParams {
  scope?: PersonaPresetScope;
  status?: PersonaPresetStatus;
  tag?: string;
  q?: string;
  skip?: number;
  limit?: number;
}
