import { useMemo, useCallback, useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import i18n from "../../../i18n";
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
import { Virtuoso, type ListRange, type VirtuosoHandle } from "react-virtuoso";
import { ApprovalPanel } from "../../panels/ApprovalPanel";
import { setSteerCancelHandler } from "../../chat/steerCancelStore";
import { SessionScheduledTasksButton } from "../../panels/ScheduledTaskPanel";
import {
  ChatSkeleton,
  ChatSkeletonMessagesOnly,
} from "../../skeletons/ChatSkeletons";
import { useMessageScroll } from "./useMessageScroll";
import {
  createInitialStartReachedSkipper,
  getAtBottomThresholdPx,
  getMessageListFooterSpacerClass,
  shouldPreloadOlderHistory,
} from "./messageScrollUtils";
import { getNextMessageListSessionKey } from "./useMessageScroll";
import {
  toDataIndex,
  translateVirtuosoRange,
  wrapVirtuosoHandleForDataIndices,
} from "./virtuosoIndexOffset";
import {
  isSessionRunning,
  shouldShowStreamingFooterSkeleton,
} from "./sessionState";
import type { Message, MessageAttachment } from "../../../types";
import type { ChatViewProps } from "./ChatViewProps";
import { useCurrentTeam, resolveChatAssistantIdentity } from "./ChatViewProps";
import { useChatOutline } from "./useChatOutline";
import { resolveAgentDisplayName } from "../../agent/agentCatalog";
import { shouldShowMessageOutline } from "./messageOutline";
import {
  MessageTimelineRail,
  updateTimelineRange,
} from "./MessageTimelineRail";
import { useRevealPreview } from "./useRevealPreview";
import { findCancelledRetryTarget } from "../../chat/ChatMessage/cancelledRetry";
import {
  getGoalForMessage,
  getVisibleActiveGoalForMessages,
} from "../../chat/goalVisibility";
import { sessionApi } from "../../../services/api";
import {
  syncToolCallPanelStore,
  toolCallPanelStore,
} from "../../chat/ChatMessage/toolCallPanelStore";
import { hasPendingAskHuman } from "../../../hooks/useAgent/messageParts";

const FLOATING_SCROLL_BUTTON_OFFSET_CLASS = "bottom-full mb-3";
// Virtuoso 反向无限滚动的起始索引：前插旧消息时递减 firstItemIndex，
// Virtuoso 会保持可视区滚动位置不跳动
const HISTORY_FIRST_ITEM_INDEX = 1_000_000;

export function ChatView({
  messages,
  sessionId,
  currentRunId,
  isLoading,
  isLoadingHistory,
  historyLoadGeneration,
  hasMoreHistoryTraces = false,
  isLoadingOlderHistory = false,
  onLoadOlderHistory,
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
  modelSupportsThinking,
  agents,
  currentAgent,
  onSelectAgent,
  selectedTeamId,
  onSelectTeam,
  onOpenTeamBuilder,
  approvals,
  onRespondApproval,
  approvalLoading,
  onSendMessage,
  onStopGeneration,
  onSteerMessage,
  steerMessages,
  onCancelSteer,
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
  autoModeEnabled = false,
  goalModeEnabled = false,
  onToggleAutoMode,
  onToggleGoalMode,
}: ChatViewProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const sessionRunning = isSessionRunning(messages, isLoading);
  const hasPendingAskHumanApproval = approvals.some(
    (approval) => approval.metadata?.mode === "interrupt",
  );
  const scheduledTasksRefreshKey = [
    sessionId ?? "",
    currentRunId ?? "",
    messages.length,
    isLoading ? "loading" : "idle",
  ].join(":");
  const hasVisibleStreamingMessage = messages.some(
    (message) => message.role === "assistant" && message.isStreaming,
  );

  useEffect(() => {
    toolCallPanelStore.clear();
  }, [sessionId]);

  useEffect(() => {
    syncToolCallPanelStore(messages);
  }, [messages]);

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

  // --- Older-history pagination (reverse infinite scroll) ---
  // Virtuoso 的 firstItemIndex 反向无限滚动：前插旧消息时递减 firstItemIndex，
  // Virtuoso 保持可视区滚动位置不跳动。Virtuoso 对外的索引是绝对索引，
  // 与数据索引的换算集中在 virtuosoIndexOffset。
  const [firstItemIndex, setFirstItemIndex] = useState(
    HISTORY_FIRST_ITEM_INDEX,
  );
  const firstItemIndexRef = useRef(firstItemIndex);
  useEffect(() => {
    firstItemIndexRef.current = firstItemIndex;
  }, [firstItemIndex]);
  const prevRenderItemsRef = useRef<Message[]>([]);
  // firstItemIndex 必须与前插数据落在同一次 commit：若放到事后 effect 里
  // 修正，中间那一帧会被 Virtuoso 当成顶部插入，滚动位置被重置——表现
  // 就是上滑加载更早消息时视口跳回列表顶部。渲染期 setState 会让 React
  // 丢弃本帧、带着新锚点立即重渲，两处变更同帧生效。
  const previousFirstMessageId = prevRenderItemsRef.current[0]?.id;
  const prependCount =
    previousFirstMessageId !== undefined &&
    messages.length > 0 &&
    messages[0].id !== previousFirstMessageId
      ? messages.findIndex((message) => message.id === previousFirstMessageId)
      : -1;
  if (prependCount > 0) {
    // ref 与 state 同帧更新：rangeChanged 的换算读 ref，父组件的
    // useEffect 晚于 Virtuoso 的事件发射，靠 effect 同步会留一帧用旧
    // 基准换算的窗口（dataRange 偏移一个分页量，时间轴点亮错位）。
    const nextFirstItemIndex = Math.max(
      0,
      firstItemIndexRef.current - prependCount,
    );
    firstItemIndexRef.current = nextFirstItemIndex;
    setFirstItemIndex(nextFirstItemIndex);
  }
  prevRenderItemsRef.current = messages;

  const {
    messagesContainerRef,
    virtuosoRef,
    handleVirtuosoScrollerElementChange,
    messagesEndRef,
    isNearBottom,
    isNearTop,
    manualDetachFromStreamRef,
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
    historyLoadGeneration,
    null,
  );

  // 大纲/时间轴按数据索引调用 scrollToIndex；该 API 原生就期望数据索引
  // （与 rangeChanged 上报的绝对索引不对称），适配器只做语义透传
  const dataIndexVirtuosoRef = useMemo<React.RefObject<VirtuosoHandle | null>>(
    () => ({
      get current() {
        const handle = virtuosoRef.current;
        return handle ? wrapVirtuosoHandleForDataIndices(handle) : null;
      },
    }),
    [virtuosoRef],
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

  // Virtuoso 挂载时列表初始位于顶部（自动滚到底部之前），startReached 会
  // 误触发一次；loading 标志此刻已清空，拦不住，须按 remount 粒度忽略。
  const startReachedSkipperRef = useRef(createInitialStartReachedSkipper());
  const prevVisibleStartIndexRef = useRef<number | null>(null);
  const prevMessageListSessionKeyRef = useRef(messageListSessionKey);
  if (prevMessageListSessionKeyRef.current !== messageListSessionKey) {
    prevMessageListSessionKeyRef.current = messageListSessionKey;
    // 在渲染阶段恢复跳过（而非 effect），确保先于新列表挂载期间
    // Virtuoso 上报的那次 startReached；近顶预加载的首报基准一并重置。
    startReachedSkipperRef.current.reset();
    prevVisibleStartIndexRef.current = null;
  }

  const handleVirtuosoStartReached = useCallback(() => {
    if (startReachedSkipperRef.current.shouldSkip()) return;
    // 历史整页加载期间列表也可能短暂处于顶部，此时不自动翻页
    if (isLoadingHistory || isLoadingOlderHistory || !hasMoreHistoryTraces) {
      return;
    }
    onLoadOlderHistory?.();
  }, [
    hasMoreHistoryTraces,
    isLoadingHistory,
    isLoadingOlderHistory,
    onLoadOlderHistory,
  ]);

  // --- Assistant identity ---
  const currentPersonaAvatar = useMemo(() => {
    const preset = personaPresets.find((p) => p.id === selectedPersonaPresetId);
    return preset?.avatar ?? null;
  }, [personaPresets, selectedPersonaPresetId]);
  const currentTeam = useCurrentTeam(currentAgent, selectedTeamId);
  const currentAgentInfo = agents.find((a) => a.id === currentAgent);
  const currentAgentDisplayName = currentAgentInfo
    ? resolveAgentDisplayName(currentAgentInfo, i18n.language, t)
    : null;
  const assistantIdentity = useMemo(
    () =>
      resolveChatAssistantIdentity({
        currentAgent,
        currentPersonaAvatar,
        currentTeam,
        selectedPersonaName,
        agentDisplayName: currentAgentDisplayName,
      }),
    [
      currentAgent,
      currentPersonaAvatar,
      currentTeam,
      selectedPersonaName,
      currentAgentDisplayName,
    ],
  );

  // --- Outline panel (side effects managed by hook) ---
  const { outlineItems, handleVisibleRangeChange: handleOutlineRangeChange } =
    useChatOutline(
      messages,
      dataIndexVirtuosoRef,
      assistantIdentity.avatar,
      outlineToggleRef,
      t,
    );

  // --- Timeline rail (mini-map navigation strip) ---
  const showTimelineRail = shouldShowMessageOutline(messages);

  const handleVisibleRangeChange = useCallback(
    (range: ListRange) => {
      const dataRange = translateVirtuosoRange(
        range,
        firstItemIndexRef.current,
      );
      handleOutlineRangeChange(dataRange);
      updateTimelineRange(dataRange);
      // 近顶自动预加载更早一页（无边滑动）：用户上滑进入距顶阈值即触发，
      // 通常无需看到「加载更早的消息」按钮；挂载/换会话首报不触发。
      if (
        shouldPreloadOlderHistory({
          startIndex: dataRange.startIndex,
          previousStartIndex: prevVisibleStartIndexRef.current,
          isLoading: isLoadingHistory,
          isLoadingOlder: isLoadingOlderHistory,
          hasMore: hasMoreHistoryTraces,
        })
      ) {
        onLoadOlderHistory?.();
      }
      prevVisibleStartIndexRef.current = dataRange.startIndex;
    },
    [
      handleOutlineRangeChange,
      hasMoreHistoryTraces,
      isLoadingHistory,
      isLoadingOlderHistory,
      onLoadOlderHistory,
    ],
  );

  const handleTimelineNavigate = useCallback(
    (anchorId: string, messageIndex: number) => {
      // 瞬时跳转：smooth 在长虚拟列表上是「估算→滚动→测量→修正」多段
      // 迭代，表现为长时间停顿后缓慢爬行；小地图点击应立即到位。
      // offset: -24 等效消息行的 scroll-mt-6 留白，一次滚动到位；不追加
      // rAF scrollIntoView——它与 scrollToIndex 的测量修正竞争，远距离
      // 条目按过期布局二次滚动会冲过头一轮（点亮落在点击轮的下一轮）。
      dataIndexVirtuosoRef.current?.scrollToIndex({
        index: messageIndex,
        behavior: "auto",
        align: "start",
        offset: -24,
      });
      requestAnimationFrame(() => {
        const el = document.getElementById(anchorId);
        if (el) {
          el.setAttribute("data-external-navigation-highlighted", "true");
          setTimeout(() => {
            el.removeAttribute("data-external-navigation-highlighted");
          }, 1600);
        }
      });
    },
    [dataIndexVirtuosoRef],
  );

  // --- Reveal preview ---
  const {
    activePreview,
    activePreviewAutomatic,
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

      const target = findCancelledRetryTarget(messages, messageId);
      if (!target) {
        return;
      }

      onSendMessage(target.content, target.attachments);
    },
    [canSendMessage, messages, onSendMessage, sessionRunning],
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
  const handleVirtuosoFollowOutput = useCallback(
    (isAtBottom: boolean) => {
      if (isLoadingHistory) {
        return isAtBottom ? "auto" : false;
      }
      // When the user has explicitly scrolled up during streaming, do not let
      // Virtuoso's built-in followOutput pull the view back to the bottom.
      if (manualDetachFromStreamRef.current) {
        return false;
      }
      return isAtBottom ? "smooth" : false;
    },
    [isLoadingHistory, manualDetachFromStreamRef],
  );

  // The Scroller identity must stay stable for the lifetime of the list:
  // react-virtuoso remounts the whole scroller subtree (resetting scroll to
  // the first message) whenever components.Scroller changes identity. The
  // completion commit — streaming stops + connectionStatus flips to
  // "disconnected" while isLoading is still true until sendMessage's finally
  // runs — toggles the skeleton flag, which must never reach the Scroller.
  // Only the Footer may be recreated; its remount cannot move scroll position.
  const virtuosoScrollerComponent = useCallback(
    (
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
            handleVirtuosoScrollerElementChange(el);
            if (typeof vRef === "function") vRef(el);
            else if (vRef)
              (vRef as React.MutableRefObject<HTMLDivElement | null>).current =
                el;
          }}
        >
          {children}
        </div>
      );
    },
    [handleVirtuosoScrollerElementChange],
  );

  const virtuosoFooterComponent = useCallback(
    () => (
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
    [showStreamingFooterSkeleton, isMobileViewport, messagesEndRef],
  );

  const virtuosoHeaderComponent = useCallback(() => {
    if (!hasMoreHistoryTraces && !isLoadingOlderHistory) return null;
    return (
      <div className="flex justify-center py-3">
        {isLoadingOlderHistory ? (
          <span className="text-xs text-[var(--theme-text-tertiary)]">
            {t("chat.historyLoadingOlder", "正在加载更早的消息…")}
          </span>
        ) : (
          <button
            type="button"
            onClick={() => void onLoadOlderHistory?.()}
            className="rounded-full border border-[var(--theme-border)] px-4 py-1.5 text-xs text-[var(--theme-text-secondary)] transition-colors hover:bg-[var(--glass-bg-subtle)]"
          >
            {t("chat.historyLoadOlder", "加载更早的消息")}
          </button>
        )}
      </div>
    );
  }, [hasMoreHistoryTraces, isLoadingOlderHistory, onLoadOlderHistory, t]);

  const virtuosoComponents = useMemo(
    () => ({
      Scroller: virtuosoScrollerComponent,
      Header: virtuosoHeaderComponent,
      Footer: virtuosoFooterComponent,
    }),
    [
      virtuosoScrollerComponent,
      virtuosoHeaderComponent,
      virtuosoFooterComponent,
    ],
  );

  // Pending steer items belong to the composer queue, not the conversation
  // timeline. Delivered steer events are written into `messages` by SSE.
  const renderItems = messages;

  const virtuosoItemContent = useCallback(
    (index: number, message: (typeof messages)[number]) => (
      <ChatMessage
        message={message}
        sessionId={sessionId ?? undefined}
        runId={currentRunId ?? undefined}
        isLastMessage={
          toDataIndex(index, firstItemIndexRef.current) ===
          renderItems.length - 1
        }
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
        isFirst={toDataIndex(index, firstItemIndexRef.current) === 0}
      />
    ),
    [
      sessionId,
      currentRunId,
      renderItems.length,
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
    ],
  );

  useEffect(() => {
    setSteerCancelHandler(
      (content, messageId) => onCancelSteer?.(content, messageId),
    );
    return () => setSteerCancelHandler(null);
  }, [onCancelSteer]);

  // Shared ChatInput props to avoid duplication
  const chatInputProps = {
    onSend: (
      content: string,
      _options?: Record<string, boolean | string | number>,
      sendAttachments?: MessageAttachment[],
      runOptions?: { enabledSkills?: string[] },
      submissionCallbacks?: Parameters<ChatViewProps["onSendMessage"]>[3],
    ) =>
      onSendMessage(content, sendAttachments, runOptions, submissionCallbacks),
    onStop: onStopGeneration,
    onSteer: onSteerMessage,
    steerMessages,
    onCancelSteer,
    isLoading: sessionRunning,
    sendBlocked:
      approvals.length > 0 ||
      hasPendingAskHuman(messages.flatMap((message) => message.parts ?? [])),
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
    modelSupportsThinking,
    agents,
    currentAgent,
    onSelectAgent,
    selectedTeamId,
    onSelectTeam,
    onOpenTeamBuilder,
    attachments,
    onAttachmentsChange,
    autoModeEnabled,
    goalModeEnabled,
    onToggleAutoMode,
    onToggleGoalMode,
  };

  return (
    <SessionImageGalleryProvider messages={messages}>
      <div className="chat-view-content-region flex min-h-0 flex-1 flex-col overflow-hidden">
        <main
          ref={messagesContainerRef}
          className="relative flex-1 min-h-0 overflow-hidden"
        >
          {/* Frosted glass fade mask — visual transition between messages and input */}
          <div
            className="pointer-events-none absolute bottom-0 left-0 right-0 z-10"
            style={{
              height: 48,
              background:
                "linear-gradient(to bottom, transparent, var(--theme-bg))",
            }}
          />
          {messages.length === 0 ? (
            isLoading ? (
              <ChatSkeleton count={8} />
            ) : (
              <WelcomePage
                greeting={greeting}
                subtitle={t(
                  "chat.welcomeSubtitle",
                  "How can I help you today?",
                )}
                refreshLabel={t("chat.welcomeRefresh", "Refresh")}
                personasLabel={t("personaPresets.title", "Personas")}
                starterPromptsLabel={t(
                  "personaPresets.starterPrompts",
                  "Start a conversation",
                )}
                changePersonaLabel={t(
                  "personaPresets.change",
                  "Change persona",
                )}
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
                onSelectTeam={onSelectTeam}
              />
            )
          ) : (
            <Virtuoso
              key={messageListSessionKey}
              ref={virtuosoRef}
              className="dark:divide-stone-800 overflow-x-hidden"
              style={undefined}
              data={renderItems}
              computeItemKey={(_, message) => message.id}
              firstItemIndex={firstItemIndex}
              startReached={handleVirtuosoStartReached}
              atBottomStateChange={handleVirtuosoAtBottomChange}
              atBottomThreshold={getAtBottomThresholdPx(isMobileViewport)}
              followOutput={handleVirtuosoFollowOutput}
              rangeChanged={handleVisibleRangeChange}
              components={virtuosoComponents}
              itemContent={virtuosoItemContent}
            />
          )}
          {showTimelineRail && (
            <MessageTimelineRail
              items={outlineItems}
              onNavigate={handleTimelineNavigate}
            />
          )}
        </main>

        <RevealPreviewHost
          preview={activePreview}
          automatic={activePreviewAutomatic}
          onClose={() => handleClosePreview(true)}
          onUserInteraction={handlePreviewInteraction}
        />
        <AttachmentPreviewHost />
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
                className="group/btn flex h-9 w-9 items-center justify-center rounded-full border border-[var(--theme-border)] bg-[var(--theme-bg-card)]/90 text-theme-text-secondary transition-all duration-300 hover:-translate-y-0.5 hover:bg-[var(--glass-bg-subtle)] hover:text-theme-text active:scale-95 sm:h-10 sm:w-10"
              />
              <button
                onClick={scrollToTop}
                className="group/btn flex h-9 w-9 items-center justify-center rounded-full border border-[var(--theme-border)] bg-[var(--theme-bg-card)]/90 transition-all duration-300 hover:-translate-y-0.5 active:scale-95 sm:h-10 sm:w-10"
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
                className={`group/btn flex h-9 w-9 items-center justify-center rounded-full border border-[var(--theme-border)] bg-[var(--theme-bg-card)]/90 transition-all duration-300 hover:-translate-y-0.5 active:scale-95 sm:h-10 sm:w-10 ${
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
            {approvals.length > 0 && (
              <div className="approval-panel-scroll-region flex min-h-0 w-full shrink-0 flex-col overflow-hidden">
                <ApprovalPanel
                  approvals={approvals}
                  onRespond={onRespondApproval}
                  isLoading={approvalLoading}
                />
              </div>
            )}
            {!hasPendingAskHumanApproval && (
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
            )}
          </div>
        )}
      </div>
    </SessionImageGalleryProvider>
  );
}
