import {
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
  memo,
  lazy,
  Suspense,
} from "react";
import toast from "react-hot-toast";
import { Ban, Maximize2, Minimize2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "../../i18n";
import { ImageViewer } from "../common";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { ContactAdminDialog } from "../common/ContactAdminDialog";
import { useFileUpload } from "../../hooks/useFileUpload";
import { useMentionState } from "../../hooks/useMentionState";
import { useMentionSearch } from "../../hooks/useMentionSearch";
import { resolveAgentDisplayName } from "../agent/agentCatalog";
import { useTeamMentionSearch } from "../../hooks/useTeamMentionSearch";
import { useInputHistory } from "../../hooks/useInputHistory";
import { useLongTextConversion } from "../../hooks/useLongTextConversion";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import { isSendEnterKey } from "../../hooks/sendModifier";
import { useAuth } from "../../hooks/useAuth";
import { MentionPopup } from "./MentionPopup";
import { TeamMentionPopup } from "./TeamMentionPopup";
import { ActiveGoalBar } from "./ActiveGoalBar";
import { ChatInputToolbar } from "./ChatInputToolbar";
import { ChatInputSelectors } from "./ChatInputSelectors";
import { ChatInputHelpMenu } from "./ChatInputHelpMenu";
import { ChatInputAttachments } from "./ChatInputAttachments";
import { ChatInputDragOverlay } from "./ChatInputDragOverlay";
import { resolveThinkingPresentation } from "./chatInputThinking";
import { FILE_CATEGORY_PERMISSIONS } from "./chatInputConstants";
import { getMentionPopupFixedPlacement } from "./chatInputViewport";
import {
  getMatchingSlashDropdownItems,
  type ChatInputSlashCommand,
} from "./chatInputSlashCommands";
import {
  consumePendingSelectionActionPrompt,
  SELECTION_ACTION_EVENT,
  type SelectionActionEventDetail,
} from "../common/selectionActionPopover";
import type { ChatInputProps } from "./chatInputTypes";
import type { FeaturePanel } from "../selectors/FeatureMenu";
import type { MessageAttachment, PersonaPreset } from "../../types";
import type { Team } from "../../types/team";
import type {
  LongTextPastePayload,
  RichChatComposerChange,
  RichChatComposerHandle,
} from "./richComposer/RichChatComposer";
import { buildLongTextClientMeta } from "./longTextConversion";
import { getComposerCaretBoundary } from "./chatInputCaret";
import type { ComposerArrowDirection } from "./richComposer/ArrowKeyPlugin";
import { selectVisibleDraftAttachments } from "./acceptedDraftCleanup";
import { useAcceptedDraftSubmission } from "./useAcceptedDraftSubmission";
const RichChatComposer = lazy(async () => {
  const module = await import("./richComposer/RichChatComposer");
  return { default: module.RichChatComposer };
});
export type { ChatInputProps } from "./chatInputTypes";
export const ChatInput = memo(function ChatInput({
  onSend,
  onStop,
  isLoading,
  disabled,
  canSend = true,
  tools = [],
  onToggleTool,
  onToggleCategory,
  onToggleAll,
  toolsLoading: _toolsLoading,
  enabledToolsCount = 0,
  totalToolsCount = 0,
  skills = [],
  onToggleSkill,
  onToggleSkillCategory,
  onToggleAllSkills,
  skillsLoading: _skillsLoading,
  pendingSkillNames = [],
  skillsMutating = false,
  enabledSkillsCount = 0,
  totalSkillsCount = 0,
  enableSkills = true,
  personaPresets = [],
  personaPresetsTotal,
  personaPresetsPage,
  onPersonaPresetsPageChange,
  onPersonaPresetsSearchChange,
  onPersonaPresetsTagChange,
  selectedPersonaPresetId,
  selectedPersonaName,
  personaSkillsControlled = false,
  personaPresetsLoading = false,
  personaPresetsMutating = false,
  onUsePersonaPreset,
  onCopyPersonaPreset,
  onClearPersonaPreset,
  canManagePersonaPresets = false,
  agentOptions,
  agentOptionValues = {},
  onToggleAgentOption,
  agents = [],
  currentAgent,
  onSelectAgent,
  selectedTeamId,
  onSelectTeam,
  onOpenTeamBuilder,
  attachments: externalAttachments,
  onAttachmentsChange: externalOnAttachmentsChange,
  onMentionQueryChange,
  pendingInput,
  onPendingInputConsumed,
  className,
  activeGoal,
  onClearActiveGoal,
  goalLabel,
  goalDurationLabel,
  goalClearLabel,
  showHelpMenu,
  helpMenuClassName,
  autoModeEnabled = false,
  goalModeEnabled = false,
  onToggleAutoMode,
  onToggleGoalMode,
}: ChatInputProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const inputValueRef = useRef("");
  const composerRef = useRef<RichChatComposerHandle>(null);
  const [activeReferenceIds, setActiveReferenceIds] = useState<string[]>([]);
  const longTextResourcesRef = useRef(new Map<string, LongTextPastePayload>());
  // Consume external pendingInput: fill textarea and focus
  useEffect(() => {
    if (pendingInput) {
      setInput(pendingInput);
      inputValueRef.current = pendingInput;
      composerRef.current?.setPlainText(pendingInput);
      onPendingInputConsumed?.();
      requestAnimationFrame(() => {
        composerRef.current?.focus({ atEnd: true });
      });
    }
  }, [pendingInput, onPendingInputConsumed]);

  const [activePanel, setActivePanel] = useState<FeaturePanel>(null);
  const [runEnabledSkillNames, setRunEnabledSkillNames] = useState<
    string[] | null
  >(null);
  const [internalAttachments, setInternalAttachments] = useState<
    MessageAttachment[]
  >([]);
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [stopConfirmOpen, setStopConfirmOpen] = useState(false);
  const [contactAdminOpen, setContactAdminOpen] = useState(false);
  const [composerExpanded, setComposerExpanded] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const [cursorPosition, setCursorPosition] = useState(0);
  const [mentionPopupPlacement, setMentionPopupPlacement] =
    useState<ReturnType<typeof getMentionPopupFixedPlacement>>(null);
  const { hasPermission } = useAuth();

  const uploadCategories = (
    Object.keys(FILE_CATEGORY_PERMISSIONS) as Array<
      keyof typeof FILE_CATEGORY_PERMISSIONS
    >
  ).filter((cat) => hasPermission(FILE_CATEGORY_PERMISSIONS[cat]));

  const attachments = externalAttachments ?? internalAttachments;
  const setAttachments = externalOnAttachmentsChange ?? setInternalAttachments;

  const { uploadFiles, uploadFile, uploadLimits, validateCount, cancelUpload } =
    useFileUpload({
      attachments,
      onAttachmentsChange: setAttachments,
    });

  const { pushHistory, navigateUp, navigateDown, isBrowsing } =
    useInputHistory();
  const scheduleTextareaResize = useCallback(() => undefined, []);
  const showExpandButton = input.length > 120 || input.includes("\n");
  const setComposerPlainText = useCallback((value: string) => {
    inputValueRef.current = value;
    setInput(value);
    composerRef.current?.setPlainText(value);
  }, []);
  useBodyScrollLock(composerExpanded);

  const { restoreLongTextAttachment, prepareSubmit } = useLongTextConversion({
    setInput: setComposerPlainText,
    setAttachments,
    uploadFiles,
    validateCount,
    scheduleTextareaResize,
    expanded: composerExpanded,
  });

  const mentionMode = currentAgent === "team" ? "team" : "persona";
  const mentionEnabled =
    mentionMode === "team" ? !!onSelectTeam : !!onUsePersonaPreset;

  const {
    mention,
    moveHighlight: moveMentionHighlight,
    setHighlightedIndex: setMentionHighlight,
    setResultCount: setMentionResultCount,
    resetMention,
    dismissMention,
  } = useMentionState(input, cursorPosition, mentionEnabled);

  const mentionSearch = useMentionSearch(
    mention.query,
    mention.isActive && mentionMode === "persona",
  );
  const teamMentionSearch = useTeamMentionSearch(
    mention.query,
    mention.isActive && mentionMode === "team",
  );

  useEffect(() => {
    if (mention.isActive) {
      setMentionResultCount(
        mentionMode === "team"
          ? teamMentionSearch.teams.length
          : mentionSearch.presets.length,
      );
    }
  }, [
    mention.isActive,
    mentionMode,
    mentionSearch.presets.length,
    teamMentionSearch.teams.length,
    setMentionResultCount,
  ]);

  useEffect(() => {
    if (!onMentionQueryChange) return;
    onMentionQueryChange(mention.isActive ? mention.query : null);
  }, [mention.isActive, mention.query, onMentionQueryChange]);

  useEffect(() => {
    if (!onMentionQueryChange || !selectedPersonaPresetId || !mention.isActive)
      return;
    const before = input.substring(0, mention.atIndex);
    const after = input.substring(mention.atIndex + mention.query.length + 1);
    setComposerPlainText(before + after);
    setCursorPosition(before.length || 0);
    requestAnimationFrame(() => {
      composerRef.current?.focus({ atEnd: true });
    });
    resetMention();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires only on preset selection
  }, [selectedPersonaPresetId, setComposerPlainText]);

  useEffect(() => {
    if (!onMentionQueryChange || !selectedTeamId || !mention.isActive) return;
    const before = input.substring(0, mention.atIndex);
    const after = input.substring(mention.atIndex + mention.query.length + 1);
    setComposerPlainText(before + after);
    setCursorPosition(before.length || 0);
    requestAnimationFrame(() => {
      composerRef.current?.focus({ atEnd: true });
    });
    resetMention();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires only on team selection
  }, [selectedTeamId, setComposerPlainText]);

  useEffect(() => {
    const applySelectionActionPrompt = (prompt: string) => {
      const separator = inputValueRef.current.trim() ? "\n\n" : "";
      composerRef.current?.focus({ atEnd: true });
      composerRef.current?.insertText(`${separator}${prompt}`);
    };

    const pendingPrompt = consumePendingSelectionActionPrompt();
    if (pendingPrompt) {
      applySelectionActionPrompt(pendingPrompt);
    }

    const handleSelectionAction = (event: Event) => {
      const detail = (event as CustomEvent<SelectionActionEventDetail>).detail;
      if (!detail?.prompt) return;
      applySelectionActionPrompt(detail.prompt);
    };

    window.addEventListener(SELECTION_ACTION_EVENT, handleSelectionAction);
    return () => {
      window.removeEventListener(SELECTION_ACTION_EVENT, handleSelectionAction);
    };
  }, []);

  // Ctrl+T / Cmd+T -> open team picker
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isMac =
        typeof navigator !== "undefined" &&
        navigator.platform.toUpperCase().indexOf("MAC") >= 0;
      const modifier = isMac ? e.metaKey : e.ctrlKey;
      if (modifier && e.key === "t") {
        e.preventDefault();
        if (currentAgent === "team" && onSelectTeam) {
          setActivePanel((prev) => (prev === "team" ? null : "team"));
        }
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [currentAgent, onSelectTeam]);

  useEffect(() => {
    if (!composerExpanded) return;
    const collapseOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setComposerExpanded(false);
    };
    document.addEventListener("keydown", collapseOnEscape);
    return () => document.removeEventListener("keydown", collapseOnEscape);
  }, [composerExpanded]);

  useEffect(() => {
    if (!mention.isActive) {
      setMentionPopupPlacement(null);
      return;
    }

    const updateMentionPopupPlacement = () => {
      const container = containerRef.current;
      setMentionPopupPlacement(
        getMentionPopupFixedPlacement({
          inputRect: container?.getBoundingClientRect() ?? null,
          viewportHeight: window.visualViewport?.height ?? window.innerHeight,
        }),
      );
    };

    updateMentionPopupPlacement();
    window.addEventListener("resize", updateMentionPopupPlacement);
    window.addEventListener("scroll", updateMentionPopupPlacement, true);
    window.visualViewport?.addEventListener(
      "resize",
      updateMentionPopupPlacement,
    );
    window.visualViewport?.addEventListener(
      "scroll",
      updateMentionPopupPlacement,
    );
    return () => {
      window.removeEventListener("resize", updateMentionPopupPlacement);
      window.removeEventListener("scroll", updateMentionPopupPlacement, true);
      window.visualViewport?.removeEventListener(
        "resize",
        updateMentionPopupPlacement,
      );
      window.visualViewport?.removeEventListener(
        "scroll",
        updateMentionPopupPlacement,
      );
    };
  }, [mention.isActive]);

  const personaAvatar = useMemo(() => {
    if (!selectedPersonaPresetId) return null;
    const preset = personaPresets.find((p) => p.id === selectedPersonaPresetId);
    if (!preset) return null;
    return {
      avatar: preset.avatar ?? undefined,
      primaryTag: preset.tags[0] || "",
    };
  }, [selectedPersonaPresetId, personaPresets]);

  const availableRunSkills = useMemo(
    () => (enableSkills ? skills.filter((skill) => skill.enabled) : []),
    [skills, enableSkills],
  );

  const applySlashCommand = useCallback((command: ChatInputSlashCommand) => {
    if (command.kind !== "panel") return;
    if (command.id === "tools") setActivePanel("tools");
    else if (command.id === "persona") setActivePanel("persona");
    else if (command.id === "team") setActivePanel("team");
    else if (command.id === "agent") setActivePanel("agent");
  }, []);

  const applyMentionSelection = useCallback(
    (preset: PersonaPreset) => {
      if (!mention.isActive) return;
      const before = input.substring(0, mention.atIndex);
      const after = input.substring(mention.atIndex + mention.query.length + 1);
      const newInput = before + after;
      setComposerPlainText(newInput);
      setCursorPosition(before.length || 0);
      requestAnimationFrame(() => {
        composerRef.current?.focus({ atEnd: true });
      });
      onUsePersonaPreset?.(preset);
      resetMention();
    },
    [input, mention, onUsePersonaPreset, resetMention, setComposerPlainText],
  );

  const applyTeamMentionSelection = useCallback(
    (team: Team) => {
      if (!mention.isActive) return;
      const before = input.substring(0, mention.atIndex);
      const after = input.substring(mention.atIndex + mention.query.length + 1);
      const newInput = before + after;
      setComposerPlainText(newInput);
      setCursorPosition(before.length || 0);
      requestAnimationFrame(() => {
        composerRef.current?.focus({ atEnd: true });
      });
      onSelectTeam?.(team.id);
      resetMention();
    },
    [input, mention, onSelectTeam, resetMention, setComposerPlainText],
  );

  const handleComposerChange = useCallback((change: RichChatComposerChange) => {
    const { projection } = change;
    inputValueRef.current = projection.message;
    setInput(projection.message);
    setCursorPosition(projection.message.length);
    setActiveReferenceIds(projection.activeReferenceIds);
    setRunEnabledSkillNames(
      projection.enabledSkills.length > 0 ? projection.enabledSkills : null,
    );
  }, []);

  const handleLongTextCreate = useCallback(
    (payload: LongTextPastePayload) => {
      longTextResourcesRef.current.set(payload.referenceId, payload);
      uploadFile(
        payload.file,
        "document",
        buildLongTextClientMeta(payload.originalText, payload.referenceId),
      );
      toast.success(t("chat.textAutoUploaded", "长文本已自动转为文件上传"));
    },
    [t, uploadFile],
  );

  const handleRetryFileReference = useCallback(
    (referenceId: string) => {
      const resource = longTextResourcesRef.current.get(referenceId);
      if (!resource) return;
      setAttachments((previous) =>
        previous.filter(
          (attachment) => attachment.composerReferenceId !== referenceId,
        ),
      );
      composerRef.current?.updateFileReference({
        referenceId,
        status: "uploading",
      });
      uploadFile(
        resource.file,
        "document",
        buildLongTextClientMeta(resource.originalText, referenceId),
      );
    },
    [setAttachments, uploadFile],
  );

  const handleRestoreLongTextAttachment = useCallback(
    (attachment: MessageAttachment) => {
      const referenceId = attachment.composerReferenceId;
      if (!referenceId) {
        restoreLongTextAttachment(attachment);
        return;
      }
      const resource = longTextResourcesRef.current.get(referenceId);
      const originalText =
        resource?.originalText ?? attachment.localOriginalText ?? "";
      composerRef.current?.removeFileReference(referenceId);
      if (originalText) composerRef.current?.insertText(originalText);
      longTextResourcesRef.current.delete(referenceId);
      setAttachments((previous) =>
        previous.filter((item) => item.id !== attachment.id),
      );
    },
    [restoreLongTextAttachment, setAttachments],
  );

  useEffect(() => {
    for (const attachment of attachments) {
      const referenceId = attachment.composerReferenceId;
      if (!referenceId) continue;
      composerRef.current?.updateFileReference({
        referenceId,
        fileName: attachment.name,
        status: attachment.uploadError
          ? "failed"
          : attachment.isUploading
            ? "uploading"
            : "ready",
      });
    }
  }, [attachments]);

  const visibleAttachments = useMemo(
    () => selectVisibleDraftAttachments(attachments, activeReferenceIds),
    [activeReferenceIds, attachments],
  );

  const handleComposerKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      // Lexical prevents Enter before this React handler runs, so
      // defaultPrevented cannot distinguish editor handling from send intent.
      if (mention.isActive) {
        if (event.key === "Enter" || event.key === "Tab") {
          event.preventDefault();
          if (mentionMode === "team") {
            const team = teamMentionSearch.teams[mention.highlightedIndex];
            if (team) applyTeamMentionSelection(team);
          } else {
            const preset = mentionSearch.presets[mention.highlightedIndex];
            if (preset) applyMentionSelection(preset);
          }
          return;
        }
        if (event.key === "Escape") {
          event.preventDefault();
          resetMention();
          return;
        }
      }
      if (event.key === "Enter") {
        if (event.nativeEvent.isComposing || event.keyCode === 229) return;
        if (!isSendEnterKey(event)) return;
        event.preventDefault();
        if (isLoading) setStopConfirmOpen(true);
        else event.currentTarget.closest("form")?.requestSubmit();
        return;
      }
    },
    [
      applyMentionSelection,
      applyTeamMentionSelection,
      isLoading,
      mention.highlightedIndex,
      mention.isActive,
      mentionMode,
      mentionSearch.presets,
      resetMention,
      teamMentionSearch.teams,
    ],
  );

  const handleComposerArrowKey = useCallback(
    (direction: ComposerArrowDirection, editor: HTMLElement) => {
      if (mention.isActive) {
        moveMentionHighlight(direction);
        return true;
      }

      if (
        getMatchingSlashDropdownItems(input, cursorPosition, availableRunSkills)
          .length > 0
      ) {
        return false;
      }

      if (!isBrowsing && input.includes("\n")) {
        const boundary = getComposerCaretBoundary(editor);
        if (!(direction === "up" ? boundary.atStart : boundary.atEnd)) {
          return false;
        }
      }

      const historyValue =
        direction === "up" ? navigateUp(input) : navigateDown();
      if (historyValue === null) return false;

      setComposerPlainText(historyValue);
      requestAnimationFrame(() => composerRef.current?.focus({ atEnd: true }));
      return true;
    },
    [
      input,
      isBrowsing,
      cursorPosition,
      availableRunSkills,
      mention.isActive,
      moveMentionHighlight,
      navigateDown,
      navigateUp,
      setComposerPlainText,
    ],
  );

  const hasContent =
    (!!input.trim() || visibleAttachments.length > 0) && !disabled;
  const hasUploadingAttachment =
    visibleAttachments.some((attachment) => attachment.isUploading) ||
    activeReferenceIds.some(
      (referenceId) =>
        !attachments.some(
          (attachment) => attachment.composerReferenceId === referenceId,
        ),
    );
  const hasFailedAttachment = visibleAttachments.some(
    (attachment) => attachment.uploadError,
  );
  const canSubmit =
    hasContent &&
    canSend &&
    !isLoading &&
    !hasUploadingAttachment &&
    !hasFailedAttachment;
  const handleSubmit = useAcceptedDraftSubmission({
    enabled: canSubmit,
    input,
    enabledSkillNames: runEnabledSkillNames,
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
  });
  const composerPlaceholder = !canSend
    ? t("chat.noPermission")
    : mentionMode === "team"
      ? t("chat.teamPlaceholder")
      : t("chat.placeholder");

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingOver(false);
    const files = e.dataTransfer?.files;
    if (!files || files.length === 0) return;
    if (!validateCount(files.length)) return;
    uploadFiles(files);
  };

  const { label: thinkingLabel, level: thinkingLevel } =
    resolveThinkingPresentation(agentOptions, agentOptionValues, t);

  return (
    <div
      className="chat-input-shell sm:px-4 pb-3 sm:pb-5"
      style={{ backgroundColor: "var(--theme-bg)" }}
    >
      {composerExpanded ? (
        <div
          className="fixed inset-0 z-[279] bg-black/45"
          onClick={() => setComposerExpanded(false)}
          aria-hidden="true"
        />
      ) : null}
      <form
        onSubmit={handleSubmit}
        className={
          className ?? "mx-auto max-w-4xl lg:max-w-5xl xl:max-w-6xl px-2"
        }
      >
        <div
          ref={containerRef}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`chat-input-container flex flex-col relative w-full rounded-3xl px-1 border transition-all duration-300 ${
            isDraggingOver ? "data-drag-over" : ""
          }`}
          data-mention-active={mention.isActive || undefined}
          data-drag-over={isDraggingOver || undefined}
          data-composer-expanded={composerExpanded || undefined}
          style={{
            backgroundColor: "var(--theme-bg-card)",
          }}
        >
          {isDraggingOver && <ChatInputDragOverlay />}
          <ActiveGoalBar
            goal={activeGoal ?? null}
            label={goalLabel}
            durationLabel={goalDurationLabel}
            clearLabel={goalClearLabel}
            onClear={onClearActiveGoal}
            disabled={isLoading || !canSend}
            embedded
          />
          {mention.isActive &&
            !onMentionQueryChange &&
            mentionMode === "persona" && (
              <MentionPopup
                presets={mentionSearch.presets}
                highlightedIndex={mention.highlightedIndex}
                selectedPresetId={selectedPersonaPresetId}
                isLoading={mentionSearch.isLoading}
                isLoadingMore={mentionSearch.isLoadingMore}
                hasMore={mentionSearch.hasMore}
                onSelect={applyMentionSelection}
                onHover={setMentionHighlight}
                onClose={dismissMention}
                onLoadMore={mentionSearch.loadMore}
                placement={mentionPopupPlacement ?? undefined}
              />
            )}
          {mention.isActive &&
            !onMentionQueryChange &&
            mentionMode === "team" && (
              <TeamMentionPopup
                teams={teamMentionSearch.teams}
                highlightedIndex={mention.highlightedIndex}
                selectedTeamId={selectedTeamId}
                isLoading={teamMentionSearch.isLoading}
                onSelect={applyTeamMentionSelection}
                onHover={setMentionHighlight}
                onClose={dismissMention}
                placement={mentionPopupPlacement ?? undefined}
              />
            )}

          <ChatInputAttachments
            attachments={visibleAttachments}
            onAttachmentsChange={setAttachments}
            onCancelUpload={cancelUpload}
            onImageViewerOpen={(url) => setImageViewerSrc(url)}
            maxFiles={uploadLimits?.maxFiles}
            onRestoreLongText={handleRestoreLongTextAttachment}
            onRemoveReference={(referenceId) => {
              longTextResourcesRef.current.delete(referenceId);
              composerRef.current?.removeFileReference(referenceId);
            }}
            onRetryUpload={(attachment) => {
              if (attachment.composerReferenceId) {
                handleRetryFileReference(attachment.composerReferenceId);
              }
            }}
          />

          <div className="chat-composer-editor-wrap px-2.5 pt-1">
            {composerExpanded ? (
              <div className="flex items-center justify-between border-b px-2 pb-3 pt-1">
                <div>
                  <div className="text-sm font-medium text-[var(--theme-text)]">
                    {t("chat.expandedComposerTitle", "展开编辑")}
                  </div>
                  <div className="mt-0.5 text-xs text-[var(--theme-text-secondary)]">
                    {t(
                      "chat.expandedComposerHint",
                      "适合编辑长提示词。Esc 收起，发送快捷键保持不变。",
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setComposerExpanded(false)}
                  className="inline-flex size-8 items-center justify-center rounded-lg transition hover:bg-[color-mix(in_srgb,var(--theme-text)_8%,transparent)]"
                  style={{ color: "var(--theme-text-secondary)" }}
                  title={t("chat.collapseComposer", "收起")}
                  aria-label={t("chat.collapseComposer", "收起")}
                >
                  <Minimize2 size={16} />
                </button>
              </div>
            ) : null}
            <div className="relative min-h-0 flex-1">
              <Suspense
                fallback={
                  <div
                    className="rich-chat-composer__editor"
                    aria-hidden="true"
                  />
                }
              >
                <RichChatComposer
                  ref={composerRef}
                  ariaLabel={t("chat.messageInput", "Message")}
                  initialPlainText={input}
                  placeholder={composerPlaceholder}
                  availableSkills={availableRunSkills}
                  onApplySlashCommand={applySlashCommand}
                  onChange={handleComposerChange}
                  filePaste={{ validateCount, onFiles: uploadFiles }}
                  longTextPaste={{
                    enabled: !composerExpanded,
                    validateCount,
                    onCreate: handleLongTextCreate,
                  }}
                  onRetryFileReference={handleRetryFileReference}
                  onKeyDown={handleComposerKeyDown}
                  onArrowKey={handleComposerArrowKey}
                  disabled={disabled || !canSend}
                />
              </Suspense>
              {!composerExpanded && showExpandButton ? (
                <button
                  type="button"
                  onClick={() => setComposerExpanded(true)}
                  className="absolute right-1 top-2 inline-flex size-6 items-center justify-center rounded-md opacity-60 transition hover:opacity-100"
                  style={{ color: "var(--theme-text-secondary)" }}
                  title={t("chat.expandComposer", "展开编辑")}
                  aria-label={t("chat.expandComposer", "展开编辑")}
                  disabled={disabled || !canSend}
                >
                  <Maximize2 size={14} />
                </button>
              ) : null}
            </div>
          </div>

          <ChatInputToolbar
            activePanel={activePanel}
            onActivePanelChange={setActivePanel}
            canSend={canSend}
            isLoading={isLoading}
            canSubmit={canSubmit}
            hasUploadingAttachment={hasUploadingAttachment}
            enabledToolsCount={enabledToolsCount}
            totalToolsCount={totalToolsCount}
            enabledSkillsCount={enabledSkillsCount}
            totalSkillsCount={totalSkillsCount}
            hasPersonaSelector={!!onUsePersonaPreset}
            personaName={selectedPersonaName}
            hasAgentSelector={agents.length > 1 && !!onSelectAgent}
            agentName={(() => {
              const agent = agents.find((a) => a.id === currentAgent);
              return agent
                ? resolveAgentDisplayName(agent, i18n.language, t)
                : undefined;
            })()}
            agentIcon={agents.find((a) => a.id === currentAgent)?.icon}
            hasThinkingOption={
              !!(
                agentOptions &&
                onToggleAgentOption &&
                Object.keys(agentOptions).length > 0
              )
            }
            thinkingLabel={thinkingLabel}
            thinkingLevel={thinkingLevel}
            uploadCategories={uploadCategories}
            uploadFiles={uploadFiles}
            selectedPersonaName={selectedPersonaName}
            personaAvatar={personaAvatar}
            onClearPersonaPreset={onClearPersonaPreset}
            currentAgent={currentAgent}
            selectedTeamId={selectedTeamId}
            onSelectTeam={onSelectTeam}
            agentOptions={agentOptions}
            agentOptionValues={agentOptionValues}
            onToggleAgentOption={onToggleAgentOption}
            onStopClick={() => setStopConfirmOpen(true)}
            onNoPermissionClick={() => setContactAdminOpen(true)}
            autoModeEnabled={autoModeEnabled}
            goalModeEnabled={goalModeEnabled}
            onToggleAutoMode={onToggleAutoMode}
            onToggleGoalMode={onToggleGoalMode}
          />
        </div>
      </form>

      <ChatInputSelectors
        activePanel={activePanel}
        onActivePanelChange={setActivePanel}
        tools={tools}
        onToggleTool={onToggleTool}
        onToggleCategory={onToggleCategory}
        onToggleAll={onToggleAll}
        enabledToolsCount={enabledToolsCount}
        totalToolsCount={totalToolsCount}
        skills={skills}
        onToggleSkill={onToggleSkill}
        onToggleSkillCategory={onToggleSkillCategory}
        onToggleAllSkills={onToggleAllSkills}
        pendingSkillNames={pendingSkillNames}
        skillsMutating={skillsMutating}
        enabledSkillsCount={enabledSkillsCount}
        totalSkillsCount={totalSkillsCount}
        enableSkills={enableSkills}
        personaSkillsControlled={personaSkillsControlled}
        selectedPersonaName={selectedPersonaName}
        personaPresets={personaPresets}
        personaPresetsTotal={personaPresetsTotal}
        personaPresetsPage={personaPresetsPage}
        onPersonaPresetsPageChange={onPersonaPresetsPageChange}
        onPersonaPresetsSearchChange={onPersonaPresetsSearchChange}
        onPersonaPresetsTagChange={onPersonaPresetsTagChange}
        selectedPersonaPresetId={selectedPersonaPresetId}
        personaPresetsLoading={personaPresetsLoading}
        personaPresetsMutating={personaPresetsMutating}
        onUsePersonaPreset={onUsePersonaPreset}
        onCopyPersonaPreset={onCopyPersonaPreset}
        onClearPersonaPreset={onClearPersonaPreset}
        canManagePersonaPresets={canManagePersonaPresets}
        agents={agents}
        currentAgent={currentAgent}
        onSelectAgent={onSelectAgent}
        selectedTeamId={selectedTeamId}
        onSelectTeam={onSelectTeam}
        onOpenTeamBuilder={onOpenTeamBuilder}
        agentOptions={agentOptions}
        agentOptionValues={agentOptionValues}
        onToggleAgentOption={onToggleAgentOption}
      />

      {showHelpMenu && <ChatInputHelpMenu className={helpMenuClassName} />}

      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          isOpen={!!imageViewerSrc}
          onClose={() => setImageViewerSrc(null)}
        />
      )}

      <ConfirmDialog
        isOpen={stopConfirmOpen}
        title={t("chat.stopConfirmTitle")}
        message={t("chat.stopConfirmMessage")}
        confirmText={t("chat.stop")}
        cancelText={t("common.cancel")}
        variant="warning"
        onConfirm={() => {
          setStopConfirmOpen(false);
          onStop();
          toast.custom(() => (
            <div
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium"
              style={{
                background:
                  "color-mix(in srgb, var(--theme-primary) 10%, transparent)",
                border:
                  "1px solid color-mix(in srgb, var(--theme-primary) 20%, transparent)",
                color: "var(--theme-primary)",
              }}
            >
              <Ban size={16} className="shrink-0" />
              <span>{t("chat.status.cancelled")}</span>
            </div>
          ));
        }}
        onCancel={() => setStopConfirmOpen(false)}
      />

      <ContactAdminDialog
        isOpen={contactAdminOpen}
        onClose={() => setContactAdminOpen(false)}
        reason="noPermission"
      />
    </div>
  );
});
