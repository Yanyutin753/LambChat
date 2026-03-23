// ============================================
// Skills Types - Simplified Architecture
// ============================================

// Skill Source Type (based on installed_from)
export type SkillSource = "builtin" | "marketplace" | "manual";

// ============================================
// User Skills Types (from /api/skills/)
// ============================================

// User skill from API list response
export interface UserSkill {
  skill_name: string;
  description: string;
  files: string[];
  enabled: boolean;
  file_count: number;
  installed_from: "manual" | "marketplace" | "builtin";
  created_at?: string;
  updated_at?: string;
}

// User skill with files list (from GET /api/skills/{name})
export interface UserSkillDetail extends UserSkill {
  files?: string[];
}

// Skill file content response
export interface SkillFileResponse {
  content: string;
}

// Skill toggle response
export interface SkillToggleResponse {
  skill_name: string;
  enabled: boolean;
  message: string;
}

// ============================================
// Frontend Skill Type (composed from API)
// ============================================

// Full skill used in frontend components
export interface SkillResponse {
  name: string;
  description: string;
  enabled: boolean;
  source: SkillSource;
  files: Record<string, string>;
  file_count: number;
  is_system: boolean;
  can_edit: boolean;
  installed_from: "manual" | "marketplace" | "builtin";
  created_at?: string;
  updated_at?: string;
}

// Skills list response
export interface SkillsResponse {
  skills: UserSkill[];
  total: number;
}

// Skill Create Request (simplified - write individual files via /files/{path})
export interface SkillCreate {
  name: string;
  description: string;
  content: string;
  enabled?: boolean;
  files?: Record<string, string>; // For multi-file support
  source?: SkillSource; // Used by form, not sent to API
}

// Skill Update Request
export interface SkillUpdate {
  description?: string;
  content?: string;
  enabled?: boolean;
}

// ============================================
// Marketplace Types (from /api/marketplace/)
// ============================================

// Marketplace skill response
export interface MarketplaceSkillResponse {
  skill_name: string;
  description: string;
  tags: string[];
  version: string;
  created_at?: string;
  updated_at?: string;
  created_by?: string;
  file_count: number;
}

// Marketplace skill files response
export interface MarketplaceSkillFilesResponse {
  files: string[];
}

// Marketplace skill file content response
export interface MarketplaceSkillFileResponse {
  content: string;
}

// Marketplace install response
export interface MarketplaceInstallResponse {
  message: string;
  skill_name: string;
  file_count: number;
}

// Marketplace update response (same as install)
export interface MarketplaceUpdateResponse extends MarketplaceInstallResponse {}

// Tags response
export interface TagsResponse {
  tags: string[];
}

// ============================================
// Admin Marketplace Types (from /api/admin/marketplace/)
// ============================================

// Admin create marketplace skill request
export interface AdminMarketplaceSkillCreate {
  skill_name: string;
  description?: string;
  tags?: string[];
  version?: string;
}

// Admin update marketplace skill request
export interface AdminMarketplaceSkillUpdate {
  description?: string;
  tags?: string[];
  version?: string;
}

// ============================================
// Legacy types for backwards compatibility
// ============================================

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
