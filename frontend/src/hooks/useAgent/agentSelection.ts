import type { AgentInfo } from "../../types";

export function resolveAvailableAgentId(
  currentAgentId: string,
  preferredDefaultAgentId: string | undefined,
  agents: AgentInfo[],
): string {
  const availableIds = new Set(agents.map((agent) => agent.id));

  if (currentAgentId && availableIds.has(currentAgentId)) {
    return currentAgentId;
  }

  if (preferredDefaultAgentId && availableIds.has(preferredDefaultAgentId)) {
    return preferredDefaultAgentId;
  }

  return agents[0]?.id || "";
}

export function resolvePersonaAgentId(
  currentAgentId: string,
  preferredDefaultAgentId: string | undefined,
  agents: AgentInfo[],
  excludedAgentIds: readonly string[] = [],
): string {
  const excludedIds = new Set(excludedAgentIds.filter(Boolean));

  if (currentAgentId && !excludedIds.has(currentAgentId)) {
    return resolveAvailableAgentId(
      currentAgentId,
      preferredDefaultAgentId,
      agents,
    );
  }

  const personaAgents = agents.filter((agent) => !excludedIds.has(agent.id));
  return resolveAvailableAgentId("", preferredDefaultAgentId, personaAgents);
}
