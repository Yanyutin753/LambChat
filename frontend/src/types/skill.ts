// ============================================
// Skills Types
// ============================================

// Skill Source Type
export type SkillSource = "builtin" | "github" | "manual";

// Skill Base
export interface SkillBase {
  name: string;
  description: string;
  content: string;
  enabled: boolean;
  files?: Record<string, string>;
}

// Skill Response (from API)
export interface SkillResponse extends SkillBase {
  source: SkillSource;
  github_url?: string;
  version?: string;
  is_system: boolean;
  can_edit: boolean;
  created_at?: string;
  updated_at?: string;
}

// Skills List Response
export interface SkillsResponse {
  skills: SkillResponse[];
  total: number;
}

// Skill Create Request
export interface SkillCreate {
  name: string;
  description: string;
  content: string;
  enabled?: boolean;
  source?: SkillSource;
  github_url?: string;
  version?: string;
  files?: Record<string, string>;
}

// Skill Update Request
export interface SkillUpdate {
  name?: string;
  description?: string;
  content?: string;
  enabled?: boolean;
  version?: string;
  files?: Record<string, string>;
  is_system?: boolean;
}

// Skill Toggle Response
export interface SkillToggleResponse {
  skill: SkillResponse;
  message: string;
}

// Skill Import Request
export interface SkillImportRequest {
  skills: Record<string, Record<string, unknown>>;
  overwrite?: boolean;
}

// Skill Import Response
export interface SkillImportResponse {
  message: string;
  imported_count: number;
  skipped_count: number;
  errors: string[];
}

// Skill Export Response
export interface SkillExportResponse {
  skills: Record<string, Record<string, unknown>>;
}

// Skill Move Request
export interface SkillMoveRequest {
  target_user_id?: string;
}

// Skill Move Response
export interface SkillMoveResponse {
  skill: SkillResponse;
  message: string;
  from_type: string;
  to_type: string;
}

// GitHub Skill Preview
export interface GitHubSkillPreview {
  name: string;
  description: string;
  path: string;
}

// GitHub Preview Response
export interface GitHubPreviewResponse {
  repo_url: string;
  skills: GitHubSkillPreview[];
}

// GitHub Install Request
export interface GitHubInstallRequest {
  repo_url: string;
  branch?: string;
  skill_names?: string[];
  as_system?: boolean;
}

// Legacy types for backwards compatibility
export interface SkillMetadata {
  name: string;
  description: string;
  path: string;
  source: "user" | "project";
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface SkillContent {
  metadata: SkillMetadata;
  content: string;
}

export interface SkillListResponse {
  skills: SkillMetadata[];
  total: number;
}

export interface SkillStats {
  total_skills: number;
  enabled_skills: number;
  disabled_skills: number;
}
