export function resolvePersonaEnabledSkills(
  personaPresetId: string | null | undefined,
  personaSkillNames: string[] | undefined,
): string[] | undefined {
  if (!personaPresetId) return undefined;
  if (!personaSkillNames || personaSkillNames.length === 0) return undefined;
  return personaSkillNames ?? [];
}
