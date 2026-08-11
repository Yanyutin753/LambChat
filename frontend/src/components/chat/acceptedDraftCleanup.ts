import type { MessageAttachment } from "../../types";
import { projectComposerSnapshot } from "./richComposer/composerProjection";
import type { ComposerSnapshot } from "./richComposer/composerTypes";
import type {
  LongTextPastePayload,
  RichChatComposerHandle,
} from "./richComposer/RichChatComposer";

interface DraftStateBindings {
  composer: RichChatComposerHandle | null;
  inputValueRef: { current: string };
  longTextResources: Map<string, LongTextPastePayload>;
  setInput: (value: string) => void;
  setActiveReferenceIds: (value: string[]) => void;
  setRunEnabledSkillNames: (value: string[] | null) => void;
  setAttachments: (
    update: (current: MessageAttachment[]) => MessageAttachment[],
  ) => void;
  setComposerExpanded: (value: boolean) => void;
}

export interface SubmittedDraftOutbox {
  composer: ComposerSnapshot;
  attachments: MessageAttachment[];
  longTextResources: Map<string, LongTextPastePayload>;
}

function attachmentSignature(attachment: MessageAttachment): string {
  return JSON.stringify([
    attachment.id,
    attachment.key,
    attachment.name,
    attachment.type,
    attachment.mimeType,
    attachment.size,
    attachment.url ?? null,
    attachment.uploadProgress ?? null,
    attachment.isUploading ?? null,
    attachment.localOriginalText ?? null,
    attachment.fromLongText ?? null,
    attachment.composerReferenceId ?? null,
    attachment.uploadError ?? null,
  ]);
}

function removeOutboxAttachments(
  current: readonly MessageAttachment[],
  submitted: readonly MessageAttachment[],
): MessageAttachment[] {
  const signatures = new Map(
    submitted.map((attachment) => [
      attachment.id,
      attachmentSignature(attachment),
    ]),
  );
  return current.filter(
    (attachment) =>
      signatures.get(attachment.id) !== attachmentSignature(attachment),
  );
}

function prependMissingOutboxAttachments(
  submitted: readonly MessageAttachment[],
  current: readonly MessageAttachment[],
): MessageAttachment[] {
  const currentIds = new Set(current.map((attachment) => attachment.id));
  return [
    ...submitted.filter((attachment) => !currentIds.has(attachment.id)),
    ...current,
  ];
}

export function mergeComposerDrafts(
  submitted: ComposerSnapshot,
  pending: ComposerSnapshot,
): ComposerSnapshot {
  if (projectComposerSnapshot(pending).isEmpty) return submitted;
  if (projectComposerSnapshot(submitted).isEmpty) return pending;

  const submittedRoot = submitted.editorState.root;
  const pendingRoot = pending.editorState.root;
  if (!submittedRoot) return pending;
  if (!pendingRoot) return submitted;

  return {
    version: 1,
    editorState: {
      ...submitted.editorState,
      root: {
        ...submittedRoot,
        children: [
          ...(submittedRoot.children ?? []),
          ...(pendingRoot.children ?? []),
        ],
      },
    },
  };
}

export function moveSubmittedDraftToOutbox(
  composer: ComposerSnapshot,
  attachments: readonly MessageAttachment[],
  activeReferenceIds: readonly string[],
  state: DraftStateBindings,
): SubmittedDraftOutbox {
  const submittedAttachments = attachments.map((attachment) => ({
    ...attachment,
  }));
  const submittedResources = new Map<string, LongTextPastePayload>();
  for (const referenceId of activeReferenceIds) {
    const resource = state.longTextResources.get(referenceId);
    if (resource) submittedResources.set(referenceId, resource);
    state.longTextResources.delete(referenceId);
  }

  state.composer?.setPlainText("");
  state.composer?.focus({ atEnd: true });
  state.inputValueRef.current = "";
  state.setInput("");
  state.setActiveReferenceIds([]);
  state.setRunEnabledSkillNames(null);
  state.setAttachments((current) =>
    removeOutboxAttachments(current, submittedAttachments),
  );
  state.setComposerExpanded(false);

  return {
    composer,
    attachments: submittedAttachments,
    longTextResources: submittedResources,
  };
}

export function restoreRejectedDraft(
  outbox: SubmittedDraftOutbox,
  state: DraftStateBindings,
): void {
  const pending = state.composer?.getSnapshot();
  const merged = pending
    ? mergeComposerDrafts(outbox.composer, pending)
    : outbox.composer;
  const projection = projectComposerSnapshot(merged);

  for (const [referenceId, resource] of outbox.longTextResources) {
    if (!state.longTextResources.has(referenceId)) {
      state.longTextResources.set(referenceId, resource);
    }
  }
  state.composer?.restoreSnapshot(merged);
  state.inputValueRef.current = projection.message;
  state.setInput(projection.message);
  state.setActiveReferenceIds(projection.activeReferenceIds);
  state.setRunEnabledSkillNames(
    projection.enabledSkills.length > 0 ? projection.enabledSkills : null,
  );
  state.setAttachments((current) =>
    prependMissingOutboxAttachments(outbox.attachments, current),
  );
}
