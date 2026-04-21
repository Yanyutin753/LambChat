export function shouldAutoExpandProject(
  autoExpandProjectId: string | null | undefined,
  projectId: string,
): boolean {
  return autoExpandProjectId === projectId;
}

export function consumeAutoExpandProjectId(
  autoExpandProjectId: string | null | undefined,
  projectId: string,
): string | null {
  return shouldAutoExpandProject(autoExpandProjectId, projectId)
    ? null
    : autoExpandProjectId || null;
}
