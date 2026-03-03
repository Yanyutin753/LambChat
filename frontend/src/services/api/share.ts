/**
 * Share API - 会话分享管理
 */

import type {
  ShareCreate,
  ShareResponse,
  ShareListResponse,
  SharedSession,
  SharedContentResponse,
} from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export const shareApi = {
  /**
   * 创建分享
   */
  async create(data: ShareCreate): Promise<ShareResponse> {
    return authFetch<ShareResponse>(`${API_BASE}/api/share`, {
      method: "POST",
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
   * 删除分享
   */
  async delete(shareId: string): Promise<void> {
    await authFetch(`${API_BASE}/api/share/${shareId}`, {
      method: "DELETE",
    });
  },

  /**
   * 获取分享内容（公开访问）
   * 使用 skipAuth 以支持未认证访问，但如果已登录会带上 token
   */
  async getSharedContent(shareId: string): Promise<SharedContentResponse> {
    return authFetch<SharedContentResponse>(
      `${API_BASE}/api/share/public/${shareId}`,
      { skipAuth: true },
    );
  },
};
