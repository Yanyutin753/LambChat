/**
 * Agent 列表加载与默认 agent 选择逻辑（从 useAgent 提取）
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentInfo, AgentListResponse } from "../../types";
import { authenticatedRequest } from "../../services/api/authenticatedRequest";
import { API_BASE } from "../../services/api/config";
import { resolveAvailableAgentId } from "./agentSelection";

async function fetchAgentsData(): Promise<{
  agents: AgentInfo[];
  allowedModelIds: string[] | null;
  defaultAgent: string | undefined;
}> {
  const response = await authenticatedRequest(`${API_BASE}/api/agents`, {
    headers: {
      "Content-Type": "application/json",
    },
  });
  if (!response.ok) throw new Error("Failed to fetch agents");
  const data: AgentListResponse = await response.json();
  return {
    agents: data.agents || [],
    allowedModelIds: data.allowed_model_ids ?? null,
    defaultAgent: data.default_agent,
  };
}

export function useAgentList(hasActiveMessages: () => boolean) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [currentAgent, setCurrentAgent] = useState<string>("");
  const [agentsLoading, setAgentsLoading] = useState(false);
  const [allowedModelIds, setAllowedModelIds] = useState<string[] | null>(null);

  // Ref for currentAgent to avoid dependency changes triggering refetch
  const currentAgentRef = useRef(currentAgent);
  useEffect(() => {
    currentAgentRef.current = currentAgent;
  }, [currentAgent]);

  // Fetch available agents
  const fetchAgents = useCallback(async () => {
    setAgentsLoading(true);
    try {
      const {
        agents: availableAgents,
        allowedModelIds: modelIds,
        defaultAgent,
      } = await fetchAgentsData();
      setAgents(availableAgents);
      setAllowedModelIds(modelIds);
      const nextAgentId = resolveAvailableAgentId(
        currentAgentRef.current,
        defaultAgent,
        availableAgents,
      );
      if (nextAgentId !== currentAgentRef.current) {
        currentAgentRef.current = nextAgentId;
        setCurrentAgent(nextAgentId);
      }
    } catch (err) {
      console.error("Failed to fetch agents:", err);
    } finally {
      setAgentsLoading(false);
    }
  }, []); // No dependencies - uses ref instead

  // Load agents on mount
  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  // Refresh agents when page becomes visible (e.g., switching back to /chat tab)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        fetchAgents();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [fetchAgents]);

  // Listen for agent preference updates to refresh agents list and apply new default
  useEffect(() => {
    const handleAgentPreferenceUpdated = async () => {
      // Fetch fresh agents data
      setAgentsLoading(true);
      try {
        const {
          agents: availableAgents,
          allowedModelIds: modelIds,
          defaultAgent,
        } = await fetchAgentsData();

        // Update agents list
        setAgents(availableAgents);
        setAllowedModelIds(modelIds);

        // Apply the new default agent if user doesn't have an active session
        // (i.e., no current messages means it's a good time to switch)
        const hasActiveSession = hasActiveMessages();
        const nextAgentId = resolveAvailableAgentId(
          hasActiveSession ? currentAgentRef.current : "",
          defaultAgent,
          availableAgents,
        );
        if (nextAgentId !== currentAgentRef.current) {
          currentAgentRef.current = nextAgentId;
          setCurrentAgent(nextAgentId);
        }
      } catch (err) {
        console.error("Failed to fetch agents after preference update:", err);
      } finally {
        setAgentsLoading(false);
      }
    };

    window.addEventListener(
      "agent-preference-updated",
      handleAgentPreferenceUpdated,
    );
    return () => {
      window.removeEventListener(
        "agent-preference-updated",
        handleAgentPreferenceUpdated,
      );
    };
  }, [hasActiveMessages]);

  return {
    agents,
    currentAgent,
    setCurrentAgent,
    agentsLoading,
    allowedModelIds,
    currentAgentRef,
    fetchAgents,
  };
}
