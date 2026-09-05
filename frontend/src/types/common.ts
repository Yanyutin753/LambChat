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
  release_notes?: string;
  release_assets?: ReleaseAsset[];
}

export interface ReleaseAsset {
  name: string;
  url: string;
  size?: number;
  content_type: string;
}

export interface UpdateState {
  available: boolean;
  version: string | null;
  releaseNotes: string | null;
  releaseUrl: string | null;
  releaseAssets: ReleaseAsset[];
  publishedAt: string | null;
  downloading: boolean;
  progress: number;
  contentLength: number;
  downloaded: number;
  /** 后台静默下载已完成，待用户确认重启安装 */
  readyToInstall: boolean;
  error: string | null;
}
