/**
 * Sandbox API - 本地沙箱在线状态与配对凭据
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export interface SandboxStatus {
  online: boolean;
  client_id?: string;
  daemon_version?: string | null;
}

export interface PatCreateResult {
  token: string;
  pat_id: string;
}

/** 桌面壳配对时创建的 PAT 名称（用户可在 PAT 列表中识别/吊销）。 */
export const DESKTOP_SHELL_PAT_NAME = "lambchat-desktop-shell";

export const sandboxApi = {
  /**
   * 查询当前用户的本地沙箱 daemon 在线状态（PAT/JWT 双通道）
   */
  async getStatus(): Promise<SandboxStatus> {
    return authFetch<SandboxStatus>(`${API_BASE}/api/sandbox/status`);
  },

  /**
   * 创建 sandbox 作用域的个人访问令牌（需当前登录 JWT）
   */
  async createPat(
    name: string = DESKTOP_SHELL_PAT_NAME,
    scopes: string[] = ["sandbox:execute"],
  ): Promise<PatCreateResult> {
    return authFetch<PatCreateResult>(`${API_BASE}/api/auth/pat`, {
      method: "POST",
      body: JSON.stringify({ name, scopes }),
    });
  },
};
