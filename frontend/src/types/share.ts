import type { AgentCatalogLocale } from "./agent";
import type { SSEEventRecord } from "./session";

// ============================================
// Share Types
// ============================================

export type ShareType = "full" | "partial";
export type ShareVisibility = "public" | "authenticated";
export type ShareScope = "session" | "project";

export interface ProjectSnapshot {
  id: string;
  name: string;
  icon?: string;
}

export interface SharedSession {
  id: string;
  share_id: string;
  session_id?: string;
  session_name?: string;
  share_scope?: ShareScope;
  project_id?: string;
  project_name?: string;
  share_type: ShareType;
  run_ids?: string[];
  session_ids?: string[];
  visibility: ShareVisibility;
  created_at: string;
  allow_files: boolean;
}

export interface ShareCreate {
  session_id?: string;
  share_type: ShareType;
  run_ids?: string[];
  visibility: ShareVisibility;
  share_scope?: ShareScope;
  project_id?: string;
  session_ids?: string[];
  allow_files?: boolean;
}

export interface ShareUpdate {
  share_type?: ShareType;
  run_ids?: string[];
  session_ids?: string[];
  visibility?: ShareVisibility;
  allow_files?: boolean;
}

export interface ShareResponse {
  id: string;
  share_id: string;
  url: string;
  session_id?: string;
  share_scope?: ShareScope;
  project_id?: string;
  share_type: ShareType;
  visibility: ShareVisibility;
  run_ids?: string[];
  session_ids?: string[];
  created_at: string;
  allow_files: boolean;
}

export interface ShareListResponse {
  shares: SharedSession[];
  total: number;
}

export interface SharedContentOwner {
  username: string;
  avatar_url?: string;
}

/** 分享接口随会话下发的 agent 展示详情（与后端 _shared_agent_metadata 的 agent_meta 同构）。 */
export interface SharedAgentMeta {
  id: string;
  name?: string;
  labels?: Record<string, Pick<AgentCatalogLocale, "name">>;
  icon?: string | null;
}

export interface SharedContentResponse {
  session: {
    id: string;
    name?: string;
    agent_id: string;
    agent_meta?: SharedAgentMeta;
    model?: string;
    created_at?: string;
    updated_at?: string;
    task_status?: string | null;
    task_error?: string | null;
    completed_at?: string | null;
    persona_preset_id?: string;
    persona_preset_name?: string;
    persona_avatar?: string;
    team_id?: string;
    team_name?: string;
    team_avatar?: string;
  };
  events: SSEEventRecord[];
  owner: SharedContentOwner;
  share_type: ShareType;
  share_scope?: ShareScope;
  run_ids?: string[];
  events_limited?: boolean;
  events_limit?: number;
}

export interface SharedProjectSessionItem {
  id: string;
  agent_id?: string;
  name?: string;
  agent_meta?: SharedAgentMeta;
  model?: string;
  updated_at?: string;
  event_count?: number;
}

export interface SharedProjectContentResponse {
  share_scope: "project";
  share_type: ShareType;
  project: ProjectSnapshot;
  sessions: SharedProjectSessionItem[];
  owner: SharedContentOwner;
  visibility: ShareVisibility;
  events_limited?: boolean;
  events_limit?: number;
  sessions_total: number;
  has_more?: boolean;
}

/** 统一公开读返回：会话内容或项目 manifest，按 share_scope 区分。 */
export type SharedContent =
  | SharedContentResponse
  | SharedProjectContentResponse;
