const openedProjectPreviewKeys = new Set<string>();

export function getProjectRevealAutoOpenKey(input: {
  projectPath?: string;
  projectName?: string;
}): string | null {
  return input.projectPath || input.projectName || null;
}

export function shouldAutoOpenProjectRevealPreview(input: {
  success?: boolean;
  showFullPreview?: boolean;
  hasClosedPreview?: boolean;
  isDesktop?: boolean;
  allowAutoPreview?: boolean;
  previewKey?: string | null;
}): boolean {
  const {
    success,
    showFullPreview,
    hasClosedPreview,
    isDesktop,
    allowAutoPreview,
    previewKey,
  } = input;

  if (
    !success ||
    showFullPreview ||
    hasClosedPreview ||
    !isDesktop ||
    !allowAutoPreview ||
    !previewKey
  ) {
    return false;
  }

  return !openedProjectPreviewKeys.has(previewKey);
}

export function markProjectRevealPreviewAutoOpened(
  previewKey: string | null | undefined,
): void {
  if (previewKey) {
    openedProjectPreviewKeys.add(previewKey);
  }
}

export function clearProjectRevealAutoOpenState(): void {
  openedProjectPreviewKeys.clear();
}
