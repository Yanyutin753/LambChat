import assert from "node:assert/strict";
import test from "node:test";
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

  assert.deepEqual(entry, {
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

  assert.equal(skillToExtensionMarketplaceEntry(marketplaceSkill({ extension })), extension);
});

test("extension marketplace item keeps the legacy skill payload", () => {
  const skill = marketplaceSkill({ skill_name: "writer", extension_id: "skill:writer" });
  const item = skillToExtensionMarketplaceItem(skill);

  assert.equal(item.skill, skill);
  assert.equal(item.extension.id, "skill:writer");
  assert.equal(item.extension.name, "writer");
});

test("fallback skill extension entries do not share compatibility objects", () => {
  const first = skillToExtensionMarketplaceEntry(
    marketplaceSkill({ skill_name: "planner" }),
  );
  const second = skillToExtensionMarketplaceEntry(
    marketplaceSkill({ skill_name: "writer" }),
  );

  assert.notEqual(first.compatibility, second.compatibility);
});

test("marketplace skill lists can be projected to extension lists", () => {
  const items = marketplaceSkillsToExtensionItems([
    marketplaceSkill({ skill_name: "planner" }),
    marketplaceSkill({ skill_name: "writer", tags: ["writing"] }),
  ]);

  assert.deepEqual(
    items.map((item) => [item.extension.id, item.extension.type]),
    [
      ["skill:planner", "skill"],
      ["skill:writer", "skill"],
    ],
  );
  assert.equal(items[1].skill?.tags[0], "writing");
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

  assert.deepEqual(
    items.map((item) => [item.extension.type, item.extension.capabilities[0], item.skill]),
    [
      ["plugin", "plugin", undefined],
      ["mcp", "mcp", undefined],
    ],
  );
});
