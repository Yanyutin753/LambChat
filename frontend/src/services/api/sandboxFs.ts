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
