import type { RevealedFileItem } from "../../../services/api";

export interface ExternalNavigationTargetFile {
  fileId?: string;
  fileKey?: string | null;
  fileName?: string;
  originalPath?: string | null;
  source?: RevealedFileItem["source"];
}

export interface ExternalNavigationState {
  externalNavigate?: boolean;
  scrollToBottom?: boolean;
  targetFile?: ExternalNavigationTargetFile | null;
}

export function shouldResetExternalNavigateFlag(
  locationState: ExternalNavigationState | null | undefined,
): boolean {
  return locationState?.externalNavigate === true;
}

export function shouldScrollToBottomAfterExternalNavigation(
  locationState: ExternalNavigationState | null | undefined,
): boolean {
  return (
    locationState?.externalNavigate === true &&
    locationState?.scrollToBottom === true
  );
}

export function getExternalNavigationTargetFile(
  locationState: ExternalNavigationState | null | undefined,
): ExternalNavigationTargetFile | null {
  if (locationState?.externalNavigate !== true) {
    return null;
  }

  const targetFile = locationState.targetFile;
  if (!targetFile) {
    return null;
  }

  const hasMatchableField =
    !!targetFile.fileId ||
    !!targetFile.fileKey?.trim() ||
    !!targetFile.originalPath?.trim() ||
    !!targetFile.fileName?.trim();

  return hasMatchableField ? targetFile : null;
}
