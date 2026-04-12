import { clsx } from "clsx";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { Copy, Info, Sparkles } from "lucide-react";
import type {
  Message,
  MessagePart,
  ToolCall,
  ToolResult,
  TokenUsagePart,
} from "../../../types";
import { useTranslation } from "react-i18next";
import { MarkdownContent } from "./MarkdownContent";
import { ToolCallItem } from "./ToolCallItem";
import { UserMessageBubble } from "./UserMessageBubble";
import { MessagePartRenderer } from "./MessagePartRenderer";
import { FeedbackButtons } from "./FeedbackButtons";
import { ShareButton } from "./ShareButton";
import { CollapsiblePill } from "../../common/CollapsiblePill";

// Skeleton-style loading animation component - refined thin lines
function ThinkingIndicator() {
  return (
    <div className="space-y-2.5 py-1 px-1">
      {/* First line - long bar */}
      <div className="skeleton-line w-full h-2 rounded-full" />

      {/* Second line - three medium bars */}
      <div className="flex gap-3">
        <div className="skeleton-line flex-1 h-2 rounded-full" />
        <div className="skeleton-line flex-1 h-2 rounded-full" />
        <div className="skeleton-line flex-1 h-2 rounded-full" />
      </div>

      {/* Third line - three medium bars */}
      <div className="flex gap-3">
        <div className="skeleton-line flex-1 h-2 rounded-full" />
        <div className="skeleton-line flex-1 h-2 rounded-full" />
        <div className="skeleton-line flex-1 h-2 rounded-full" />
      </div>

      {/* Fourth line */}
      <div className="flex gap-3">
        <div className="skeleton-line flex-1 h-2 rounded-full" />
        <div className="skeleton-line w-2/5 h-2 rounded-full" />
      </div>
    </div>
  );
}

interface ChatMessageProps {
  message: Message;
  sessionId?: string;
  sessionName?: string;
  runId?: string;
  isLastMessage?: boolean;
  onStop?: () => void;
}

// Token usage statistics button component - ChatGPT style
function TokenDetailsButton({
  tokenUsage,
  duration,
  timestamp,
  isLastMessage,
}: {
  tokenUsage?: TokenUsagePart;
  duration?: number;
  timestamp?: Date;
  isLastMessage?: boolean;
}) {
  const { t } = useTranslation();
  const [showDetails, setShowDetails] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Close details when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setShowDetails(false);
      }
    };
    if (showDetails) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showDetails]);

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        onClick={() => setShowDetails(!showDetails)}
        className={clsx(
          "p-1.5 rounded-md transition-colors",
          !isLastMessage && "opacity-0 group-hover:opacity-100",
          "hover:bg-stone-200 dark:hover:bg-stone-700",
          "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300",
        )}
        title={t("chat.message.tokenUsage")}
      >
        <Info size={16} />
      </button>
      {/* ChatGPT style details popup */}
      {showDetails && (
        <div
          className={clsx(
            "absolute bottom-full mb-2 left-0 z-50",
            "min-w-[150px] w-auto p-3 rounded-lg shadow-lg",
            "bg-white dark:bg-stone-800",
            "border border-stone-200 dark:border-stone-700",
            "whitespace-nowrap",
          )}
        >
          <div className="text-xs space-y-1.5">
            {tokenUsage && (
              <>
                <div className="flex justify-between gap-4 text-sky-600 dark:text-sky-400">
                  <span className="">{t("chat.message.tokenInput")}</span>
                  <span className="font-medium">
                    {tokenUsage.input_tokens?.toLocaleString()} tokens
                  </span>
                </div>
                <div className="flex justify-between gap-4 text-violet-600 dark:text-violet-400">
                  <span className="">{t("chat.message.tokenOutput")}</span>
                  <span className="font-medium">
                    {tokenUsage.output_tokens?.toLocaleString()} tokens
                  </span>
                </div>
                {(tokenUsage.cache_creation_tokens ?? 0) > 0 && (
                  <div className="flex justify-between gap-4 text-emerald-600 dark:text-emerald-400">
                    <span className="">
                      {t("chat.message.tokenCacheCreation")}
                    </span>
                    <span className="font-medium">
                      {(tokenUsage.cache_creation_tokens ?? 0).toLocaleString()}{" "}
                      tokens
                    </span>
                  </div>
                )}
                {(tokenUsage.cache_read_tokens ?? 0) > 0 && (
                  <div className="flex justify-between gap-4 text-pink-600 dark:text-pink-400">
                    <span className="">{t("chat.message.tokenCacheRead")}</span>
                    <span className="font-medium">
                      {(tokenUsage.cache_read_tokens ?? 0).toLocaleString()}{" "}
                      tokens
                    </span>
                  </div>
                )}
                <div className="flex justify-between gap-4 border-t border-stone-100 dark:border-stone-700 pt-1.5 mt-1.5 text-amber-600 dark:text-amber-400">
                  <span className="">{t("chat.message.tokenTotal")}</span>
                  <span className="font-medium">
                    {tokenUsage.total_tokens?.toLocaleString()} tokens
                  </span>
                </div>
              </>
            )}
            {duration && (
              <div className="flex justify-between gap-4 border-t border-stone-100 dark:border-stone-700 pt-1.5 mt-1.5">
                <span className="text-stone-500 dark:text-stone-400">
                  {t("chat.message.duration")}
                </span>
                <span className="text-stone-700 dark:text-stone-200 font-medium">
                  {(duration / 1000).toFixed(2)}s
                </span>
              </div>
            )}
            {timestamp && (
              <div className="flex justify-between gap-4 border-t border-stone-100 dark:border-stone-700 pt-1.5 mt-1.5">
                <span className="text-stone-500 dark:text-stone-400">
                  {t("chat.message.startTime")}
                </span>
                <span className="text-stone-700 dark:text-stone-200 font-medium tabular-nums">
                  {new Date(timestamp).toLocaleString([], {
                    year: "numeric",
                    month: "2-digit",
                    day: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function ChatMessage({
  message,
  sessionId,
  sessionName,
  runId,
  isLastMessage,
}: ChatMessageProps) {
  const { t } = useTranslation();
  const isUser = message.role === "user";
  const isStreaming = message.isStreaming && !message.content;

  // If there are parts, render in order; otherwise fall back to old rendering method
  const hasParts = message.parts && message.parts.length > 0;

  // User message: bubble style, right aligned
  if (isUser) {
    return (
      <UserMessageBubble
        content={message.content}
        attachments={message.attachments}
      />
    );
  }

  // Get assistant message's plain text content for copying
  const getAssistantTextContent = (): string => {
    if (hasParts && message.parts) {
      // Extract all text content from parts
      return message.parts
        .filter(
          (part): part is Extract<MessagePart, { type: "text" }> =>
            part.type === "text",
        )
        .map((part) => part.content)
        .join("\n");
    }
    return message.content || "";
  };

  // Assistant message: left layout
  return (
    <div className="group w-full animate-[fade-in_0.3s_ease-out]">
      <div className="mx-auto flex flex-col max-w-3xl xl:max-w-5xl px-4 sm:px-6 mb-3 sm:mb-4">
        {/* Content */}
        <div className="min-w-0 min-h-0">
          {/* Header: Avatar + Role label + Stop button */}
          <div className="mb-3 flex items-center gap-2">
            <img
              src="/icons/icon.svg"
              alt="Assistant"
              className="size-6 shrink-0 rounded-full"
            />
            <span
              className="text-base sm:text-lg font-semibold tracking-tight font-serif"
              style={{ color: "var(--theme-text)" }}
            >
              {t("chat.message.assistant")}
            </span>
            {message.timestamp && (
              <span
                className="text-xs ml-2 mt-0.5 tabular-nums opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {new Date(message.timestamp).toLocaleString([], {
                  year: "numeric",
                  month: "2-digit",
                  day: "2-digit",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            )}
          </div>

          {/* Streaming/Thinking indicator */}
          {isStreaming && !hasParts && <ThinkingIndicator />}

          {hasParts ? (
            <div className="space-y-3 px-2 my-2">
              {message.parts!.map((part: MessagePart, index: number) => (
                <MessagePartRenderer
                  key={index}
                  part={part}
                  isStreaming={message.isStreaming}
                  isLast={index === message.parts!.length - 1}
                />
              ))}
            </div>
          ) : (
            <>
              {message.content && (
                <MarkdownContent
                  content={message.content}
                  isStreaming={message.isStreaming}
                />
              )}
              {message.toolCalls && message.toolCalls.length > 0 && (
                <div className="mt-4 space-y-2">
                  <div
                    className="text-xs font-medium uppercase tracking-wide mb-2"
                    style={{ color: "var(--theme-text-secondary)" }}
                  >
                    {t("chat.message.toolCalls")} ({message.toolCalls.length})
                  </div>
                  {message.toolCalls.map((call: ToolCall, index: number) => {
                    const result = message.toolResults?.find(
                      (r: ToolResult) => r.name === call.name,
                    );
                    return (
                      <ToolCallItem
                        key={index}
                        name={call.name}
                        args={call.args || {}}
                        result={result?.result}
                        success={result?.success}
                        isPending={!result && message.isStreaming}
                      />
                    );
                  })}
                </div>
              )}
            </>
          )}
          {/* Streaming indicator - bottom of message (when not showing thinking indicator) */}
          {message.isStreaming && !(isStreaming && !hasParts) && (
            <div className="mt-3 px-2">
              <CollapsiblePill
                status="loading"
                icon={<Sparkles size={12} className="shrink-0 opacity-50" />}
                label={t("chat.message.generating")}
                variant="tool"
                expandable={false}
              />
            </div>
          )}
        </div>
        {/* Copy button and Token button - same line at bottom, show on message hover (only after message completes) */}
        {!message.isStreaming && (
          <div className="mt-2 flex items-center gap-1">
            <button
              onClick={() => {
                const textContent = getAssistantTextContent();
                if (textContent) {
                  navigator.clipboard.writeText(textContent);
                  toast.success(t("chat.message.copied"));
                }
              }}
              className={clsx(
                "p-1.5 rounded-md transition-colors",
                !isLastMessage && "opacity-0 group-hover:opacity-100",
                "hover:bg-stone-200 dark:hover:bg-stone-700",
                "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300",
              )}
              title={t("chat.message.copy")}
            >
              <Copy size={16} />
            </button>
            {/* Token usage statistics button */}
            {(message.tokenUsage || message.duration) && (
              <TokenDetailsButton
                tokenUsage={message.tokenUsage}
                duration={message.duration}
                timestamp={message.timestamp}
                isLastMessage={isLastMessage}
              />
            )}
            {/* Feedback buttons */}
            {sessionId && (message.runId || runId) && (
              <FeedbackButtons
                sessionId={sessionId}
                runId={message.runId || runId!}
                currentFeedback={message.feedback}
                isLastMessage={isLastMessage}
              />
            )}
            {/* Share button */}
            {sessionId && (
              <ShareButton
                sessionId={sessionId}
                sessionName={sessionName}
                runId={message.runId || runId}
                isLastMessage={isLastMessage}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
