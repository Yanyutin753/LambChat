import type { CoreAgentCategoryContribution } from "../../../extensions";
import type { AgentConfig, AgentInfo } from "../../../types";

export interface AgentCategoryGroup<TAgent extends AgentConfig | AgentInfo> {
  id: string;
  label: string;
  description: string;
  icon: string;
  order: number;
  agents: TAgent[];
  pluginOwned: boolean;
}

const CORE_AGENT_GROUP_ID = "core";

function isPluginScopedCategory(categoryId: string): boolean {
  return categoryId.includes(":");
}

export function groupAgentsByPluginCategory<TAgent extends AgentConfig | AgentInfo>(
  agents: readonly TAgent[],
  categories: readonly CoreAgentCategoryContribution[],
): AgentCategoryGroup<TAgent>[] {
  const categoryMap = new Map(categories.map((category) => [category.id, category]));
  const groups = new Map<string, AgentCategoryGroup<TAgent>>();

  const ensureGroup = (agent: TAgent): AgentCategoryGroup<TAgent> | null => {
    const categoryId = agent.category || CORE_AGENT_GROUP_ID;
    const declared = categoryId === CORE_AGENT_GROUP_ID ? undefined : categoryMap.get(categoryId);
    if (!declared && isPluginScopedCategory(categoryId)) {
      return null;
    }
    const groupId = declared?.id ?? CORE_AGENT_GROUP_ID;
    const existing = groups.get(groupId);
    if (existing) return existing;

    const group: AgentCategoryGroup<TAgent> = {
      id: groupId,
      label: declared?.label ?? "agentConfig.coreAgents",
      description: declared?.description ?? "",
      icon: declared?.icon ?? "Bot",
      order: declared?.order ?? 0,
      agents: [],
      pluginOwned: Boolean(declared),
    };
    groups.set(groupId, group);
    return group;
  };

  for (const agent of agents) {
    ensureGroup(agent)?.agents.push(agent);
  }

  return [...groups.values()].sort((left, right) => {
    if (left.id === CORE_AGENT_GROUP_ID && right.id !== CORE_AGENT_GROUP_ID) return -1;
    if (right.id === CORE_AGENT_GROUP_ID && left.id !== CORE_AGENT_GROUP_ID) return 1;
    return left.order - right.order || left.label.localeCompare(right.label);
  });
}
