export function updateRunSkillNamesForSlashSelection({
  currentRunSkillNames,
  availableSkillNames,
  selectedSkillName,
}: {
  currentRunSkillNames: string[] | null;
  availableSkillNames: string[];
  selectedSkillName: string;
}): string[] {
  if (!availableSkillNames.includes(selectedSkillName)) {
    return currentRunSkillNames ?? [];
  }

  if (currentRunSkillNames === null) {
    return [selectedSkillName];
  }

  const next = new Set(currentRunSkillNames);
  if (next.has(selectedSkillName)) {
    next.delete(selectedSkillName);
  } else {
    next.add(selectedSkillName);
  }
  return Array.from(next);
}
