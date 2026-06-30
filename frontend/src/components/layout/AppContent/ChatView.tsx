import { useMemo, useCallback, useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../../hooks/useAuth";
import { ChatMessage } from "../../chat/ChatMessage";
import { AttachmentPreviewHost } from "../../chat/AttachmentPreviewHost";
import { RevealPreviewHost } from "../../chat/ChatMessage/items/RevealPreviewHost";
import { SessionImageGalleryProvider } from "../../chat/ChatMessage/sessionImageGallery";
import { PersistentToolPanelHost } from "../../chat/ChatMessage/items/persistentToolPanelState";
import { ChatInput } from "../../chat/ChatInput";
import { WelcomePage } from "../../chat/WelcomePage";
import { Virtuoso, type ListRange } from "react-virtuoso";
import { ApprovalPanel } from "../../panels/ApprovalPanel";
import { SessionScheduledTasksButton } from "../../panels/ScheduledTaskPanel";
import {
  ChatSkeleton,
  ChatSkeletonMessagesOnly,
} from "../../skeletons/ChatSkeletons";
import { useMessageScroll } from "./useMessageScroll";
import {
  getAtBottomThresholdPx,
  getInitialBottomItemLocation,
  getMessageListFooterSpacerClass,
} from "./messageScrollUtils";
import { getNextMessageListSessionKey } from "./useMessageScroll";
import {
  isSessionRunning,
  shouldShowStreamingFooterSkeleton,
} from "./sessionState";
import type { MessageAttachment } from "../../../types";
import type { ChatViewProps } from "./ChatViewProps";
import { useChatAssistantIdentity } from "./ChatViewProps";
import { useChatOutline } from "./useChatOutline";
import { useRevealPreview } from "./useRevealPreview";
import { findCancelledRetryTarget } from "../../chat/ChatMessage/cancelledRetry";
import {
  getGoalForMessage,
  getVisibleActiveGoalForMessages,
} from "../../chat/goalVisibility";
import { sessionApi } from "../../../services/api";

const FLOATING_SCROLL_BUTTON_OFFSET_CLASS = "bottom-full mb-3";

export function ChatView({
  messages,
  sessionId,
  currentRunId,
  isLoading,
  isLoadingHistory,
  connectionStatus,
  canSendMessage,
  tools,
  onToggleTool,
  onToggleCategory,
  onToggleAll,
  toolsLoading,
  enabledToolsCount,
  totalToolsCount,
  skills,
  onToggleSkill,
  onToggleSkillCategory,
  onToggleAllSkills,
  skillsLoading,
  pendingSkillNames,
  skillsMutating,
  enabledSkillsCount,
  totalSkillsCount,
  enableSkills,
  personaPresets,
  personaPresetsTotal,
  hasMorePersonaPresets,
  isLoadingMorePersonaPresets,
  onLoadMorePersonaPresets,
  personaPresetsPage,
  onPersonaPresetsPageChange,
  onPersonaPresetsSearchChange,
  onPersonaPresetsTagChange,
  selectedPersonaPresetId,
  selectedPersonaName,
  selectedPersonaSnapshot,
  personaSkillsControlled,
  personaPresetsLoading,
  personaPresetsMutating,
  onUsePersonaPreset,
  onTogglePersonaPreference,
  onCopyPersonaPreset,
  onSavePersonaPreset,
  onClearPersonaPreset,
  canManagePersonaPresets,
  agentOptions,
  agentOptionValues,
  onToggleAgentOption,
  agents,
  currentAgent,
  onSelectAgent,
  selectedTeamId,
  pluginOptionValues,
  onPluginOptionChange,
  approvals,
  onRespondApproval,
  approvalLoading,
  onSendMessage,
  onStopGeneration,
  activeGoal,
  goalsByRunId,
  onClearActiveGoal,
  attachments,
  onAttachmentsChange,
  externalNavigationToken,
  externalNavigationTargetFile,
  externalNavigationPreview,
  externalNavigationTargetRunId,
  externalNavigationTargetRunPending,
  externalScrollToBottom,
  outlineToggleRef,
  runtimePlugins,
}: ChatViewProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const sessionRunning = isSessionRunning(messages, isLoading);
  const scheduledTasksRefreshKey = [
    sessionId ?? "",
    currentRunId ?? "",
    messages.length,
    isLoading ? "loading" : "idle",
  ].join(":");
  const hasVisibleStreamingMessage = messages.some(
    (message) => message.role === "assistant" && message.isStreaming,
  );

  const showStreamingFooterSkeleton = shouldShowStreamingFooterSkeleton({
    connectionStatus,
    sessionRunning,
    messageCount: messages.length,
    hasVisibleStreamingMessage,
  });

  const getGreetingKey = () => {
    const h = new Date().getHours();
    if (h < 6) return "chat.goodEvening";
    if (h < 12) return "chat.goodMorning";
    if (h < 18) return "chat.goodAfternoon";
    return "chat.goodEvening";
  };
  const greeting = user?.username
    ? t(getGreetingKey(), { name: user.username })
    : t(getGreetingKey());

  const previousSessionIdRef = useRef<string | null | undefined>(sessionId);
  const [messageListSessionKey, setMessageListSessionKey] = useState(
    sessionId ?? "__new_session__",
  );
  const [visibleRange, setVisibleRange] = useState<ListRange | null>(null);

  const {
    messagesContainerRef,
    virtuosoRef,
    virtuosoScrollerRef,
    messagesEndRef,
    isNearBottom,
    isNearTop,
    isHistoryScrollSettling,
    handleVirtuosoAtBottomChange,
    scrollToBottom,
    scrollToTop,
  } = useMessageScroll(
    messages,
    sessionId,
    externalNavigationToken,
    externalNavigationTargetFile,
    externalNavigationTargetRunId,
    externalNavigationTargetRunPending,
    externalScrollToBottom,
    isLoadingHistory,
    null,
  );

  useEffect(() => {
    const previousSessionId = previousSessionIdRef.current;
    previousSessionIdRef.current = sessionId;
    setMessageListSessionKey((previousKey) => {
      const nextKey = getNextMessageListSessionKey({
        previousSessionId,
        sessionId,
        messageCount: messages.length,
        previousKey,
      });
      return nextKey === previousKey ? previousKey : nextKey;
    });
  }, [messages.length, sessionId]);

  // --- Assistant identity ---
  const currentPersonaAvatar = useMemo(() => {
    const preset = personaPresets.find((p) => p.id === selectedPersonaPresetId);
    return preset?.avatar ?? null;
  }, [personaPresets, selectedPersonaPresetId]);
  const assistantIdentity = useChatAssistantIdentity({
    currentAgent,
    currentPersonaAvatar,
    pluginOptionValues,
    runtimePlugins,
    selectedPersonaName,
  });

  // --- Outline panel (side effects managed by hook) ---
  useChatOutline(
    messages,
    visibleRange,
    virtuosoRef,
    assistantIdentity.avatar,
    outlineToggleRef,
    t,
  );

  // --- Reveal preview ---
  const {
    activePreview,
    handleOpenPreview,
    handleClosePreview,
    handlePreviewInteraction,
    latestAutoPreview,
  } = useRevealPreview(
    messages,
    messagesContainerRef,
    scrollToBottom,
    isNearBottom,
    sessionId,
    externalNavigationToken,
    externalNavigationPreview,
    currentRunId,
    isLoadingHistory,
  );

  // --- Goal visibility ---
  const visibleActiveGoal = useMemo(
    () => getVisibleActiveGoalForMessages(activeGoal, messages),
    [activeGoal, messages],
  );
  const isMobileViewport =
    typeof window !== "undefined" ? window.innerWidth < 640 : false;
  const shouldHideHistoryMeasurementFrame =
    isLoadingHistory || isHistoryScrollSettling;

  // --- Message action handlers ---
  const handleForkMessage = useCallback(
    async (messageId: string) => {
      if (!sessionId) return;
      try {
        const response = await sessionApi.forkMessage(sessionId, messageId);
        toast.success(t("chat.message.forkSuccess"));
        navigate(`/chat/${response.session.id}`);
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : t("chat.message.forkFailed"),
        );
      }
    },
    [navigate, sessionId, t],
  );

  const handleRetryCancelledMessage = useCallback(
    (messageId: string) => {
      if (sessionRunning || !canSendMessage) {
        return;
      }

      if (!sessionId) {
        return;
      }

      const target = findCancelledRetryTarget(messages, messageId);
      if (!target) {
        return;
      }

      onSendMessage(target.content, target.attachments, {
        retryUserMessage: true,
        retryAssistantMessageId: target.assistantMessageId,
        retryAfterUserMessageId: target.userMessageId,
      });
    },
    [canSendMessage, messages, onSendMessage, sessionId, sessionRunning],
  );

  const handleRecommendQuestionClick = useCallback(
    (question: string) => {
      if (sessionRunning || !canSendMessage) {
        return;
      }
      onSendMessage(question);
    },
    [canSendMessage, onSendMessage, sessionRunning],
  );

  // --- Virtuoso rendering ---
  const handleVirtuosoRangeChanged = useCallback((range: ListRange) => {
    setVisibleRange((current) =>
      current?.startIndex === range.startIndex &&
      current?.endIndex === range.endIndex
        ? current
        : range,
    );
  }, []);
  const handleVirtuosoFollowOutput = useCallback(
    (isAtBottom: boolean) => {
      if (shouldHideHistoryMeasurementFrame) {
        return isAtBottom ? "auto" : false;
      }
      return isAtBottom ? "smooth" : false;
    },
    [shouldHideHistoryMeasurementFrame],
  );

  const virtuosoComponents = useMemo(
    () => ({
      Scroller: (
        scrollerProps: React.HTMLAttributes<HTMLDivElement> & {
          children?: React.ReactNode;
          ref?: React.Ref<HTMLDivElement>;
        },
      ) => {
        const { children, ref: vRef, ...props } = scrollerProps;
        return (
          <div
            {...props}
            className={`chat-message-scroller ${props.className ?? ""}`}
            ref={(el: HTMLDivElement | null) => {
              virtuosoScrollerRef.current = el;
              if (typeof vRef === "function") vRef(el);
              else if (vRef)
                (
                  vRef as React.MutableRefObject<HTMLDivElement | null>
                ).current = el;
            }}
          >
            {children}
          </div>
        );
      },
      Footer: () => (
        <>
          {showStreamingFooterSkeleton && (
            <div className="pb-4">
              <ChatSkeletonMessagesOnly count={3} />
            </div>
          )}
          <div
            ref={messagesEndRef}
            className={getMessageListFooterSpacerClass(isMobileViewport)}
          />
        </>
      ),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [showStreamingFooterSkeleton],
  );

  const virtuosoItemContent = useCallback(
    (index: number, message: (typeof messages)[number]) => (
      <ChatMessage
        message={message}
        sessionId={sessionId ?? undefined}
        runId={currentRunId ?? undefined}
        isLastMessage={index === messages.length - 1}
        personaAvatar={assistantIdentity.avatar}
        personaName={assistantIdentity.name}
        activePreview={activePreview}
        latestAutoPreview={latestAutoPreview}
        onOpenPreview={handleOpenPreview}
        onForkMessage={handleForkMessage}
        onRecommendQuestionClick={handleRecommendQuestionClick}
        onRetryCancelledMessage={handleRetryCancelledMessage}
        activeGoal={
          getGoalForMessage(goalsByRunId, message) ?? visibleActiveGoal
        }
        isFirst={index === 0}
        runtimePlugins={runtimePlugins}
      />
    ),
    [
      sessionId,
      currentRunId,
      messages.length,
      assistantIdentity.avatar,
      assistantIdentity.name,
      activePreview,
      latestAutoPreview,
      handleOpenPreview,
      handleForkMessage,
      handleRecommendQuestionClick,
      handleRetryCancelledMessage,
      visibleActiveGoal,
      goalsByRunId,
      runtimePlugins,
    ],
  );

  // Shared ChatInput props to avoid duplication
  const chatInputProps = {
    onSend: (
      content: string,
      _options?: Record<string, boolean | string | number>,
      sendAttachments?: MessageAttachment[],
      runOptions?: { enabledSkills?: string[] },
    ) => onSendMessage(content, sendAttachments, runOptions),
    onStop: onStopGeneration,
    isLoading: sessionRunning,
    canSend: canSendMessage,
    tools,
    onToggleTool,
    onToggleCategory,
    onToggleAll,
    toolsLoading,
    enabledToolsCount,
    totalToolsCount,
    skills,
    onToggleSkill,
    onToggleSkillCategory,
    onToggleAllSkills,
    skillsLoading,
    pendingSkillNames,
    skillsMutating,
    enabledSkillsCount,
    totalSkillsCount,
    enableSkills,
    personaPresets,
    personaPresetsTotal,
    personaPresetsPage,
    onPersonaPresetsPageChange,
    onPersonaPresetsSearchChange,
    onPersonaPresetsTagChange,
    selectedPersonaPresetId,
    selectedPersonaName,
    personaSkillsControlled,
    personaPresetsLoading,
    personaPresetsMutating,
    onUsePersonaPreset,
    onTogglePersonaPreference,
    onCopyPersonaPreset,
    onSavePersonaPreset,
    onClearPersonaPreset,
    canManagePersonaPresets,
    agentOptions,
    agentOptionValues,
    onToggleAgentOption,
    agents,
    currentAgent,
    onSelectAgent,
    selectedTeamId,
    pluginOptionValues,
    onPluginOptionChange,
    runtimePlugins,
    attachments,
    onAttachmentsChange,
  };

  return (
    <SessionImageGalleryProvider messages={messages}>
      <main
        ref={messagesContainerRef}
        className="relative flex-1 min-h-0 overflow-hidden"
      >
        {messages.length === 0 ? (
          isLoading ? (
            <ChatSkeleton count={8} />
          ) : (
            <WelcomePage
              greeting={greeting}
              subtitle={t("chat.welcomeSubtitle", "How can I help you today?")}
              refreshLabel={t("chat.welcomeRefresh", "Refresh")}
              personasLabel={t("personaPresets.title", "Personas")}
              starterPromptsLabel={t(
                "personaPresets.starterPrompts",
                "Start a conversation",
              )}
              changePersonaLabel={t("personaPresets.change", "Change persona")}
              personaPresets={personaPresets}
              hasMorePersonaPresets={hasMorePersonaPresets}
              isLoadingMorePersonaPresets={isLoadingMorePersonaPresets}
              onLoadMorePersonaPresets={onLoadMorePersonaPresets}
              selectedPersonaPresetId={selectedPersonaPresetId}
              selectedPersonaSnapshot={selectedPersonaSnapshot}
              personaPresetsLoading={personaPresetsLoading}
              personaPresetsMutating={personaPresetsMutating}
              currentAgent={currentAgent}
              selectedTeamId={selectedTeamId}
              canSendMessage={canSendMessage}
              chatInputProps={chatInputProps}
              activeGoal={visibleActiveGoal}
              onClearActiveGoal={onClearActiveGoal}
              onUsePersonaPreset={onUsePersonaPreset}
              onClearPersonaPreset={onClearPersonaPreset}
            />
          )
        ) : (
          <>
            <Virtuoso
              key={messageListSessionKey}
              ref={virtuosoRef}
              className={`dark:divide-stone-800 overflow-x-hidden ${
                shouldHideHistoryMeasurementFrame
                  ? "chat-history-scroll-settling"
                  : ""
              }`}
              data={messages}
              computeItemKey={(_, message) => message.id}
              atBottomStateChange={handleVirtuosoAtBottomChange}
              atBottomThreshold={getAtBottomThresholdPx(isMobileViewport)}
              followOutput={handleVirtuosoFollowOutput}
              rangeChanged={handleVirtuosoRangeChanged}
              components={virtuosoComponents}
              itemContent={virtuosoItemContent}
              initialTopMostItemIndex={getInitialBottomItemLocation(
                messages.length,
              )}
            />
            {shouldHideHistoryMeasurementFrame && (
              <div className="chat-history-settling-overlay">
                <ChatSkeletonMessagesOnly count={8} />
              </div>
            )}
          </>
        )}
      </main>

      <ApprovalPanel
        approvals={approvals}
        onRespond={onRespondApproval}
        isLoading={approvalLoading}
      />

      <RevealPreviewHost
        preview={activePreview}
        onClose={() => handleClosePreview(true)}
        onUserInteraction={handlePreviewInteraction}
        runtimePlugins={runtimePlugins}
      />
      <AttachmentPreviewHost runtimePlugins={runtimePlugins} />
      <PersistentToolPanelHost />

      {/* ChatInput at bottom (when messages exist, WelcomePage renders its own) */}
      {messages.length > 0 && (
        <div className="relative">
          <div
            className={`absolute ${FLOATING_SCROLL_BUTTON_OFFSET_CLASS} right-2 z-50 flex flex-col gap-2 sm:right-4`}
          >
            <SessionScheduledTasksButton
              sessionId={sessionId}
              refreshKey={scheduledTasksRefreshKey}
              className="group/btn flex h-9 w-9 items-center justify-center rounded-full border border-[var(--theme-border)] bg-[var(--theme-bg-card)]/90 text-theme-text-secondary shadow-[0_2px_8px_-2px_rgb(0_0_0/0.08),0_4px_16px_-4px_rgb(0_0_0/0.04)] transition-all duration-300 hover:-translate-y-0.5 hover:bg-[var(--glass-bg-subtle)] hover:text-theme-text hover:shadow-[0_4px_12px_-2px_rgb(0_0_0/0.12),0_8px_24px_-4px_rgb(0_0_0/0.08)] active:scale-95 dark:bg-[var(--theme-bg-card)]/80 dark:shadow-[0_2px_8px_-2px_rgb(0_0_0/0.3),0_4px_16px_-4px_rgb(0_0_0/0.2)] dark:hover:shadow-[0_4px_12px_-2px_rgb(0_0_0/0.4),0_8px_24px_-4px_rgb(0_0_0/0.3)] sm:h-10 sm:w-10"
            />
            <button
              onClick={scrollToTop}
              className="group/btn flex h-9 w-9 items-center justify-center rounded-full border border-[var(--theme-border)] bg-[var(--theme-bg-card)]/90 shadow-[0_2px_8px_-2px_rgb(0_0_0/0.08),0_4px_16px_-4px_rgb(0_0_0/0.04)] transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_4px_12px_-2px_rgb(0_0_0/0.12),0_8px_24px_-4px_rgb(0_0_0/0.08)] active:scale-95 dark:bg-[var(--theme-bg-card)]/80 dark:shadow-[0_2px_8px_-2px_rgb(0_0_0/0.3),0_4px_16px_-4px_rgb(0_0_0/0.2)] dark:hover:shadow-[0_4px_12px_-2px_rgb(0_0_0/0.4),0_8px_24px_-4px_rgb(0_0_0/0.3)] sm:h-10 sm:w-10"
              style={{
                opacity: isNearTop ? 0 : 1,
                transform: isNearTop ? "translateY(6px)" : "translateY(0)",
                pointerEvents: isNearTop ? "none" : "auto",
              }}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
                className="w-4 h-4 sm:w-[18px] sm:h-[18px] text-[var(--theme-text-tertiary)] group-hover/btn:text-[var(--theme-text-secondary)] transition-colors duration-200"
              >
                <path
                  fillRule="evenodd"
                  d="M10 17a.75.75 0 01-.75-.75V5.612l-3.96 4.158a.75.75 0 11-1.08-1.04l5.25-5.5a.75.75 0 011.08 0l5.25 5.5a.75.75 0 11-1.08 1.04l-3.96-4.158V16.25A.75.75 0 0110 17z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
            <button
              onClick={scrollToBottom}
              className={`group/btn flex h-9 w-9 items-center justify-center rounded-full border border-[var(--theme-border)] bg-[var(--theme-bg-card)]/90 shadow-[0_2px_8px_-2px_rgb(0_0_0/0.08),0_4px_16px_-4px_rgb(0_0_0/0.04)] transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_4px_12px_-2px_rgb(0_0_0/0.12),0_8px_24px_-4px_rgb(0_0_0/0.08)] active:scale-95 dark:bg-[var(--theme-bg-card)]/80 dark:shadow-[0_2px_8px_-2px_rgb(0_0_0/0.3),0_4px_16px_-4px_rgb(0_0_0/0.2)] dark:hover:shadow-[0_4px_12px_-2px_rgb(0_0_0/0.4),0_8px_24px_-4px_rgb(0_0_0/0.3)] sm:h-10 sm:w-10 ${
                hasVisibleStreamingMessage ? "scroll-btn-glow" : ""
              }`}
              style={{
                opacity: isNearBottom ? 0 : 1,
                transform: isNearBottom ? "translateY(6px)" : "translateY(0)",
                pointerEvents: isNearBottom ? "none" : "auto",
              }}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
                className="w-4 h-4 sm:w-[18px] sm:h-[18px] text-[var(--theme-text-tertiary)] group-hover/btn:text-[var(--theme-text-secondary)] transition-colors duration-200"
              >
                <path
                  fillRule="evenodd"
                  d="M10 3a.75.75 0 01.75.75v10.638l3.96-4.158a.75.75 0 111.08 1.04l-5.25 5.5a.75.75 0 01-1.08 0l-5.25-5.5a.75.75 0 111.08-1.04l3.96 4.158V3.75A.75.75 0 0110 3z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
          </div>
          <ChatInput
            {...chatInputProps}
            activeGoal={visibleActiveGoal}
            onClearActiveGoal={onClearActiveGoal}
            goalLabel={t("chat.goal.active", "Goal")}
            goalDurationLabel={t("chat.goal.running", "Running")}
            goalClearLabel={t("chat.goal.clear", "Clear goal")}
            showHelpMenu
            helpMenuClassName="hidden sm:block"
          />
        </div>
      )}
    </SessionImageGalleryProvider>
  );
}
