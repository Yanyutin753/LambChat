import type { SkillResponse } from "../../../types";

export function buildEffectiveSkills({
  skills,
  skillsLoading,
  personaSkillNames,
  disabledSkillNames,
}: {
  skills: SkillResponse[];
  skillsLoading: boolean;
  personaSkillNames?: string[];
  disabledSkillNames?: string[];
}): SkillResponse[] {
  if (skillsLoading) return skills;

  const disabledSet = new Set(disabledSkillNames ?? []);
  const personaSet =
    personaSkillNames && personaSkillNames.length > 0
      ? new Set(personaSkillNames)
      : null;

  return skills
    .filter(
      (skill) => skill.enabled && (!personaSet || personaSet.has(skill.name)),
    )
    .map((skill) => ({
      ...skill,
      enabled: !disabledSet.has(skill.name),
    }));
}

export function countEnabledSkills(skills: SkillResponse[]): number {
  return skills.filter((skill) => skill.enabled).length;
}
