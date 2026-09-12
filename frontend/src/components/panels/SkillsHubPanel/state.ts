export type SkillsHubTab = "skills" | "plugins";

export function resolveSkillsHubTab(
  requestedTab: SkillsHubTab | undefined,
  canReadSkills: boolean,
  canReadPlugins: boolean,
): SkillsHubTab | null {
  if (canReadSkills && canReadPlugins) {
    return requestedTab ?? "skills";
  }

  if (canReadSkills) {
    return "skills";
  }

  if (canReadPlugins) {
    return "plugins";
  }

  return null;
}
