/**
 * Share API - 会话/项目分享管理
 */

import type {
  ShareCreate,
  ShareUpdate,
  ShareResponse,
  ShareListResponse,
  SharedSession,
  SharedContent,
  SharedContentResponse,
} from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import { getValidAccessToken } from "./tokenManager";

export const shareApi = {
  /**
   * 创建分享（支持会话维度与项目维度）
   */
  async create(data: ShareCreate): Promise<ShareResponse> {
    return authFetch<ShareResponse>(`${API_BASE}/api/share`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * 更新已有分享
   */
  async update(shareId: string, data: ShareUpdate): Promise<ShareResponse> {
    return authFetch<ShareResponse>(`${API_BASE}/api/share/${shareId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  /**
   * 获取我的分享列表
   */
  async list(skip = 0, limit = 50): Promise<ShareListResponse> {
    return authFetch<ShareListResponse>(
      `${API_BASE}/api/share?skip=${skip}&limit=${limit}`,
    );
  },

  /**
   * 获取指定会话的分享列表
   */
  async listBySession(sessionId: string): Promise<SharedSession[]> {
    return authFetch<SharedSession[]>(
      `${API_BASE}/api/share/session/${sessionId}`,
    );
  },

  /**
   * 获取指定项目的分享列表
   */
  async listByProject(projectId: string): Promise<SharedSession[]> {
    return authFetch<SharedSession[]>(
      `${API_BASE}/api/share/project/${projectId}`,
    );
  },

  /**
   * 删除分享
   */
  async delete(shareId: string): Promise<void> {
    await authFetch(`${API_BASE}/api/share/${shareId}`, {
      method: "DELETE",
    });
  },

  /**
   * 获取分享内容（公开访问，统一入口）
   *
   * 按 share_scope 返回会话内容或项目 manifest；调用方按 share_scope 分流。
   * 使用 skipAuth 以支持未认证访问，但如果已登录会带上 token。
   */
  async getSharedContent(
    shareId: string,
    opts?: { sessionSkip?: number; sessionLimit?: number; eventLimit?: number },
  ): Promise<SharedContent> {
    // 手动带上 token（如果已登录），同时 skipAuth 避免未登录时 401 跳转登录页
    const token = await getValidAccessToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const params = new URLSearchParams();
    if (opts?.sessionSkip) params.set("session_skip", String(opts.sessionSkip));
    if (opts?.sessionLimit)
      params.set("session_limit", String(opts.sessionLimit));
    if (opts?.eventLimit) params.set("event_limit", String(opts.eventLimit));
    const query = params.toString() ? `?${params.toString()}` : "";
    return authFetch<SharedContent>(
      `${API_BASE}/api/share/public/${shareId}${query}`,
      { skipAuth: true, headers },
    );
  },

  /**
   * 获取项目分享中的某个子会话事件（公开访问）
   */
  async getSessionContentInProject(
    shareId: string,
    sessionId: string,
    eventLimit?: number,
  ): Promise<SharedContentResponse> {
    const token = await getValidAccessToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const query = eventLimit != null ? `?event_limit=${eventLimit}` : "";
    return authFetch<SharedContentResponse>(
      `${API_BASE}/api/share/public/${shareId}/sessions/${sessionId}${query}`,
      { skipAuth: true, headers },
    );
  },
};
