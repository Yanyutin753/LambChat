/**
 * Sandbox API - 本地沙箱在线状态与配对凭据
 */

import i18n from "i18next";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import { parseErrorDetail, translateApiError } from "../../utils/backendErrors";

export interface SandboxStatus {
  online: boolean;
  client_id?: string;
  daemon_version?: string | null;
  /** daemon 上报平台（linux/darwin/win32，M4 T3；旧 daemon 为 null） */
  daemon_platform?: string | null;
}

export interface PatCreateResult {
  token: string;
  pat_id: string;
}

/** 桌面壳配对时创建的 PAT 名称（用户可在 PAT 列表中识别/吊销）。 */
export const DESKTOP_SHELL_PAT_NAME = "lambchat-desktop-shell";

/**
 * 直连 fetch 的统一错误处理：按 `{detail: {code, message, args}}` 契约解析并
 * 抛带 `.status` / `.code` 的 Error（与 authFetch 的错误形态一致）。
 */
async function throwResponseError(resp: Response): Promise<never> {
  const errorData = await resp.json().catch(() => ({}));
  const { code, message, args } = parseErrorDetail(errorData);
  const errorMessage = message || `Request failed: ${resp.statusText}`;
  const error = new Error(
    translateApiError(code, errorMessage, args, i18n.t.bind(i18n)),
  ) as Error & { status?: number; code?: string; args?: Record<string, unknown> };
  error.status = resp.status;
  error.code = code;
  error.args = args;
  throw error;
}

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

  /**
   * 配对专用登录：直连 fetch，**无副作用**——不 setTokens、不派发 auth:login
   * 事件（用别的账号配对不能切换壳会话身份），token 只返回给调用方闭包使用。
   */
  async pairingLogin(credentials: {
    username: string;
    password: string;
  }): Promise<string> {
    const resp = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept-Language": i18n.language || "en",
      },
      body: JSON.stringify(credentials),
    });
    if (!resp.ok) {
      await throwResponseError(resp);
    }
    const body = (await resp.json().catch(() => null)) as {
      access_token?: string;
    } | null;
    if (!body?.access_token) {
      throw new Error("pairingLogin: login response missing access_token");
    }
    return body.access_token;
  },

  /**
   * 用**配对账号**的 JWT 铸 PAT（不是壳会话 token）：配对表单专用，
   * 直连 fetch 显式携带 Bearer。
   */
  async createPairingPat(
    accessToken: string,
    name: string = DESKTOP_SHELL_PAT_NAME,
  ): Promise<PatCreateResult> {
    const resp = await fetch(`${API_BASE}/api/auth/pat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept-Language": i18n.language || "en",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ name, scopes: ["sandbox:execute"] }),
    });
    if (!resp.ok) {
      await throwResponseError(resp);
    }
    return (await resp.json()) as PatCreateResult;
  },

  /**
   * PAT 自撤销（桌面壳"取消配对"）：Bearer PAT 删自己，服务端按 token 哈希吊销。
   */
  async revokePairingPat(pat: string): Promise<void> {
    const resp = await fetch(`${API_BASE}/api/auth/pat/current`, {
      method: "DELETE",
      headers: {
        "Accept-Language": i18n.language || "en",
        Authorization: `Bearer ${pat}`,
      },
    });
    if (!resp.ok) {
      await throwResponseError(resp);
    }
  },
};
