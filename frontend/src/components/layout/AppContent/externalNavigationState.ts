import type { RevealedFileItem } from "../../../services/api";
import { getFullUrl } from "../../../services/api/config";
import type { RevealPreviewRequest } from "../../chat/ChatMessage/items/revealPreviewData";
import { getFileExtension, isImageFile } from "../../documents/utils";

export interface ExternalNavigationTargetFile {
  fileId?: string;
  fileKey?: string | null;
  fileName?: string;
  originalPath?: string | null;
  traceId?: string | null;
  source?: RevealedFileItem["source"];
}

export interface ExternalNavigationState {
  externalNavigate?: boolean;
  scrollToBottom?: boolean;
  targetFile?: ExternalNavigationTargetFile | null;
  targetPreview?: RevealPreviewRequest | null;
}

export function shouldOpenExternalNavigationPreview(input: {
  externalNavigationToken?: string | null;
  externalNavigationPreview?: RevealPreviewRequest | null;
  handledToken?: string | null;
  handledSessionId?: string | null;
  sessionId?: string | null;
}): boolean {
  const {
    externalNavigationToken,
    externalNavigationPreview,
    handledToken,
    handledSessionId,
    sessionId,
  } = input;

  if (!externalNavigationToken || !externalNavigationPreview) {
    return false;
  }

  return (
    handledToken !== externalNavigationToken || handledSessionId !== sessionId
  );
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
    !!targetFile.traceId?.trim() ||
    !!targetFile.fileName?.trim();

  return hasMatchableField ? targetFile : null;
}

export function buildExternalNavigationPreviewRequest(
  file: Pick<
    RevealedFileItem,
    | "id"
    | "file_key"
    | "file_name"
    | "file_size"
    | "url"
    | "source"
    | "original_path"
    | "project_meta"
  >,
): RevealPreviewRequest | null {
  if (file.source === "reveal_project") {
    const projectMeta = file.project_meta;
    if (!projectMeta?.files) {
      return null;
    }

    return {
      kind: "project",
      previewKey: `external-project:${file.id}`,
      project: {
        version: 2,
        name: file.file_name,
        path: file.original_path ?? undefined,
        template: projectMeta.template,
        entry: projectMeta.entry,
        fileCount:
          projectMeta.file_count ?? Object.keys(projectMeta.files).length,
        files: Object.fromEntries(
          Object.entries(projectMeta.files).map(([path, entry]) => [
            path,
            {
              ...entry,
              is_binary: entry.is_binary ?? false,
            },
          ]),
        ),
      },
    };
  }

  const filePath = file.original_path?.trim() || file.file_name;

  return {
    kind: "file",
    previewKey: `external-file:${file.id}`,
    filePath,
    s3Key: file.file_key || undefined,
    signedUrl: getFullUrl(file.url),
    fileSize: file.file_size,
  };
}

export function buildExternalNavigationStateForFile(
  file: Pick<
    RevealedFileItem,
    | "id"
    | "file_key"
    | "file_name"
    | "file_size"
    | "url"
    | "source"
    | "original_path"
    | "project_meta"
    | "trace_id"
  >,
): ExternalNavigationState {
  const filePath = file.original_path?.trim() || file.file_name;
  const isImageNavigationTarget =
    file.source !== "reveal_project" && isImageFile(getFileExtension(filePath));

  return {
    externalNavigate: true,
    targetFile: {
      fileId: file.id,
      fileKey: file.file_key,
      fileName: file.file_name,
      originalPath: file.original_path,
      source: file.source,
      ...(file.trace_id ? { traceId: file.trace_id } : {}),
    },
    targetPreview: isImageNavigationTarget
      ? null
      : buildExternalNavigationPreviewRequest(file),
  };
}

export function getExternalNavigationPreviewRequest(
  locationState: ExternalNavigationState | null | undefined,
): RevealPreviewRequest | null {
  if (locationState?.externalNavigate !== true) {
    return null;
  }

  return locationState.targetPreview ?? null;
}
