import { useState, useRef, useEffect, useCallback, useMemo, memo } from "react";
import toast from "react-hot-toast";
import { Ban, Maximize2 } from "lucide-react";
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
import { useTextareaResize } from "../../hooks/useTextareaResize";
import { usePasteHandler } from "../../hooks/usePasteHandler";
import { useChatInputKeyboard } from "../../hooks/useChatInputKeyboard";
import { useLongTextConversion } from "../../hooks/useLongTextConversion";
import { useAuth } from "../../hooks/useAuth";
import { MentionPopup } from "./MentionPopup";
import { TeamMentionPopup } from "./TeamMentionPopup";
import { ActiveGoalBar } from "./ActiveGoalBar";
import { ChatInputToolbar } from "./ChatInputToolbar";
import { ChatInputSelectors } from "./ChatInputSelectors";
import { ChatInputHelpMenu } from "./ChatInputHelpMenu";
import { ChatInputAttachments } from "./ChatInputAttachments";
import { ChatInputDragOverlay } from "./ChatInputDragOverlay";
import { ChatInputExpandedComposer } from "./ChatInputExpandedComposer";
import { ChatInputRunSkillsBar } from "./ChatInputRunSkillsBar";
import { resolveThinkingPresentation } from "./chatInputThinking";
import { SkillSelector } from "../selectors/SkillSelector";
import { FILE_CATEGORY_PERMISSIONS } from "./chatInputConstants";
import { getMentionPopupFixedPlacement } from "./chatInputViewport";
import { SlashDropdownMenu } from "./SlashDropdownMenu";
import {
  applySlashCommandSelection,
  clearSlashCommandInput,
  getMatchingSlashDropdownItems,
  getSlashDropdownSections,
  type SlashDropdownItem,
} from "./chatInputSlashCommands";
import { updateRunSkillNamesForSlashSelection } from "./runSkillSelection";
import {
  consumePendingSelectionActionPrompt,
  SELECTION_ACTION_EVENT,
  type SelectionActionEventDetail,
} from "../common/selectionActionPopover";
import type { ChatInputProps } from "./chatInputTypes";
import type { FeaturePanel } from "../selectors/FeatureMenu";
import type { MessageAttachment, PersonaPreset } from "../../types";
import type { Team } from "../../types/team";

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

  // Consume external pendingInput: fill textarea and focus
  useEffect(() => {
    if (pendingInput) {
      setInput(pendingInput);
      onPendingInputConsumed?.();
      requestAnimationFrame(() => {
        const textarea = textareaRef.current;
        if (textarea) {
          textarea.focus();
          textarea.selectionStart = textarea.selectionEnd = pendingInput.length;
        }
      });
    }
  }, [pendingInput, onPendingInputConsumed]);

  const [activePanel, setActivePanel] = useState<FeaturePanel>(null);
  const [runSkillSelectorOpen, setRunSkillSelectorOpen] = useState(false);
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

  const textareaRef = useRef<HTMLTextAreaElement>(null);
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

  const { uploadFiles, uploadLimits, validateCount, cancelUpload } =
    useFileUpload({
      attachments,
      onAttachmentsChange: setAttachments,
    });

  const { history, pushHistory, navigateUp, navigateDown } = useInputHistory();

  const { scheduleTextareaResize, showExpandButton } = useTextareaResize(
    textareaRef,
    input,
  );

  const {
    convertTextToAttachment,
    maybeConvertInput,
    restoreLongTextAttachment,
    prepareSubmit,
  } = useLongTextConversion({
    setInput,
    setAttachments,
    uploadFiles,
    validateCount,
    scheduleTextareaResize,
    expanded: composerExpanded,
  });

  const handleLongTextPaste = useCallback(
    (text: string) => {
      // Expanded composer keeps long prompts editable as plain text.
      if (composerExpanded) return false;
      return convertTextToAttachment(text);
    },
    [composerExpanded, convertTextToAttachment],
  );

  const { handlePaste } = usePasteHandler({
    textareaRef,
    input,
    setInput,
    uploadFiles,
    validateCount,
    scheduleTextareaResize,
    onLongTextPaste: handleLongTextPaste,
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
    setInput(before + after);
    setCursorPosition(before.length || 0);
    requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (textarea) {
        textarea.selectionStart = textarea.selectionEnd = before.length;
        textarea.focus();
        scheduleTextareaResize();
      }
    });
    resetMention();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires only on preset selection
  }, [selectedPersonaPresetId]);

  useEffect(() => {
    if (!onMentionQueryChange || !selectedTeamId || !mention.isActive) return;
    const before = input.substring(0, mention.atIndex);
    const after = input.substring(mention.atIndex + mention.query.length + 1);
    setInput(before + after);
    setCursorPosition(before.length || 0);
    requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (textarea) {
        textarea.selectionStart = textarea.selectionEnd = before.length;
        textarea.focus();
        scheduleTextareaResize();
      }
    });
    resetMention();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires only on team selection
  }, [selectedTeamId]);

  useEffect(() => {
    const applySelectionActionPrompt = (prompt: string) => {
      setInput((previous) => {
        const next = previous.trim()
          ? `${previous.trim()}\n\n${prompt}`
          : prompt;
        setCursorPosition(next.length);
        requestAnimationFrame(() => {
          const textarea = textareaRef.current;
          if (!textarea) return;
          textarea.focus();
          textarea.selectionStart = textarea.selectionEnd = next.length;
          scheduleTextareaResize();
        });
        return next;
      });
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
  }, [scheduleTextareaResize]);

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

  const slashDropdownItems = useMemo(
    () =>
      getMatchingSlashDropdownItems(
        input,
        cursorPosition,
        enableSkills ? availableRunSkills : undefined,
      ),
    [input, cursorPosition, enableSkills, availableRunSkills],
  );
  const slashCommandOpen = slashDropdownItems.length > 0;
  const slashDropdownSections = useMemo(
    () => getSlashDropdownSections(slashDropdownItems),
    [slashDropdownItems],
  );

  const [slashHighlightIndex, setSlashHighlightIndex] = useState(0);

  const applySlashDropdownSelection = useCallback(
    (item: SlashDropdownItem) => {
      // ── Skill selection: require this skill for the next message ──
      if (item.type === "skill") {
        setRunEnabledSkillNames((current) => {
          return updateRunSkillNamesForSlashSelection({
            currentRunSkillNames: current,
            availableSkillNames: availableRunSkills.map((s) => s.name),
            selectedSkillName: item.skill.name,
          });
        });
        const cleared = clearSlashCommandInput(input, cursorPosition);
        setInput(cleared.input);
        setCursorPosition(cleared.cursorPosition);
        requestAnimationFrame(() => {
          const textarea = textareaRef.current;
          if (!textarea) return;
          textarea.focus();
          scheduleTextareaResize();
        });
        return;
      }

      // ── Built-in command handling ──
      const command = item.command;
      if (command.kind === "panel") {
        setInput("");
        setCursorPosition(0);
        if (command.id === "tools") {
          setActivePanel("tools");
        } else if (command.id === "persona") {
          setActivePanel("persona");
        } else if (command.id === "team") {
          setActivePanel("team");
        } else if (command.id === "agent") {
          setActivePanel("agent");
        }
        requestAnimationFrame(() => {
          const textarea = textareaRef.current;
          if (!textarea) return;
          textarea.focus();
          scheduleTextareaResize();
        });
        return;
      }
      // kind: "insert" (e.g. /goal)
      const next = applySlashCommandSelection(input, cursorPosition, command);
      setInput(next.input);
      setCursorPosition(next.cursorPosition);
      requestAnimationFrame(() => {
        const textarea = textareaRef.current;
        if (!textarea) return;
        textarea.focus();
        textarea.selectionStart = textarea.selectionEnd = next.cursorPosition;
        scheduleTextareaResize();
      });
    },
    [availableRunSkills, cursorPosition, input, scheduleTextareaResize],
  );

  const applyMentionSelection = useCallback(
    (preset: PersonaPreset) => {
      if (!mention.isActive) return;
      const before = input.substring(0, mention.atIndex);
      const after = input.substring(mention.atIndex + mention.query.length + 1);
      const newInput = before + after;
      setInput(newInput);
      setCursorPosition(before.length || 0);
      requestAnimationFrame(() => {
        const textarea = textareaRef.current;
        if (textarea) {
          textarea.selectionStart = textarea.selectionEnd = before.length;
          textarea.focus();
          scheduleTextareaResize();
        }
      });
      onUsePersonaPreset?.(preset);
      resetMention();
    },
    [input, mention, onUsePersonaPreset, resetMention, scheduleTextareaResize],
  );

  const applyTeamMentionSelection = useCallback(
    (team: Team) => {
      if (!mention.isActive) return;
      const before = input.substring(0, mention.atIndex);
      const after = input.substring(mention.atIndex + mention.query.length + 1);
      const newInput = before + after;
      setInput(newInput);
      setCursorPosition(before.length || 0);
      requestAnimationFrame(() => {
        const textarea = textareaRef.current;
        if (textarea) {
          textarea.selectionStart = textarea.selectionEnd = before.length;
          textarea.focus();
          scheduleTextareaResize();
        }
      });
      onSelectTeam?.(team.id);
      resetMention();
    },
    [input, mention, onSelectTeam, resetMention, scheduleTextareaResize],
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSend) return;
    if (canSubmit) {
      const trimmed = input.trim();
      const runOptions = runEnabledSkillNames
        ? { enabledSkills: runEnabledSkillNames }
        : undefined;
      const prepared = prepareSubmit(trimmed, attachments);
      onSend(
        prepared.message,
        agentOptionValues,
        prepared.attachments,
        runOptions,
      );
      if (trimmed) {
        pushHistory(trimmed);
      }
      setInput("");
      setRunEnabledSkillNames(null);
      setAttachments([]);
      setComposerExpanded(false);
      requestAnimationFrame(() => {
        if (textareaRef.current) {
          textareaRef.current.style.height = "auto";
        }
      });
    }
  };

  const handleKeyDown = useChatInputKeyboard(
    {
      open: slashCommandOpen,
      items: slashDropdownItems,
      highlightIndex: slashHighlightIndex,
      setHighlightIndex: setSlashHighlightIndex,
      onSelect: applySlashDropdownSelection,
    },
    {
      active: mention.isActive,
      mode: mentionMode,
      highlightedIndex: mention.highlightedIndex,
      moveHighlight: moveMentionHighlight,
      teamItems: teamMentionSearch.teams,
      personaItems: mentionSearch.presets,
      onTeamSelect: applyTeamMentionSelection,
      onPersonaSelect: applyMentionSelection,
      reset: resetMention,
    },
    {
      isLoading,
      textareaRef,
      input,
      setInput,
      setCursorPosition,
      onSubmit: handleSubmit,
      onSetStopConfirmOpen: setStopConfirmOpen,
      navigateUp,
      navigateDown,
      historyLength: history.length,
    },
  );

  const hasContent = (!!input.trim() || attachments.length > 0) && !disabled;
  const hasUploadingAttachment = attachments.some((a) => a.isUploading);
  const canSubmit =
    hasContent && canSend && !isLoading && !hasUploadingAttachment;

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

  const runSkillNameSet = useMemo(() => {
    const initialNames =
      runEnabledSkillNames ?? availableRunSkills.map((skill) => skill.name);
    return new Set(initialNames);
  }, [availableRunSkills, runEnabledSkillNames]);
  const runSkillSelectorSkills = useMemo(
    () =>
      availableRunSkills.map((skill) => ({
        ...skill,
        enabled: runSkillNameSet.has(skill.name),
      })),
    [availableRunSkills, runSkillNameSet],
  );
  const runSkillEnabledCount = runSkillSelectorSkills.filter(
    (skill) => skill.enabled,
  ).length;
  const updateRunSkillSelection = useCallback(
    (updater: (current: Set<string>) => Set<string>) => {
      setRunEnabledSkillNames((current) => {
        const base = new Set(
          current ?? availableRunSkills.map((skill) => skill.name),
        );
        return Array.from(updater(base));
      });
    },
    [availableRunSkills],
  );

  return (
    <div
      className="chat-input-shell sm:px-4 pb-3 sm:pb-5"
      style={{ backgroundColor: "var(--theme-bg)" }}
    >
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
            attachments={attachments}
            onAttachmentsChange={setAttachments}
            onCancelUpload={cancelUpload}
            onImageViewerOpen={(url) => setImageViewerSrc(url)}
            maxFiles={uploadLimits?.maxFiles}
            onRestoreLongText={restoreLongTextAttachment}
          />

          <div className="px-2.5 pt-1">
            {runEnabledSkillNames && (
              <ChatInputRunSkillsBar
                skillNames={runEnabledSkillNames}
                availableSkills={availableRunSkills}
                onOpenSelector={() => setRunSkillSelectorOpen(true)}
                onRemoveSkill={(skillName) => {
                  updateRunSkillSelection((current) => {
                    current.delete(skillName);
                    return current;
                  });
                }}
                onClear={() => setRunEnabledSkillNames(null)}
              />
            )}
            <div className="relative">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => {
                  const next = e.target.value;
                  setCursorPosition(e.target.selectionStart);
                  if (maybeConvertInput(next)) return;
                  setInput(next);
                }}
                onClick={(e) => {
                  setCursorPosition(e.currentTarget.selectionStart);
                }}
                onKeyUp={(e) => {
                  setCursorPosition(e.currentTarget.selectionStart);
                }}
                onFocus={scheduleTextareaResize}
                onKeyDown={handleKeyDown}
                onPaste={handlePaste}
                placeholder={
                  canSend
                    ? mentionMode === "team"
                      ? t("chat.teamPlaceholder")
                      : t("chat.placeholder")
                    : t("chat.noPermission")
                }
                disabled={disabled || !canSend}
                className={`bg-transparent outline-none w-full pt-[10px] resize-none text-[15px] disabled:opacity-50 leading-relaxed overflow-y-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none] min-h-[40px] sm:min-h-[44px] ${
                  showExpandButton ? "pr-8" : "pr-1"
                }`}
                style={{
                  color: "var(--theme-text)",
                  paddingLeft: 4,
                }}
                rows={1}
              />
              {showExpandButton && (
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
              )}
            </div>
          </div>
          <SlashDropdownMenu
            open={slashCommandOpen}
            sections={slashDropdownSections}
            items={slashDropdownItems}
            runSkillNameSet={runSkillNameSet}
            containerRef={containerRef}
            onApplySelection={applySlashDropdownSelection}
            highlightIndex={slashHighlightIndex}
            onHighlightChange={setSlashHighlightIndex}
          />

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

      {enableSkills && (
        <SkillSelector
          skills={runSkillSelectorSkills}
          onToggleSkill={async (name) => {
            updateRunSkillSelection((current) => {
              if (current.has(name)) {
                current.delete(name);
              } else {
                current.add(name);
              }
              return current;
            });
            return true;
          }}
          onToggleCategory={async (category, enabled) => {
            updateRunSkillSelection((current) => {
              availableRunSkills
                .filter((skill) => skill.source === category)
                .forEach((skill) => {
                  if (enabled) current.add(skill.name);
                  else current.delete(skill.name);
                });
              return current;
            });
            return true;
          }}
          onToggleAll={async (enabled) => {
            setRunEnabledSkillNames(
              enabled ? availableRunSkills.map((skill) => skill.name) : [],
            );
            return true;
          }}
          enabledCount={runSkillEnabledCount}
          totalCount={availableRunSkills.length}
          isOpen={runSkillSelectorOpen}
          onOpenChange={setRunSkillSelectorOpen}
          toastOnToggle={false}
        />
      )}

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

      <ChatInputExpandedComposer
        open={composerExpanded}
        value={input}
        disabled={disabled || !canSend}
        placeholder={
          canSend
            ? mentionMode === "team"
              ? t("chat.teamPlaceholder")
              : t("chat.placeholder")
            : t("chat.noPermission")
        }
        onChange={(next) => {
          if (maybeConvertInput(next)) return;
          setInput(next);
          setCursorPosition(next.length);
        }}
        onCollapse={() => setComposerExpanded(false)}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
      />
    </div>
  );
});
