import { useEffect, useState } from "react";
import { agentApi } from "../../services/api/agent";
import type { AgentInfo } from "../../types";

export function useAgentCatalog() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  useEffect(() => {
    let active = true;
    agentApi.list()
      .then((data) => {
        if (active) setAgents(data.agents || []);
      })
      .catch(() => { /* Keep recorded names or built-in translations on failure. */ });
    return () => {
      active = false;
    };
  }, []);
  return agents;
}
