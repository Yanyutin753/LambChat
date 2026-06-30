import type {
  ExtensionMarketplaceEntry,
  ExtensionMarketplaceItem,
  MarketplaceSkillResponse,
} from "../types";

export function skillToExtensionMarketplaceEntry(
  skill: MarketplaceSkillResponse,
): ExtensionMarketplaceEntry {
  if (skill.extension) {
    return skill.extension;
  }

  return {
    id: skill.extension_id ?? `skill:${skill.skill_name}`,
    type: "skill",
    name: skill.skill_name,
    version: skill.version || "1.0.0",
    publisher: skill.created_by_username ?? skill.created_by ?? "unknown",
    description: skill.description ?? "",
    tags: skill.tags ?? [],
    capabilities: ["skill"],
    permissions: [],
    install_state: "not_installed",
    enabled: skill.is_active,
    compatibility: {},
    legacy: {
      kind: "marketplace_skill",
      skill_name: skill.skill_name,
      file_count: skill.file_count,
    },
  };
}

export function skillToExtensionMarketplaceItem(
  skill: MarketplaceSkillResponse,
): ExtensionMarketplaceItem {
  return {
    extension: skillToExtensionMarketplaceEntry(skill),
    skill,
  };
}

export function marketplaceSkillsToExtensionItems(
  skills: readonly MarketplaceSkillResponse[],
): ExtensionMarketplaceItem[] {
  return skills.map(skillToExtensionMarketplaceItem);
}
