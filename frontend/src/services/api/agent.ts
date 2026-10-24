/**
 * Agent API - Agent 相关
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import { getAccessToken } from "./token";
import type { AgentListResponse } from "../../types";

const AGENT_LIST_CACHE_TTL_MS = 10_000;
let agentListCache: {
  data?: AgentListResponse;
  expiresAt: number;
  authScope: string | null;
  promise?: Promise<AgentListResponse>;
} | null = null;

function getCachedAgentList(url: string): Promise<AgentListResponse> {
  const now = Date.now();
  const authScope = getAccessToken();
  if (
    agentListCache?.data &&
    agentListCache.expiresAt > now &&
    agentListCache.authScope === authScope
  ) {
    return Promise.resolve(agentListCache.data);
  }
  if (agentListCache?.promise && agentListCache.authScope === authScope) {
    return agentListCache.promise;
  }

  const promise = authFetch<AgentListResponse>(url)
    .then((data) => {
      agentListCache = {
        data,
        expiresAt: Date.now() + AGENT_LIST_CACHE_TTL_MS,
        authScope,
      };
      return data;
    })
    .catch((error) => {
      agentListCache = null;
      throw error;
    });

  agentListCache = {
    promise,
    expiresAt: now + AGENT_LIST_CACHE_TTL_MS,
    authScope,
  };
  return promise;
}

export const agentApi = {
  /**
   * List all agents
   */
  async list(): Promise<AgentListResponse> {
    return getCachedAgentList(`${API_BASE}/api/agents`);
  },
};
