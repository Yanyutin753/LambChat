import type { MessageAttachment } from "../../../types";
import type { FileReferenceStatus } from "./composerTypes";

export interface DraftAttachmentResource {
  referenceId: string;
  file: File;
  status: FileReferenceStatus;
  active: boolean;
  attachment?: MessageAttachment;
  error?: string;
}

export interface DraftAttachmentState {
  resources: Record<string, DraftAttachmentResource>;
  cardOnlyAttachments: MessageAttachment[];
}

export type DraftAttachmentAction =
  | { type: "insert"; resource: DraftAttachmentResource }
  | { type: "reconcile-active"; activeReferenceIds: string[] }
  | {
      type: "upload-ready";
      referenceId: string;
      attachment: MessageAttachment;
    }
  | { type: "upload-failed"; referenceId: string; error: string }
  | { type: "retry"; referenceId: string }
  | { type: "sync-card-only"; attachments: MessageAttachment[] }
  | { type: "cleanup-inactive" }
  | { type: "reset" };

export function createDraftAttachmentState(): DraftAttachmentState {
  return { resources: {}, cardOnlyAttachments: [] };
}

export function reduceDraftAttachments(
  state: DraftAttachmentState,
  action: DraftAttachmentAction,
): DraftAttachmentState {
  switch (action.type) {
    case "insert":
      return {
        ...state,
        resources: {
          ...state.resources,
          [action.resource.referenceId]: action.resource,
        },
      };
    case "reconcile-active": {
      const activeIds = new Set(action.activeReferenceIds);
      return {
        ...state,
        resources: Object.fromEntries(
          Object.entries(state.resources).map(([id, resource]) => [
            id,
            { ...resource, active: activeIds.has(id) },
          ]),
        ),
      };
    }
    case "upload-ready": {
      const resource = state.resources[action.referenceId];
      if (!resource) return state;
      return {
        ...state,
        resources: {
          ...state.resources,
          [action.referenceId]: {
            ...resource,
            status: "ready",
            attachment: action.attachment,
            error: undefined,
          },
        },
      };
    }
    case "upload-failed": {
      const resource = state.resources[action.referenceId];
      if (!resource) return state;
      return {
        ...state,
        resources: {
          ...state.resources,
          [action.referenceId]: {
            ...resource,
            status: "failed",
            error: action.error,
          },
        },
      };
    }
    case "retry": {
      const resource = state.resources[action.referenceId];
      if (!resource) return state;
      return {
        ...state,
        resources: {
          ...state.resources,
          [action.referenceId]: {
            ...resource,
            status: "uploading",
            error: undefined,
          },
        },
      };
    }
    case "sync-card-only":
      return { ...state, cardOnlyAttachments: action.attachments };
    case "cleanup-inactive":
      return {
        ...state,
        resources: Object.fromEntries(
          Object.entries(state.resources).filter(
            ([, resource]) => resource.active,
          ),
        ),
      };
    case "reset":
      return createDraftAttachmentState();
  }
}

export function selectActiveAttachments(
  state: DraftAttachmentState,
): MessageAttachment[] {
  const referenced = Object.values(state.resources)
    .filter((resource) => resource.active && resource.attachment)
    .map((resource) => resource.attachment!);
  return [...state.cardOnlyAttachments, ...referenced];
}

export function selectSubmitAttachments(
  state: DraftAttachmentState,
): MessageAttachment[] {
  const referenced = Object.values(state.resources)
    .filter(
      (resource) =>
        resource.active && resource.status === "ready" && resource.attachment,
    )
    .map((resource) => resource.attachment!);
  return [
    ...state.cardOnlyAttachments.filter(
      (attachment) => !attachment.isUploading && !attachment.uploadError,
    ),
    ...referenced,
  ];
}
