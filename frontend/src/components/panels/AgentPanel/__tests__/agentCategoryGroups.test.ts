import assert from "node:assert/strict";
import test from "node:test";
import { groupAgentsByPluginCategory } from "../agentCategoryGroups";
import type { CoreAgentCategoryContribution } from "../../../../extensions";
import type { AgentInfo } from "../../../../types";

const categories: CoreAgentCategoryContribution[] = [
  {
    id: "agent_team:team-builder",
    pluginId: "agent_team",
    label: "agentTeam.category.teamBuilder",
    description: "Team builder agents",
    icon: "Users",
    order: 20,
    area: "agent_category",
  },
];

test("groups agents by plugin-declared category", () => {
  const agents: AgentInfo[] = [
    {
      id: "search",
      name: "Search",
      description: "Core search agent",
      version: "1.0.0",
    },
    {
      id: "team",
      name: "Team",
      description: "Team agent",
      version: "1.0.0",
      category: "agent_team:team-builder",
    },
  ];

  const groups = groupAgentsByPluginCategory(agents, categories);

  assert.deepEqual(
    groups.map((group) => ({ id: group.id, agents: group.agents.map((agent) => agent.id) })),
    [
      { id: "core", agents: ["search"] },
      { id: "agent_team:team-builder", agents: ["team"] },
    ],
  );
});

test("hides plugin-owned agents when disabled plugin category is absent", () => {
  const groups = groupAgentsByPluginCategory(
    [
      {
        id: "team",
        name: "Team",
        description: "Team agent",
        version: "1.0.0",
        category: "agent_team:team-builder",
      },
    ],
    [],
  );

  assert.equal(groups.length, 0);
});

test("keeps unknown non-plugin categories in the core group", () => {
  const groups = groupAgentsByPluginCategory(
    [
      {
        id: "custom",
        name: "Custom",
        description: "Custom agent",
        version: "1.0.0",
        category: "custom",
      },
    ],
    [],
  );

  assert.equal(groups.length, 1);
  assert.equal(groups[0].id, "core");
  assert.equal(groups[0].agents[0].id, "custom");
});
