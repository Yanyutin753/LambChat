import { useCallback, type FormEvent } from "react";
import type { MessageAttachment } from "../../types";
import type { ChatInputProps } from "./chatInputTypes";
import { filterSendableAttachments } from "./attachmentValidation";
import {
  moveSubmittedDraftToOutbox,
  restoreRejectedDraft,
  type DraftStateBindings,
} from "./acceptedDraftCleanup";
import type {
  LongTextPastePayload,
  RichChatComposerHandle,
} from "./richComposer/RichChatComposer";

interface PreparedSubmission {
  message: string;
  attachments?: MessageAttachment[];
}

interface UseAcceptedDraftSubmissionOptions
  extends Omit<DraftStateBindings, "composer" | "longTextResources"> {
  enabled: boolean;
  input: string;
  enabledSkillNames: string[] | null;
  composerRef: { current: RichChatComposerHandle | null };
  longTextResourcesRef: { current: Map<string, LongTextPastePayload> };
  visibleAttachments: MessageAttachment[];
  activeReferenceIds: string[];
  agentOptionValues: Record<string, boolean | string | number>;
  prepareSubmit: (
    message: string,
    attachments: MessageAttachment[],
  ) => PreparedSubmission;
  pushHistory: (value: string) => void;
  onSend: ChatInputProps["onSend"];
}

export function useAcceptedDraftSubmission({
  enabled,
  input,
  enabledSkillNames,
  composerRef,
  inputValueRef,
  longTextResourcesRef,
  visibleAttachments,
  activeReferenceIds,
  agentOptionValues,
  prepareSubmit,
  pushHistory,
  onSend,
  setInput,
  setActiveReferenceIds,
  setRunEnabledSkillNames,
  setAttachments,
  setComposerExpanded,
}: UseAcceptedDraftSubmissionOptions) {
  return useCallback(
    (event: FormEvent) => {
      event.preventDefault();
      if (!enabled) return;

      const composer = composerRef.current;
      if (!composer) return;
      const historyEntry = input.trim();
      const sendableAttachments = filterSendableAttachments(visibleAttachments);
      const prepared = prepareSubmit(historyEntry, sendableAttachments);
      const draftState: DraftStateBindings = {
        composer,
        inputValueRef,
        longTextResources: longTextResourcesRef.current,
        setInput,
        setActiveReferenceIds,
        setRunEnabledSkillNames,
        setAttachments,
        setComposerExpanded,
      };
      const submittedDraft = moveSubmittedDraftToOutbox(
        composer.getSnapshot(),
        sendableAttachments,
        activeReferenceIds,
        draftState,
      );
      if (historyEntry) pushHistory(historyEntry);
      onSend(
        prepared.message,
        agentOptionValues,
        prepared.attachments,
        enabledSkillNames ? { enabledSkills: enabledSkillNames } : undefined,
        {
          onAccepted: () => undefined,
          onRejected: () => restoreRejectedDraft(submittedDraft, draftState),
        },
      );
    },
    [
      activeReferenceIds,
      agentOptionValues,
      composerRef,
      enabled,
      enabledSkillNames,
      input,
      inputValueRef,
      longTextResourcesRef,
      onSend,
      prepareSubmit,
      pushHistory,
      setActiveReferenceIds,
      setAttachments,
      setComposerExpanded,
      setInput,
      setRunEnabledSkillNames,
      visibleAttachments,
    ],
  );
}
