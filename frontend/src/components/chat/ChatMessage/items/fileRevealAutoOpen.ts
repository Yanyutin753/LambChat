const openedPreviewKeys = new Set<string>();

export function getFileRevealAutoOpenKey(input: {
  s3Key?: string;
  s3Url?: string;
  filePath?: string;
}): string | null {
  return input.s3Key || input.s3Url || input.filePath || null;
}

export function shouldAutoOpenFileRevealPreview(input: {
  success?: boolean;
  filePath?: string;
  isImage?: boolean;
  showPreview?: boolean;
  hasClosedPreview?: boolean;
  isDesktop?: boolean;
  allowAutoPreview?: boolean;
  previewKey?: string | null;
}): boolean {
  const {
    success,
    filePath,
    isImage,
    showPreview,
    hasClosedPreview,
    isDesktop,
    allowAutoPreview,
    previewKey,
  } = input;

  if (
    !success ||
    !filePath ||
    isImage ||
    showPreview ||
    hasClosedPreview ||
    !isDesktop ||
    !allowAutoPreview ||
    !previewKey
  ) {
    return false;
  }

  return !openedPreviewKeys.has(previewKey);
}

export function markFileRevealPreviewAutoOpened(
  previewKey: string | null | undefined,
): void {
  if (previewKey) {
    openedPreviewKeys.add(previewKey);
  }
}

export function clearFileRevealAutoOpenState(): void {
  openedPreviewKeys.clear();
}
