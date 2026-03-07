import type { SSEEventRecord } from "./session";

// ============================================
// Share Types
// ============================================

export type ShareType = "full" | "partial";
export type ShareVisibility = "public" | "authenticated";

export interface SharedSession {
  id: string;
  share_id: string;
  session_id: string;
  session_name?: string;
  share_type: ShareType;
  run_ids?: string[];
  visibility: ShareVisibility;
  created_at: string;
}

export interface ShareCreate {
  session_id: string;
  share_type: ShareType;
  run_ids?: string[];
  visibility: ShareVisibility;
}

export interface ShareResponse {
  id: string;
  share_id: string;
  url: string;
  session_id: string;
  share_type: ShareType;
  visibility: ShareVisibility;
  run_ids?: string[];
  created_at: string;
}

export interface ShareListResponse {
  shares: SharedSession[];
  total: number;
}

export interface SharedContentOwner {
  username: string;
  avatar_url?: string;
}

export interface SharedContentResponse {
  session: {
    id: string;
    name?: string;
    agent_id: string;
    created_at?: string;
  };
  events: SSEEventRecord[];
  owner: SharedContentOwner;
  share_type: ShareType;
  run_ids?: string[];
}
