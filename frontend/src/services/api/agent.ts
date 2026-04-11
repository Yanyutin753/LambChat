/**
 * Agent API - Agent 相关
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type { AgentListResponse } from "../../types";

export const agentApi = {
  /**
   * List all agents
   */
  async list(): Promise<AgentListResponse> {
    return authFetch<AgentListResponse>(`${API_BASE}/api/agents`);
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
};
