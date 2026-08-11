import type { MessageAttachment } from "../../types";
import type {
  LongTextPastePayload,
  RichChatComposerHandle,
} from "./richComposer/RichChatComposer";
import type {
  ComposerSnapshot,
  SerializedComposerNode,
} from "./richComposer/composerTypes";

export interface SubmittedDraftSnapshot {
  composer: ComposerSnapshot | null;
  attachments: ReadonlyMap<string, string>;
  references: ReadonlyMap<string, string>;
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

function collectReferenceSignatures(
  node: SerializedComposerNode | undefined,
  wanted: ReadonlySet<string>,
  references: Map<string, string>,
): void {
  if (!node) return;
  if (node.referenceId && wanted.has(node.referenceId)) {
    references.set(node.referenceId, JSON.stringify(node));
  }
  for (const child of node.children ?? []) {
    collectReferenceSignatures(child, wanted, references);
  }
}

export function captureSubmittedDraft(
  composer: ComposerSnapshot | null,
  attachments: readonly MessageAttachment[],
  activeReferenceIds: readonly string[],
): SubmittedDraftSnapshot {
  const wantedReferences = new Set(activeReferenceIds);
  const references = new Map<string, string>();
  collectReferenceSignatures(
    composer?.editorState.root,
    wantedReferences,
    references,
  );
  return {
    composer,
    attachments: new Map(
      attachments.map((attachment) => [
        attachment.id,
        attachmentSignature(attachment),
      ]),
    ),
    references,
  };
}

export function composerMatchesSubmission(
  submitted: SubmittedDraftSnapshot,
  current: ComposerSnapshot | null,
): boolean {
  return JSON.stringify(current) === JSON.stringify(submitted.composer);
}

export function getUnchangedSubmittedReferenceIds(
  submitted: SubmittedDraftSnapshot,
  current: ComposerSnapshot | null,
): string[] {
  const currentReferences = new Map<string, string>();
  collectReferenceSignatures(
    current?.editorState.root,
    new Set(submitted.references.keys()),
    currentReferences,
  );
  return [...submitted.references].flatMap(([referenceId, signature]) =>
    currentReferences.get(referenceId) === signature ? [referenceId] : [],
  );
}

export function removeUnchangedSubmittedAttachments(
  current: readonly MessageAttachment[],
  submitted: SubmittedDraftSnapshot,
): MessageAttachment[] {
  return current.filter((attachment) => {
    const submittedSignature = submitted.attachments.get(attachment.id);
    return (
      submittedSignature === undefined ||
      submittedSignature !== attachmentSignature(attachment)
    );
  });
}

export function applyAcceptedDraftCleanup(
  submitted: SubmittedDraftSnapshot,
  state: {
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
  },
): void {
  const currentSnapshot = state.composer?.getSnapshot() ?? null;
  if (composerMatchesSubmission(submitted, currentSnapshot)) {
    state.setInput("");
    state.inputValueRef.current = "";
    state.composer?.setPlainText("");
    state.setActiveReferenceIds([]);
    state.longTextResources.clear();
    state.setRunEnabledSkillNames(null);
  } else {
    for (const referenceId of getUnchangedSubmittedReferenceIds(
      submitted,
      currentSnapshot,
    )) {
      state.composer?.removeFileReference(referenceId);
      state.longTextResources.delete(referenceId);
    }
  }
  state.setAttachments((current) =>
    removeUnchangedSubmittedAttachments(current, submitted),
  );
  state.setComposerExpanded(false);
}
