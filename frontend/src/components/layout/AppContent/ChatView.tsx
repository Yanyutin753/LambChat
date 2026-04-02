import { useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../hooks/useAuth";
import { toast } from "react-hot-toast";
import { ChatMessage } from "../../chat/ChatMessage";
import { ChatInput } from "../../chat/ChatInput";
import { Virtuoso } from "react-virtuoso";
import { ApprovalPanel } from "../../panels/ApprovalPanel";
import { Loading } from "../../common";
import { useMessageScroll } from "./useMessageScroll";
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
        key={message.id}
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
    if (!list) return undefined;
    const shuffled = [...list].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, 4);
  }, [settings, i18n.language]);

  return (
    <>
      <main
        ref={messagesContainerRef}
        className="relative flex-1 overflow-hidden min-h-0 pt-6"
      >
        {isLoading && messages.length === 0 && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/80 dark:bg-stone-900/80 ">
            <Loading size="lg" />
          </div>
        )}
        {messages.length === 0 ? (
          <div className="relative flex h-full flex-col items-center justify-center px-4 py-6 sm:py-8 welcome-grain">
            <div className="relative flex flex-col items-center mb-8 sm:mb-10 w-full max-w-[90vw]">
              {/* Greeting */}
              <h1 className="max-w-[90vw] welcome-title text-3xl sm:text-4xl font-bold bg-gradient-to-r from-stone-900 via-stone-600 to-stone-900 dark:from-stone-50 dark:via-stone-200 dark:to-stone-50 bg-clip-text text-transparent font-serif tracking-tight mb-3 sm:mb-4 whitespace-nowrap overflow-hidden text-ellipsis">
                {greeting}
              </h1>
              {/* Subtitle */}
              <p className="text-sm sm:text-base text-stone-500 dark:text-stone-400 font-medium tracking-wide">
                ✦ {t("chat.welcomeSubtitle") ?? "How can I help you today?"}
              </p>
            </div>

            <div className="relative w-full max-w-xl sm:max-w-2xl px-2 sm:px-4 sm:block hidden">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-5">
                {suggestions?.map((suggestion, i) => (
                  <button
                    key={suggestion.text}
                    onClick={() => {
                      if (!canSendMessage) {
                        toast.error(t("chat.noPermissionHint"));
                        return;
                      }
                      onSendMessage(suggestion.text);
                    }}
                    className="welcome-card group flex items-center gap-3 sm:gap-3.5 rounded-xl sm:rounded-2xl border border-stone-200/70 dark:border-stone-700/40 px-4 py-3.5 sm:px-5 sm:py-4 text-left text-sm text-stone-700 dark:text-stone-200 bg-white/60 dark:bg-stone-800/30  hover:bg-white dark:hover:bg-stone-800/60 hover:border-stone-300/80 dark:hover:border-stone-600/50 transition-all duration-300 hover:shadow-md hover:shadow-stone-200/40 dark:hover:shadow-stone-900/40 hover:-translate-y-0.5"
                    style={{ animationDelay: `${0.4 + i * 80}ms` }}
                  >
                    <span className="flex items-center justify-center size-9 sm:size-10 rounded-xl bg-stone-100 dark:bg-stone-700/60 text-lg sm:text-xl shrink-0 group-hover:scale-110 group-hover:bg-stone-200/80 dark:group-hover:bg-stone-600/50 transition-all duration-300">
                      {suggestion.icon}
                    </span>
                    <span className="text-[13px] sm:text-sm leading-snug text-stone-500 dark:text-stone-400 group-hover:text-stone-700 dark:group-hover:text-stone-200 transition-colors duration-300">
                      {suggestion.text}
                    </span>
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 20 20"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="w-4 h-4 ml-auto shrink-0 text-stone-300 dark:text-stone-600 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 group-hover:text-stone-400 dark:group-hover:text-stone-500 transition-all duration-300"
                    >
                      <path d="M7 5l5 5-5 5" />
                    </svg>
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <Virtuoso
            key={sessionId || undefined}
            ref={virtuosoRef}
            className="dark:divide-stone-800 overflow-x-hidden"
            data={messages}
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
          className="absolute right-3 sm:right-4 z-50 flex items-center p-2 rounded-full bg-white/90 dark:bg-stone-800/90 border border-stone-200/80 dark:border-stone-700/60 shadow-lg  hover:shadow-xl transition-all duration-200 hover:scale-105 active:scale-95"
          style={{ bottom: "9rem" }}
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
          className="absolute left-1/2 z-50 flex items-center p-2 rounded-full bg-white/90 dark:bg-stone-800/90 border border-stone-200/80 dark:border-stone-700/60 shadow-lg  hover:shadow-xl transition-all duration-200 hover:scale-105 active:scale-95"
          style={{ bottom: "9rem", transform: "translateX(-50%)" }}
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

      {messages.length === 0 && (
        <div className="sm:hidden px-3 pb-2 flex gap-2 overflow-x-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
          {suggestions?.map((suggestion) => (
            <button
              key={suggestion.text}
              onClick={() => {
                if (!canSendMessage) {
                  toast.error(t("chat.noPermissionHint"));
                  return;
                }
                onSendMessage(suggestion.text);
              }}
              className="shrink-0 inline-flex items-center gap-1 rounded-full border border-stone-200/70 dark:border-stone-700/40 bg-white/60 dark:bg-stone-800/30 px-3 py-1.5 text-[13px] text-stone-500 dark:text-stone-400 active:bg-stone-100 dark:active:bg-stone-700/40 transition-colors"
            >
              {suggestion.icon}
              <span className="ml-1">{suggestion.text}</span>
            </button>
          ))}
        </div>
      )}

      <ChatInput
        onSend={onSendMessage}
        onStop={onStopGeneration}
        isLoading={isLoading}
        canSend={canSendMessage}
        tools={tools}
        onToggleTool={onToggleTool}
        onToggleCategory={onToggleCategory}
        onToggleAll={onToggleAll}
        toolsLoading={toolsLoading}
        enabledToolsCount={enabledToolsCount}
        totalToolsCount={totalToolsCount}
        skills={skills}
        onToggleSkill={onToggleSkill}
        onToggleSkillCategory={onToggleSkillCategory}
        onToggleAllSkills={onToggleAllSkills}
        skillsLoading={skillsLoading}
        pendingSkillNames={pendingSkillNames}
        skillsMutating={skillsMutating}
        enabledSkillsCount={enabledSkillsCount}
        totalSkillsCount={totalSkillsCount}
        enableSkills={enableSkills}
        agentOptions={agentOptions}
        agentOptionValues={agentOptionValues}
        onToggleAgentOption={onToggleAgentOption}
        attachments={attachments}
        onAttachmentsChange={onAttachmentsChange}
      />
    </>
  );
}
