import { useMemo, useCallback, useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { ListTree } from "lucide-react";
import { useAuth } from "../../../hooks/useAuth";
import { ChatMessage } from "../../chat/ChatMessage";
import { AttachmentPreviewHost } from "../../chat/AttachmentPreviewHost";
import { RevealPreviewHost } from "../../chat/ChatMessage/items/RevealPreviewHost";
import {
  PersistentToolPanelHost,
  closePersistentToolPanel,
  openPersistentToolPanel,
  isPersistentToolPanelOpen,
  updatePersistentToolPanel,
  type PersistentToolPanelState,
} from "../../chat/ChatMessage/items/persistentToolPanelState";
import { ChatInput } from "../../chat/ChatInput";
import { WelcomePage } from "../../chat/WelcomePage";
import { Virtuoso } from "react-virtuoso";
import { ApprovalPanel } from "../../panels/ApprovalPanel";
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
  shouldShowMessageOutline,
  extractMessageOutline,
} from "./messageOutline";
import { useActiveOutlineItem } from "./useActiveOutlineItem";
import { MessageOutlinePanel } from "./MessageOutlinePanel";
import {
  isSessionRunning,
  shouldShowStreamingFooterSkeleton,
} from "./sessionState";
import type {
  Message,
  PendingApproval,
  ToolState,
  SkillResponse,
  SkillSource,
  ToolCategory,
  AgentOption,
  MessageAttachment,
  ConnectionStatus,
} from "../../../types";
import type { RevealPreviewRequest } from "../../chat/ChatMessage/items/revealPreviewData";
import { clearFileRevealAutoOpenState } from "../../chat/ChatMessage/items/fileRevealAutoOpen";
import { clearProjectRevealAutoOpenState } from "../../chat/ChatMessage/items/projectRevealAutoOpen";
import { getLatestChatAutoPreviewTarget } from "../../chat/ChatMessage/autoPreviewEligibility";
import {
  createActiveRevealPreviewState,
  markRevealPreviewInteracted,
  shouldAcceptRevealPreviewOpen,
  type ActiveRevealPreviewState,
  type RevealPreviewOpenSource,
} from "../../chat/ChatMessage/items/revealPreviewState";
import {
  getActiveRevealPreviewState,
  setActiveRevealPreviewState,
  subscribeActiveRevealPreviewState,
  updateActiveRevealPreviewState,
} from "../../chat/ChatMessage/items/activeRevealPreviewStore";
import type { ExternalNavigationTargetFile } from "./externalNavigationState";
import { shouldOpenExternalNavigationPreview } from "./externalNavigationState";

interface ChatViewProps {
  messages: Message[];
  sessionId: string | null;
  sessionName: string | null;
  currentRunId: string | null;
  isLoading: boolean;
  isLoadingHistory: boolean;
  connectionStatus?: ConnectionStatus;
  canSendMessage: boolean;
  tools: ToolState[];
  onToggleTool: (name: string) => void;
  onToggleCategory: (category: ToolCategory, enabled: boolean) => void;
  onToggleAll: (enabled: boolean) => void;
  toolsLoading: boolean;
  enabledToolsCount: number;
  totalToolsCount: number;
  skills: SkillResponse[];
  onToggleSkill: (name: string) => Promise<boolean>;
  onToggleSkillCategory: (
    category: SkillSource,
    enabled: boolean,
  ) => Promise<boolean>;
  onToggleAllSkills: (enabled: boolean) => Promise<boolean>;
  skillsLoading: boolean;
  pendingSkillNames: string[];
  skillsMutating: boolean;
  enabledSkillsCount: number;
  totalSkillsCount: number;
  enableSkills: boolean;
  agentOptions: Record<string, AgentOption>;
  agentOptionValues: Record<string, boolean | string | number>;
  onToggleAgentOption: (key: string, value: boolean | string | number) => void;
  // Agent mode selector
  agents: { id: string; name: string; description: string }[];
  currentAgent: string;
  onSelectAgent: (id: string) => void;
  approvals: PendingApproval[];
  onRespondApproval: (
    id: string,
    response: Record<string, unknown>,
    approved: boolean,
  ) => void;
  approvalLoading: boolean;
  onSendMessage: (content: string) => void;
  onStopGeneration: () => void;
  attachments: MessageAttachment[];
  onAttachmentsChange: React.Dispatch<
    React.SetStateAction<MessageAttachment[]>
  >;
  settings: {
    settings?: { frontend?: Array<{ key: string; value: unknown }> };
  };
  i18n: { language?: string };
  externalNavigationToken?: string | null;
  externalNavigationTargetFile?: ExternalNavigationTargetFile | null;
  externalNavigationPreview?: RevealPreviewRequest | null;
  externalNavigationTargetRunId?: string | null;
  externalNavigationTargetRunPending?: boolean;
  externalScrollToBottom?: boolean;
  outlineToggleRef?: React.RefObject<(() => void) | null>;
}

export function ChatView({
  messages,
  sessionId,
  sessionName,
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
  agentOptions,
  agentOptionValues,
  onToggleAgentOption,
  agents,
  currentAgent,
  onSelectAgent,
  approvals,
  onRespondApproval,
  approvalLoading,
  onSendMessage,
  onStopGeneration,
  attachments,
  onAttachmentsChange,
  settings,
  i18n,
  externalNavigationToken,
  externalNavigationTargetFile,
  externalNavigationPreview,
  externalNavigationTargetRunId,
  externalNavigationTargetRunPending,
  externalScrollToBottom,
  outlineToggleRef,
}: ChatViewProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const sessionRunning = isSessionRunning(messages, isLoading);
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

  const showOutline = shouldShowMessageOutline(messages);
  const outlineItems = useMemo(
    () => (showOutline ? extractMessageOutline(messages) : []),
    [messages, showOutline],
  );

  const {
    messagesContainerRef,
    virtuosoRef,
    virtuosoScrollerRef,
    messagesEndRef,
    isNearBottom,
    showScrollTop,
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
  );
  const previousSessionIdRef = useRef<string | null | undefined>(sessionId);
  const messageListSessionKeyRef = useRef(sessionId ?? "__new_session__");

  useEffect(() => {
    const previousSessionId = previousSessionIdRef.current;
    messageListSessionKeyRef.current = getNextMessageListSessionKey({
      previousSessionId,
      sessionId,
      messageCount: messages.length,
      previousKey: messageListSessionKeyRef.current,
    });
    previousSessionIdRef.current = sessionId;
  }, [messages.length, sessionId]);

  const activeOutlineId = useActiveOutlineItem(
    outlineItems,
    virtuosoScrollerRef,
  );

  const handleOutlineNavigate = useCallback(
    (anchorId: string, messageIndex: number) => {
      virtuosoRef.current?.scrollToIndex({
        index: messageIndex,
        behavior: "smooth",
        align: "start",
      });
      // After Virtuoso renders the message, scroll to the specific heading anchor
      requestAnimationFrame(() => {
        const el = document.getElementById(anchorId);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
      requestAnimationFrame(() => {
        closePersistentToolPanel();
      });
    },
    [virtuosoRef],
  );

  const handleOpenOutline = useCallback(() => {
    if (isPersistentToolPanelOpen("outline")) {
      closePersistentToolPanel();
      return;
    }
    const isMobile = window.innerWidth < 640;
    openPersistentToolPanel({
      title: t("chat.outline"),
      icon: <ListTree size={18} strokeWidth={2} />,
      status: "idle",
      panelKey: "outline",
      viewMode: isMobile ? "center" : "sidebar",
      children: (
        <MessageOutlinePanel
          items={outlineItems}
          activeId={activeOutlineId}
          onNavigate={handleOutlineNavigate}
        />
      ),
    });
  }, [outlineItems, activeOutlineId, handleOutlineNavigate, t]);

  useEffect(() => {
    if (outlineToggleRef) {
      outlineToggleRef.current = showOutline ? handleOpenOutline : null;
    }
  }, [outlineToggleRef, showOutline, handleOpenOutline]);

  useEffect(() => {
    if (!isPersistentToolPanelOpen("outline")) return;
    updatePersistentToolPanel(
      (prev: PersistentToolPanelState) => ({
        ...prev,
        children: (
          <MessageOutlinePanel
            items={outlineItems}
            activeId={activeOutlineId}
            onNavigate={handleOutlineNavigate}
          />
        ),
      }),
      "outline",
    );
  }, [outlineItems, activeOutlineId, handleOutlineNavigate]);

  const [, forcePreviewRender] = useState(0);
  const activePreviewStateRef = useRef<ActiveRevealPreviewState | null>(
    getActiveRevealPreviewState(),
  );
  const dismissedPreviewKeysRef = useRef<Set<string>>(new Set());
  const handledExternalPreviewRef = useRef<{
    token: string | null;
    sessionId: string | null;
  }>({
    token: null,
    sessionId: null,
  });
  const externalPreviewActiveRef = useRef(false);
  const activePreview = activePreviewStateRef.current?.request ?? null;

  useEffect(() => {
    const syncPreviewState = () => {
      activePreviewStateRef.current = getActiveRevealPreviewState();
      forcePreviewRender((count) => count + 1);
    };

    return subscribeActiveRevealPreviewState(syncPreviewState);
  }, []);

  const handleOpenPreview = useCallback(
    (
      preview: RevealPreviewRequest,
      source: RevealPreviewOpenSource = "manual",
    ) => {
      // Block auto-open when an external navigation preview is active
      if (source === "auto" && externalPreviewActiveRef.current) {
        return false;
      }

      const shouldOpen = shouldAcceptRevealPreviewOpen({
        activePreview: activePreviewStateRef.current,
        nextPreview: preview,
        source,
        dismissedPreviewKeys: dismissedPreviewKeysRef.current,
      });

      if (!shouldOpen) {
        return false;
      }

      if (source !== "auto") {
        dismissedPreviewKeysRef.current.delete(preview.previewKey);
      }

      setActiveRevealPreviewState(
        createActiveRevealPreviewState(preview, source),
      );
      return true;
    },
    [],
  );

  const handleClosePreview = useCallback((dismiss = true) => {
    const currentPreview = activePreviewStateRef.current;
    if (dismiss && currentPreview) {
      dismissedPreviewKeysRef.current.add(currentPreview.request.previewKey);
    }
    externalPreviewActiveRef.current = false;
    setActiveRevealPreviewState(null);
  }, []);

  const handlePreviewInteraction = useCallback(() => {
    updateActiveRevealPreviewState((current) =>
      markRevealPreviewInteracted(current),
    );
  }, []);

  useEffect(() => {
    dismissedPreviewKeysRef.current.clear();
    clearFileRevealAutoOpenState();
    clearProjectRevealAutoOpenState();
    setActiveRevealPreviewState(null);
    externalPreviewActiveRef.current = false;
    closePersistentToolPanel();
  }, [sessionId]);

  useEffect(() => {
    if (
      !shouldOpenExternalNavigationPreview({
        externalNavigationToken,
        externalNavigationPreview,
        handledToken: handledExternalPreviewRef.current.token,
        handledSessionId: handledExternalPreviewRef.current.sessionId,
        sessionId,
      })
    ) {
      return;
    }

    if (typeof window !== "undefined" && window.innerWidth < 640) {
      return;
    }

    if (!externalNavigationToken || !externalNavigationPreview) {
      return;
    }

    const opened = handleOpenPreview(externalNavigationPreview, "external");
    if (!opened) {
      return;
    }

    handledExternalPreviewRef.current = {
      token: externalNavigationToken,
      sessionId: sessionId ?? null,
    };
    externalPreviewActiveRef.current = true;
  }, [
    externalNavigationToken,
    externalNavigationPreview,
    handleOpenPreview,
    sessionId,
  ]);

  const latestAutoPreview = useMemo(
    () =>
      getLatestChatAutoPreviewTarget({
        messages,
        suppressAutoPreview: !!externalNavigationPreview,
      }),
    [messages, externalNavigationPreview],
  );
  const isMobileViewport =
    typeof window !== "undefined" ? window.innerWidth < 640 : false;

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
        sessionName={sessionName ?? undefined}
        runId={currentRunId ?? undefined}
        isLastMessage={index === messages.length - 1}
        activePreview={activePreview}
        latestAutoPreview={latestAutoPreview}
        onOpenPreview={handleOpenPreview}
      />
    ),
    [
      sessionId,
      sessionName,
      currentRunId,
      messages.length,
      activePreview,
      latestAutoPreview,
      handleOpenPreview,
    ],
  );

  const suggestions = useMemo(() => {
    const rawValue = settings?.settings?.frontend?.find(
      (s) => s.key === "WELCOME_SUGGESTIONS",
    )?.value;
    const currentLang = i18n.language?.split("-")[0] || "en";
    let list: Array<{ icon: string; text: string }> | undefined;
    if (Array.isArray(rawValue)) list = rawValue;
    else if (rawValue && typeof rawValue === "object") {
      const langMap = rawValue as Record<
        string,
        Array<{ icon: string; text: string }>
      >;
      list = langMap[currentLang] || langMap["en"];
    }
    return list;
  }, [settings, i18n.language]);

  const [displaySuggestions, setDisplaySuggestions] = useState(() => {
    if (!suggestions) return undefined;
    return [...suggestions].sort(() => Math.random() - 0.5).slice(0, 4);
  });

  // Sync displaySuggestions when suggestions change (language/settings update)
  useEffect(() => {
    if (!suggestions) {
      setDisplaySuggestions(undefined);
      return;
    }
    setDisplaySuggestions(
      [...suggestions].sort(() => Math.random() - 0.5).slice(0, 4),
    );
  }, [suggestions]);

  const refreshSuggestions = useCallback(() => {
    if (!suggestions) return;
    setDisplaySuggestions(
      [...suggestions].sort(() => Math.random() - 0.5).slice(0, 4),
    );
  }, [suggestions]);

  // Shared ChatInput props to avoid duplication
  const chatInputProps = {
    onSend: onSendMessage,
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
    agentOptions,
    agentOptionValues,
    onToggleAgentOption,
    agents,
    currentAgent,
    onSelectAgent,
    attachments,
    onAttachmentsChange,
  };

  return (
    <>
      <main
        ref={messagesContainerRef}
        className={`relative flex-1 min-h-0 pt-6 ${
          messages.length > 0 ? "overflow-hidden" : ""
        }`}
      >
        {messages.length === 0 ? (
          isLoading ? (
            <ChatSkeleton count={5} />
          ) : (
            <WelcomePage
              greeting={greeting}
              subtitle={
                t("chat.welcomeSubtitle") ?? "How can I help you today?"
              }
              suggestionsLabel={t("chat.welcomeSuggestions") ?? "Suggestions"}
              refreshLabel={t("chat.welcomeRefresh") ?? "Refresh"}
              suggestions={displaySuggestions}
              canSendMessage={canSendMessage}
              onSendMessage={onSendMessage}
              chatInputProps={chatInputProps}
              onRefreshSuggestions={refreshSuggestions}
            />
          )
        ) : (
          <Virtuoso
            key={messageListSessionKeyRef.current}
            ref={virtuosoRef}
            className="dark:divide-stone-800 overflow-x-hidden"
            data={messages}
            computeItemKey={(_, message) => message.id}
            atBottomStateChange={handleVirtuosoAtBottomChange}
            atBottomThreshold={getAtBottomThresholdPx(isMobileViewport)}
            components={virtuosoComponents}
            itemContent={virtuosoItemContent}
            initialTopMostItemIndex={getInitialBottomItemLocation(
              messages.length,
            )}
          />
        )}
      </main>

      {/* Right-side floating button cluster */}
      {messages.length > 0 && showScrollTop && (
        <div className="absolute right-3 sm:right-4 z-50 flex flex-col gap-1.5 bottom-36 sm:bottom-48">
          <button
            onClick={scrollToTop}
            className="flex items-center p-2 rounded-full bg-white/90 dark:bg-stone-800/90 border border-stone-200/80 dark:border-stone-700/60 shadow-lg  hover:shadow-xl transition-all duration-200 hover:scale-105 active:scale-95"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-4 h-4 text-stone-500 dark:text-stone-300"
            >
              <path
                fillRule="evenodd"
                d="M10 17a.75.75 0 01-.75-.75V5.612l-3.96 4.158a.75.75 0 11-1.08-1.04l5.25-5.5a.75.75 0 011.08 0l5.25 5.5a.75.75 0 11-1.08 1.04l-3.96-4.158V16.25A.75.75 0 0110 17z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      )}

      {messages.length > 0 && !isNearBottom && (
        <button
          onClick={scrollToBottom}
          className="absolute left-1/2 z-50 flex items-center p-2 rounded-full bg-white/90 dark:bg-stone-800/90 border border-stone-200/80 dark:border-stone-700/60 shadow-lg  hover:shadow-xl transition-all duration-200 hover:scale-105 active:scale-95 bottom-36 sm:bottom-48 -translate-x-1/2"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="w-4 h-4 text-stone-500 dark:text-stone-300"
          >
            <path
              fillRule="evenodd"
              d="M10 3a.75.75 0 01.75.75v10.638l3.96-4.158a.75.75 0 111.08 1.04l-5.25 5.5a.75.75 0 01-1.08 0l-5.25-5.5a.75.75 0 111.08-1.04l3.96 4.158V3.75A.75.75 0 0110 3z"
              clipRule="evenodd"
            />
          </svg>
        </button>
      )}

      <ApprovalPanel
        approvals={approvals}
        onRespond={onRespondApproval}
        isLoading={approvalLoading}
      />

      <RevealPreviewHost
        preview={activePreview}
        onClose={() => handleClosePreview(true)}
        onUserInteraction={handlePreviewInteraction}
      />
      <AttachmentPreviewHost />
      <PersistentToolPanelHost />

      {/* ChatInput at bottom (when messages exist, WelcomePage renders its own) */}
      {messages.length > 0 && <ChatInput {...chatInputProps} />}
    </>
  );
}
