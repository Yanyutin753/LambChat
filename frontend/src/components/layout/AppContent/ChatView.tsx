import { useMemo, useCallback, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../hooks/useAuth";
import { ChatMessage } from "../../chat/ChatMessage";
import { ChatInput } from "../../chat/ChatInput";
import { WelcomePage } from "../../chat/WelcomePage";
import { Virtuoso } from "react-virtuoso";
import { ApprovalPanel } from "../../panels/ApprovalPanel";
import { useMessageScroll } from "./useMessageScroll";
import { isSessionRunning } from "./sessionState";
import type {
  Message,
  PendingApproval,
  ToolState,
  SkillResponse,
  SkillSource,
  ToolCategory,
  AgentOption,
  MessageAttachment,
} from "../../../types";

interface ChatViewProps {
  messages: Message[];
  sessionId: string | null;
  sessionName: string | null;
  currentRunId: string | null;
  isLoading: boolean;
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
}

export function ChatView({
  messages,
  sessionId,
  sessionName,
  currentRunId,
  isLoading,
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
}: ChatViewProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const sessionRunning = isSessionRunning(messages, isLoading);

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
  } = useMessageScroll(messages, sessionId);

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
      Footer: () => <div ref={messagesEndRef} className="h-8" />,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const virtuosoItemContent = useCallback(
    (index: number, message: (typeof messages)[number]) => (
      <ChatMessage
        message={message}
        sessionId={sessionId ?? undefined}
        sessionName={sessionName ?? undefined}
        runId={currentRunId ?? undefined}
        isLastMessage={index === messages.length - 1}
      />
    ),
    [sessionId, sessionName, currentRunId, messages.length],
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
          <WelcomePage
            greeting={greeting}
            subtitle={t("chat.welcomeSubtitle") ?? "How can I help you today?"}
            suggestionsLabel={t("chat.welcomeSuggestions") ?? "Suggestions"}
            refreshLabel={t("chat.welcomeRefresh") ?? "Refresh"}
            suggestions={displaySuggestions}
            canSendMessage={canSendMessage}
            onSendMessage={onSendMessage}
            noPermissionHint={t("chat.noPermissionHint")}
            chatInputProps={chatInputProps}
            onRefreshSuggestions={refreshSuggestions}
          />
        ) : (
          <Virtuoso
            ref={virtuosoRef}
            className="dark:divide-stone-800 overflow-x-hidden"
            data={messages}
            computeItemKey={(_, message) => message.id}
            atBottomStateChange={handleVirtuosoAtBottomChange}
            atBottomThreshold={50}
            followOutput="smooth"
            components={virtuosoComponents}
            itemContent={virtuosoItemContent}
            initialTopMostItemIndex={messages.length - 1}
          />
        )}
      </main>

      {messages.length > 0 && showScrollTop && (
        <button
          onClick={scrollToTop}
          className="absolute right-3 sm:right-4 z-50 flex items-center p-2 rounded-full bg-white/90 dark:bg-stone-800/90 border border-stone-200/80 dark:border-stone-700/60 shadow-lg  hover:shadow-xl transition-all duration-200 hover:scale-105 active:scale-95 bottom-36 sm:bottom-48"
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

      {/* ChatInput at bottom (when messages exist, WelcomePage renders its own) */}
      {messages.length > 0 && <ChatInput {...chatInputProps} />}
    </>
  );
}
