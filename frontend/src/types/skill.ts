// ============================================
// Skills Types - Simplified Architecture
// ============================================

// Skill Source Type (based on installed_from)
export type SkillSource = "marketplace" | "manual";

// ============================================
// User Skills Types (from /api/skills/)
// ============================================

// User skill from API list response
export interface UserSkill {
  skill_name: string;
  description: string;
  tags: string[];
  files: string[];
  enabled: boolean;
  file_count: number;
  installed_from: "manual" | "marketplace";
  published_marketplace_name?: string;
  created_at?: string;
  updated_at?: string;
  is_published: boolean;
  marketplace_is_active: boolean;
}

// User skill with files list (from GET /api/skills/{name})
export interface UserSkillDetail {
  files?: string[];
  enabled?: boolean;
  skill_name?: string;
  description?: string;
  tags?: string[];
  is_published?: boolean;
  marketplace_is_active?: boolean;
}

// Skill file content response
export interface SkillFileResponse {
  content: string;
  is_binary?: boolean;
  url?: string;
  mime_type?: string;
  size?: number;
}

// Binary file info stored alongside content in SkillResponse
export interface BinaryFileInfo {
  url: string;
  mime_type: string;
  size: number;
}

// Skill toggle response
export interface SkillToggleResponse {
  skill_name: string;
  enabled: boolean;
  message: string;
}

// Publish to marketplace request
export interface PublishToMarketplaceRequest {
  skill_name?: string;
  description?: string;
  tags?: string[];
  version?: string;
}

// ============================================
// Frontend Skill Type (composed from API)
// ============================================

// Full skill used in frontend components
export interface SkillResponse {
  name: string;
  description: string;
  tags: string[];
  enabled: boolean;
  source: SkillSource;
  content?: string; // Main SKILL.md content
  files: Record<string, string>;
  filePaths?: string[]; // file path list without content (for lazy loading)
  binaryFiles?: Record<string, BinaryFileInfo>; // binary file path -> metadata
  file_count: number;
  installed_from: "manual" | "marketplace";
  published_marketplace_name?: string;
  created_at?: string;
  updated_at?: string;
  is_published: boolean;
  marketplace_is_active: boolean;
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
  tags: string[];
  content: string;
  enabled?: boolean;
  files?: Record<string, string>; // For multi-file support
  source?: SkillSource; // Used by form, not sent to API
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
  created_by_username?: string;
  is_active: boolean;
  is_owner: boolean;
  file_count: number;
}

// Direct create in marketplace request
export interface MarketplaceCreateRequest {
  skill_name: string;
  description?: string;
  tags?: string[];
  version?: string;
  files: Record<string, string>;
}

// Marketplace skill files response
export interface MarketplaceSkillFilesResponse {
  files: string[];
}

// Marketplace skill file content response
export interface MarketplaceSkillFileResponse {
  content: string;
  is_binary?: boolean;
  url?: string;
  mime_type?: string;
  size?: number;
}

// Marketplace install response
export interface MarketplaceInstallResponse {
  message: string;
  skill_name: string;
  file_count: number;
}

// Marketplace update response (same as install)
export type MarketplaceUpdateResponse = MarketplaceInstallResponse;

// Tags response
export interface TagsResponse {
  tags: string[];
}
