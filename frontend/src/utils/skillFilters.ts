import type { SkillResponse, MarketplaceSkillResponse } from "../types";

type TaggedSkill = Pick<SkillResponse, "name" | "description" | "tags">;
type TaggedMarketplaceSkill = Pick<
  MarketplaceSkillResponse,
  "skill_name" | "description" | "tags"
>;

export function sanitizeSkillName(name: string): string {
  return (
    name
      .replace(
        /[^\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af\-.]/g,
        "-",
      )
      .replace(/-{2,}/g, "-")
      .replace(/^-+|-+$/g, "") || "unnamed-skill"
  );
}

export function normalizeSkillTags(tags: string[]): string[] {
  return Array.from(new Set(tags.map((tag) => tag.trim()).filter(Boolean)));
}

export function collectSkillTags(
  skills: Array<Pick<SkillResponse, "tags">>,
): string[] {
  return normalizeSkillTags(skills.flatMap((skill) => skill.tags || [])).sort(
    (left, right) => left.localeCompare(right),
  );
}

export function skillMatchesQuery(skill: TaggedSkill, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return true;
  }

  return (
    skill.name.toLowerCase().includes(normalized) ||
    skill.description.toLowerCase().includes(normalized) ||
    (skill.tags || []).some((tag) => tag.toLowerCase().includes(normalized))
  );
}

export function marketplaceSkillMatchesQuery(
  skill: TaggedMarketplaceSkill,
  query: string,
): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return true;
  }

  return (
    skill.skill_name.toLowerCase().includes(normalized) ||
    skill.description.toLowerCase().includes(normalized) ||
    (skill.tags || []).some((tag) => tag.toLowerCase().includes(normalized))
  );
}
