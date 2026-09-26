/**
 * Sandbox FS API - 桌面工作区文件树的只读数据源
 *
 * 服务端 /api/sandbox/fs/* 把 fs_ls/fs_read 中继到会话绑定的本地 daemon：
 * cwd 权威在服务端（会话存储解析），前端只指定会话与相对路径。
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";

/** fs/list 条目：path 为工作区内相对路径（posix 风格）。 */
export interface SandboxFsEntry {
  path: string;
  is_dir: boolean;
}

/** daemon 文件级错误（path_not_found / permission_denied 等）也在 200 里。 */
export interface SandboxFsListResult {
  entries?: SandboxFsEntry[];
  error?: string;
}

/** fs/read 结果：utf-8 行分页或 base64 二进制（与模型侧 read_file 同源契约）。 */
export interface SandboxFsReadResult {
  encoding?: "utf-8" | "base64";
  content?: string;
  total_lines?: number | null;
  start_line?: number;
  end_line?: number;
  next_offset?: number | null;
  error?: string;
}

export const sandboxFsApi = {
  /** 列目录（懒加载源）：path 空 = 工作区根。 */
  async list(sessionId: string, path: string = ""): Promise<SandboxFsListResult> {
    const query = new URLSearchParams({ session_id: sessionId });
    if (path) {
      query.set("path", path);
    }
    return authFetch<SandboxFsListResult>(
      `${API_BASE}/api/sandbox/fs/list?${query.toString()}`,
    );
  },

  /** 读文件预览：行分页（offset 0 基；limit ≤ 2000）。 */
  async read(
    sessionId: string,
    path: string,
    offset: number = 0,
    limit: number = 500,
  ): Promise<SandboxFsReadResult> {
    const query = new URLSearchParams({
      session_id: sessionId,
      path,
      offset: String(offset),
      limit: String(limit),
    });
    return authFetch<SandboxFsReadResult>(
      `${API_BASE}/api/sandbox/fs/read?${query.toString()}`,
    );
  },
};

// ---------------------------------------------------------------------------
// 云端电脑（E2B/Daytona SDK 直连）：与本地端点同契约，供「云端电脑」视图
// ---------------------------------------------------------------------------

export interface SandboxCloudStatus {
  /** 当前云端平台（e2b/daytona/cubesandbox；沙箱未启用时 null）。 */
  platform: string | null;
  /** running | paused（上次落库值）| not_created | disabled */
  state: string;
}

/** 树数据源抽象：本地（daemon 中继）与云端（SDK 直连）共用同一前端状态机。 */
export interface WorkspaceFsSource {
  list: (sessionId: string, path: string) => Promise<SandboxFsListResult>;
  read: (
    sessionId: string,
    path: string,
    offset?: number,
    limit?: number,
  ) => Promise<SandboxFsReadResult>;
}

export const sandboxCloudFsApi: WorkspaceFsSource = {
  async list(sessionId, path = "") {
    const query = new URLSearchParams({ session_id: sessionId });
    if (path) {
      query.set("path", path);
    }
    return authFetch<SandboxFsListResult>(
      `${API_BASE}/api/sandbox/fs/cloud/list?${query.toString()}`,
    );
  },

  async read(sessionId, path, offset = 0, limit = 500) {
    const query = new URLSearchParams({
      session_id: sessionId,
      path,
      offset: String(offset),
      limit: String(limit),
    });
    return authFetch<SandboxFsReadResult>(
      `${API_BASE}/api/sandbox/fs/cloud/read?${query.toString()}`,
    );
  },
};

export const sandboxFsCloudStatusApi = {
  /** 云端电脑状态速览（零副作用，不唤醒沙箱）。 */
  async status(sessionId: string): Promise<SandboxCloudStatus> {
    const query = new URLSearchParams({ session_id: sessionId });
    return authFetch<SandboxCloudStatus>(
      `${API_BASE}/api/sandbox/fs/cloud/status?${query.toString()}`,
    );
  },
};
