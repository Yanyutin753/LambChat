import {
  marketplaceSkillsToExtensionItems,
  skillToExtensionMarketplaceEntry,
  skillToExtensionMarketplaceItem,
} from "../extensionMarketplace";
import type {
  ExtensionMarketplaceEntry,
  ExtensionMarketplaceItem,
  MarketplaceSkillResponse,
} from "../../types";

function marketplaceSkill(
  overrides: Partial<MarketplaceSkillResponse> = {},
): MarketplaceSkillResponse {
  return {
    skill_name: "planner",
    description: "Plan work",
    tags: ["planning"],
    version: "1.2.3",
    created_by: "user-1",
    created_by_username: "tester",
    is_active: true,
    is_owner: false,
    file_count: 3,
    ...overrides,
  };
}

test("skill marketplace responses adapt to extension marketplace entries", () => {
  const entry = skillToExtensionMarketplaceEntry(marketplaceSkill());

  expect(entry).toEqual({
    id: "skill:planner",
    type: "skill",
    name: "planner",
    version: "1.2.3",
    publisher: "tester",
    description: "Plan work",
    tags: ["planning"],
    capabilities: ["skill"],
    permissions: [],
    install_state: "not_installed",
    enabled: true,
    compatibility: {},
    legacy: {
      kind: "marketplace_skill",
      skill_name: "planner",
      file_count: 3,
    },
  });
});

test("backend-provided extension entries are preserved", () => {
  const extension: ExtensionMarketplaceEntry = {
    id: "skill:planner",
    type: "skill",
    name: "Planner",
    version: "2.0.0",
    publisher: "remote",
    description: "Remote entry",
    tags: ["remote"],
    capabilities: ["skill"],
    permissions: [],
    install_state: "not_installed",
    enabled: false,
    compatibility: {},
    legacy: { skill_name: "planner" },
  };

  expect(skillToExtensionMarketplaceEntry(marketplaceSkill({ extension }))).toBe(extension);
});

test("extension marketplace item keeps the legacy skill payload", () => {
  const skill = marketplaceSkill({ skill_name: "writer", extension_id: "skill:writer" });
  const item = skillToExtensionMarketplaceItem(skill);

  expect(item.skill).toBe(skill);
  expect(item.extension.id).toBe("skill:writer");
  expect(item.extension.name).toBe("writer");
});

test("fallback skill extension entries do not share compatibility objects", () => {
  const first = skillToExtensionMarketplaceEntry(
    marketplaceSkill({ skill_name: "planner" }),
  );
  const second = skillToExtensionMarketplaceEntry(
    marketplaceSkill({ skill_name: "writer" }),
  );

  expect(first.compatibility).not.toBe(second.compatibility);
});

test("marketplace skill lists can be projected to extension lists", () => {
  const items = marketplaceSkillsToExtensionItems([
    marketplaceSkill({ skill_name: "planner" }),
    marketplaceSkill({ skill_name: "writer", tags: ["writing"] }),
  ]);

  expect(items.map((item) => [item.extension.id, item.extension.type])).toEqual([
      ["skill:planner", "skill"],
      ["skill:writer", "skill"],
    ]);
  expect(items[1].skill?.tags[0]).toBe("writing");
});

test("extension marketplace items can model plugin and mcp entries", () => {
  const items: ExtensionMarketplaceItem[] = [
    {
      extension: {
        id: "plugin:feedback",
        type: "plugin",
        name: "Feedback",
        version: "1.0.0",
        publisher: "LambChat",
        description: "Collect ratings",
        tags: ["feedback"],
        capabilities: ["plugin"],
        permissions: ["feedback:read"],
        install_state: "installed",
        enabled: true,
        compatibility: { api_version: "v1" },
      },
    },
    {
      extension: {
        id: "mcp:github",
        type: "mcp",
        name: "GitHub MCP",
        version: "1.0.0",
        publisher: "LambChat",
        description: "GitHub tool profile",
        tags: ["mcp"],
        capabilities: ["mcp"],
        permissions: ["mcp:read"],
        install_state: "not_installed",
        enabled: false,
        compatibility: {},
      },
    },
  ];

  expect(items.map((item) => [item.extension.type, item.extension.capabilities[0], item.skill])).toEqual([
      ["plugin", "plugin", undefined],
      ["mcp", "mcp", undefined],
    ]);
});
