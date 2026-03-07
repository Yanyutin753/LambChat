// ============================================
// Version Types
// ============================================

export interface VersionInfo {
  app_version: string;
  git_tag?: string;
  commit_hash?: string;
  build_time?: string;
  latest_version?: string;
  release_url?: string;
  github_url?: string;
  has_update?: boolean;
  published_at?: string;
  last_checked?: string;
}
