export type SkillsHubTab = "skills" | "marketplace" | "plugins";

export function resolveSkillsHubTab(
  requestedTab: SkillsHubTab | undefined,
  canReadSkills: boolean,
  canReadMarketplace: boolean,
): SkillsHubTab | null {
  if (canReadSkills && canReadMarketplace) {
    return requestedTab ?? "skills";
  }

  if (canReadSkills) {
    return "skills";
  }

  if (canReadMarketplace) {
    return requestedTab === "plugins" ? "plugins" : "marketplace";
  }

  return null;
}
