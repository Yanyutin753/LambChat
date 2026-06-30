import { useState, useRef, useEffect, useCallback, useMemo, memo } from "react";
import toast from "react-hot-toast";
import { Ban, Sparkles, UploadCloud } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ImageViewer } from "../common";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { ContactAdminDialog } from "../common/ContactAdminDialog";
import { useFileUpload } from "../../hooks/useFileUpload";
import { useMentionState } from "../../hooks/useMentionState";
import { useMentionSearch } from "../../hooks/useMentionSearch";
import { useInputHistory } from "../../hooks/useInputHistory";
import { useTextareaResize } from "../../hooks/useTextareaResize";
import { usePasteHandler } from "../../hooks/usePasteHandler";
import { useChatInputKeyboard } from "../../hooks/useChatInputKeyboard";
import { useAuth } from "../../hooks/useAuth";
import { MentionPopup } from "./MentionPopup";
import { ActiveGoalBar } from "./ActiveGoalBar";
import { ChatInputToolbar } from "./ChatInputToolbar";
import { ChatInputSelectors } from "./ChatInputSelectors";
import { ChatInputHelpMenu } from "./ChatInputHelpMenu";
import { ChatInputAttachments } from "./ChatInputAttachments";
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
import {
  buildChatInputOptionContributions,
  buildChatInputPanelContributions,
  buildMentionProviderContributions,
} from "../../extensions/coreContributions";
import {
  isPluginMentionProviderSupported,
  usePluginMentionProviderRuntime,
} from "./chatMentionProviderRenderers";
import type { PluginOptionsMetadata } from "../../extensions/pluginOptions";

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
  pluginOptionValues: providedPluginOptionValues,
  onPluginOptionChange,
  runtimePlugins,
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

  const { scheduleTextareaResize } = useTextareaResize(textareaRef, input);

  const { handlePaste } = usePasteHandler({
    textareaRef,
    input,
    setInput,
    uploadFiles,
    validateCount,
    scheduleTextareaResize,
  });

  const pluginContributionContext = useMemo(
    () => ({ agentId: currentAgent ?? null }),
    [currentAgent],
  );
  const chatInputOptions = useMemo(
    () => buildChatInputOptionContributions(runtimePlugins, pluginContributionContext),
    [runtimePlugins, pluginContributionContext],
  );
  const chatInputPanels = useMemo(
    () => buildChatInputPanelContributions(runtimePlugins, pluginContributionContext),
    [runtimePlugins, pluginContributionContext],
  );
  const pluginOptionValues = useMemo<PluginOptionsMetadata>(() => {
    return providedPluginOptionValues ?? {};
  }, [providedPluginOptionValues]);
  const handlePluginOptionChange = useCallback(
    (pluginId: string, key: string, value: unknown) => {
      onPluginOptionChange?.(pluginId, key, value);
    },
    [onPluginOptionChange],
  );
  const mentionProviders = useMemo(
    () => buildMentionProviderContributions(runtimePlugins, pluginContributionContext),
    [runtimePlugins, pluginContributionContext],
  );
  const activePluginMentionProvider = mentionProviders.find((provider) =>
    isPluginMentionProviderSupported(provider, {
      onPluginOptionChange: handlePluginOptionChange,
    }),
  );
  const pluginShortcutPanelIds = new Set(chatInputPanels.map((panel) => panel.id));
  const pluginShortcutOptions = chatInputOptions.filter(
    (option) => option.shortcut && option.panel && pluginShortcutPanelIds.has(option.panel),
  );
  const mentionMode: "team" | "persona" =
    activePluginMentionProvider?.mode === "team" ? "team" : "persona";
  const mentionEnabled =
    activePluginMentionProvider ? true : !!onUsePersonaPreset;

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

  const clearActiveMention = useCallback(() => {
    if (!mention.isActive) return;
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
  }, [input, mention, resetMention, scheduleTextareaResize]);

  const pluginMentionRuntime = usePluginMentionProviderRuntime({
    provider: activePluginMentionProvider ?? null,
    query: mention.query,
    isActive: mention.isActive,
    highlightedIndex: mention.highlightedIndex,
    selectedTeamId,
    onPluginOptionChange: handlePluginOptionChange,
    onBeforeSelect: clearActiveMention,
    onHover: setMentionHighlight,
    onClose: dismissMention,
    placement: mentionPopupPlacement ?? undefined,
  });

  useEffect(() => {
    if (mention.isActive) {
      setMentionResultCount(
        pluginMentionRuntime
          ? pluginMentionRuntime.resultCount
          : mentionSearch.presets.length,
      );
    }
  }, [
    mention.isActive,
    mentionSearch.presets.length,
    pluginMentionRuntime,
    setMentionResultCount,
  ]);

  useEffect(() => {
    if (!onMentionQueryChange) return;
    onMentionQueryChange(mention.isActive ? mention.query : null);
  }, [mention.isActive, mention.query, onMentionQueryChange]);

  useEffect(() => {
    if (!onMentionQueryChange || !selectedPersonaPresetId || !mention.isActive)
      return;
    clearActiveMention();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires only on preset selection
  }, [selectedPersonaPresetId]);

  useEffect(() => {
    if (!onMentionQueryChange || !selectedTeamId || !mention.isActive) return;
    clearActiveMention();
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

  // Plugin-declared shortcuts open their matching chat input panels.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const matchingOption = pluginShortcutOptions.find((option) =>
        matchesPluginShortcut(option.shortcut, e),
      );
      const panelId = matchingOption?.panel;
      if (!panelId) return;
      e.preventDefault();
      setActivePanel((prev) => (prev === panelId ? null : panelId));
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [pluginShortcutOptions]);

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
      clearActiveMention();
      onUsePersonaPreset?.(preset);
    },
    [clearActiveMention, mention.isActive, onUsePersonaPreset],
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSend) return;
    if (input.trim() && canSubmit) {
      const trimmed = input.trim();
      const runOptions = runEnabledSkillNames
        ? { enabledSkills: runEnabledSkillNames }
        : undefined;
      onSend(trimmed, agentOptionValues, attachments, runOptions);
      pushHistory(trimmed);
      setInput("");
      setRunEnabledSkillNames(null);
      setAttachments([]);
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
      selectHighlighted: pluginMentionRuntime?.selectHighlighted,
      teamItems: [],
      personaItems: mentionSearch.presets,
      onTeamSelect: () => undefined,
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

  const hasContent = !!input.trim() && !disabled;
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

  const thinkingLabel = agentOptions
    ? Object.entries(agentOptions)
        .filter(([, opt]) => opt.options && opt.options.length > 0)
        .map(([, opt]) => {
          const val =
            agentOptionValues[
              Object.keys(agentOptions).find((k) => agentOptions[k] === opt)!
            ] ?? opt.default;
          const selected = opt.options?.find((o) => o.value === val);
          return selected?.label_key
            ? t(selected.label_key)
            : selected?.label || String(val);
        })[0]
    : undefined;

  const thinkingLevel = agentOptions
    ? Object.entries(agentOptions)
        .filter(([, opt]) => opt.options && opt.options.length > 0)
        .map(([, opt]) => {
          const val =
            agentOptionValues[
              Object.keys(agentOptions).find((k) => agentOptions[k] === opt)!
            ] ?? opt.default;
          return String(val);
        })[0]
    : undefined;

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
            isDraggingOver ? "border-dashed border-2 scale-[1.01]" : ""
          }`}
          data-mention-active={mention.isActive || undefined}
          style={{
            backgroundColor: "var(--theme-bg-card)",
            borderColor: isDraggingOver
              ? "var(--theme-primary)"
              : "var(--theme-border)",
            boxShadow: isDraggingOver
              ? "0 0 0 3px color-mix(in srgb, var(--theme-primary) 15%, transparent), 0 4px 20px rgba(0,0,0,0.08)"
              : "0 2px 12px rgba(0,0,0,0.06)",
          }}
        >
          {/* Drag-over overlay */}
          {isDraggingOver && (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded-3xl pointer-events-none">
              <div
                className="flex flex-col items-center gap-2 rounded-2xl px-10 py-8 transition-all"
                style={{
                  backgroundColor:
                    "color-mix(in srgb, var(--theme-primary) 6%, transparent)",
                }}
              >
                <UploadCloud
                  size={28}
                  className="animate-bounce"
                  style={{
                    color: "var(--theme-primary)",
                    opacity: 0.7,
                  }}
                />
                <span
                  className="text-sm font-medium"
                  style={{
                    color: "var(--theme-primary)",
                    opacity: 0.7,
                  }}
                >
                  {t("chat.dropFilesHere", "Drop files here to upload")}
                </span>
              </div>
            </div>
          )}
          <ActiveGoalBar
            goal={activeGoal ?? null}
            label={goalLabel}
            durationLabel={goalDurationLabel}
            clearLabel={goalClearLabel}
            onClear={onClearActiveGoal}
            disabled={isLoading || !canSend}
            embedded
          />
          {runEnabledSkillNames && (
            <div className="flex items-center gap-2 border-b px-3 py-2 text-xs sm:px-4">
              <Sparkles
                size={14}
                className="shrink-0"
                style={{ color: "var(--theme-primary)" }}
              />
              <button
                type="button"
                className="min-w-0 flex-1 truncate text-left"
                style={{ color: "var(--theme-text-secondary)" }}
                onClick={() => setRunSkillSelectorOpen(true)}
              >
                {t("chat.commands.runSkillsCount", {
                  count: runEnabledSkillNames.length,
                  defaultValue: "{{count}} skills for next message",
                })}
              </button>
              <button
                type="button"
                className="rounded-md px-2 py-1 transition-colors hover:bg-stone-100 dark:hover:bg-stone-800"
                style={{ color: "var(--theme-text-secondary)" }}
                onClick={() => setRunEnabledSkillNames(null)}
              >
                {t("common.clear", "Clear")}
              </button>
            </div>
          )}
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
            pluginMentionRuntime?.popup}

          <ChatInputAttachments
            attachments={attachments}
            onAttachmentsChange={setAttachments}
            onCancelUpload={cancelUpload}
            onImageViewerOpen={(url) => setImageViewerSrc(url)}
            maxFiles={uploadLimits?.maxFiles}
          />

          <div className="px-2.5 pt-1">
            <div className="relative">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  setCursorPosition(e.target.selectionStart);
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
                    ? pluginMentionRuntime?.placeholderKey
                      ? t(pluginMentionRuntime.placeholderKey)
                      : t("chat.placeholder")
                    : t("chat.noPermission")
                }
                disabled={disabled || !canSend}
                className="bg-transparent outline-none w-full pt-[10px] resize-none text-[15px] disabled:opacity-50 leading-relaxed overflow-y-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none] min-h-[40px] sm:min-h-[44px]"
                style={{
                  color: "var(--theme-text)",
                  paddingLeft: 4,
                }}
                rows={1}
              />
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
            agentName={agents.find((a) => a.id === currentAgent)?.name}
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
            uploadLimits={uploadLimits}
            uploadFiles={uploadFiles}
            selectedPersonaName={selectedPersonaName}
            personaAvatar={personaAvatar}
            onClearPersonaPreset={onClearPersonaPreset}
            currentAgent={currentAgent}
            pluginOptionValues={pluginOptionValues}
            onPluginOptionChange={handlePluginOptionChange}
            chatInputOptions={chatInputOptions}
            agentOptions={agentOptions}
            agentOptionValues={agentOptionValues}
            onToggleAgentOption={onToggleAgentOption}
            onStopClick={() => setStopConfirmOpen(true)}
            onNoPermissionClick={() => setContactAdminOpen(true)}
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
        pluginOptionValues={pluginOptionValues}
        onPluginOptionChange={handlePluginOptionChange}
        chatInputPanels={chatInputPanels}
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
    </div>
  );
});

function matchesPluginShortcut(
  shortcut: string | null | undefined,
  event: KeyboardEvent,
): boolean {
  if (!shortcut) return false;
  const normalized = shortcut.trim().toLowerCase();
  const match = normalized.match(/^mod\+([a-z])$/);
  if (!match) return false;
  const isMac =
    typeof navigator !== "undefined" &&
    navigator.platform.toUpperCase().includes("MAC");
  const modifier = isMac ? event.metaKey : event.ctrlKey;
  return modifier && event.key.toLowerCase() === match[1];
}
