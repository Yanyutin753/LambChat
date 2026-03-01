/**
 * Agent API - Agent 相关
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import { getAccessToken } from "./token";

export const agentApi = {
  /**
   * List all agents
   */
  async list() {
    return authFetch(`${API_BASE}/agents`);
  },

  /**
   * Stream chat endpoint URL
   */
  getStreamUrl(agentId: string) {
    return `${API_BASE}/${agentId}/stream`;
  },

  /**
   * Non-streaming chat
   */
  async chat(agentId: string, message: string, sessionId?: string) {
    return authFetch(`${API_BASE}/${agentId}/chat`, {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
    });
  },

  /**
   * 获取带认证的 Stream URL（用于 EventSource）
   */
  getAuthenticatedStreamUrl(agentId: string, sessionId?: string) {
    const token = getAccessToken();
    const params = new URLSearchParams();
    if (token) {
      params.set("token", token);
    }
    if (sessionId) {
      params.set("session_id", sessionId);
    }
    return `${API_BASE}/${agentId}/stream?${params.toString()}`;
  },
};
