import { useCallback, type FormEvent } from "react";
import type { MessageAttachment } from "../../types";
import type { ChatInputProps } from "./chatInputTypes";
import { filterSendableAttachments } from "./attachmentValidation";
import {
  moveSubmittedDraftToOutbox,
  restoreRejectedDraft,
  mergeComposerDrafts,
  type DraftStateBindings,
} from "./acceptedDraftCleanup";
import type {
  LongTextPastePayload,
  RichChatComposerHandle,
} from "./richComposer/RichChatComposer";
import { updateChatDraft } from "./chatDraftStore";

interface PreparedSubmission {
  message: string;
  attachments?: MessageAttachment[];
}

interface UseAcceptedDraftSubmissionOptions
  extends Omit<DraftStateBindings, "composer" | "longTextResources"> {
  enabled: boolean;
  draftKey?: string;
  input: string;
  enabledSkillNames: string[] | null;
  runModes?: Array<"auto" | "goal">;
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
  draftKey,
  enabled,
  input,
  enabledSkillNames,
  runModes,
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
      const runOptions: {
        enabledSkills?: string[];
        runModes?: Array<"auto" | "goal">;
      } = {};
      if (enabledSkillNames) runOptions.enabledSkills = enabledSkillNames;
      if (runModes && runModes.length > 0) runOptions.runModes = runModes;
      onSend(
        prepared.message,
        agentOptionValues,
        prepared.attachments,
        Object.keys(runOptions).length > 0 ? runOptions : undefined,
        {
          onAccepted: () => undefined,
          onRejected: () => {
            if (draftKey && composerRef.current !== composer) {
              updateChatDraft(draftKey, (draft) => ({
                composer: draft.composer
                  ? mergeComposerDrafts(submittedDraft.composer, draft.composer)
                  : submittedDraft.composer,
                attachments: [
                  ...submittedDraft.attachments.filter(
                    (item) =>
                      !draft.attachments.some(
                        (current) => current.id === item.id,
                      ),
                  ),
                  ...draft.attachments,
                ],
              }));
            } else {
              restoreRejectedDraft(submittedDraft, draftState);
            }
          },
        },
      );
    },
    [
      activeReferenceIds,
      agentOptionValues,
      composerRef,
      draftKey,
      enabled,
      enabledSkillNames,
      input,
      inputValueRef,
      longTextResourcesRef,
      onSend,
      prepareSubmit,
      pushHistory,
      runModes,
      setActiveReferenceIds,
      setAttachments,
      setComposerExpanded,
      setInput,
      setRunEnabledSkillNames,
      visibleAttachments,
    ],
  );
}
