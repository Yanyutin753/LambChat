import { clsx } from "clsx";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { Bot, Copy, Info, Ban } from "lucide-react";
import type {
  Message,
  MessagePart,
  ToolCall,
  ToolResult,
  TokenUsagePart,
} from "../../../types";
import { useTranslation } from "react-i18next";
import { MarkdownContent } from "./MarkdownContent";
import { ToolCallItem, FileRevealItem } from "./ToolCallItem";
import { ThinkingBlock, SubagentBlock, SandboxItem } from "./SubagentBlocks";
import { UserMessageBubble } from "./UserMessageBubble";
import { FeedbackButtons } from "./FeedbackButtons";
import { ShareButton } from "./ShareButton";

// Skeleton-style loading animation component - refined thin lines
function ThinkingIndicator() {
  return (
    <div className="space-y-2.5 py-1">
      {/* First line - long bar */}
      <div className="skeleton-line w-full h-2 rounded-sm" />

      {/* Second line - three medium bars */}
      <div className="flex gap-4">
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
      </div>

      {/* Third line - three medium bars */}
      <div className="flex gap-4">
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
      </div>

      {/* Fourth line */}
      <div className="flex gap-4">
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
        <div className="skeleton-line w-2/5 h-2 rounded-sm" />
      </div>
    </div>
  );
}

interface ChatMessageProps {
  message: Message;
  sessionId?: string;
  sessionName?: string;
  runId?: string;
  onStop?: () => void;
}

// Token usage statistics button component - ChatGPT style
function TokenDetailsButton({
  tokenUsage,
  duration,
}: {
  tokenUsage?: TokenUsagePart;
  duration?: number;
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
          "p-1.5 rounded-md transition-all",
          "opacity-0 group-hover:opacity-100",
          "hover:bg-gray-200 dark:hover:bg-stone-700",
          "text-gray-400 dark:text-stone-500 hover:text-gray-600 dark:hover:text-stone-300",
        )}
        title="Token usage"
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
            "border border-gray-200 dark:border-stone-700",
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
                <div className="flex justify-between gap-4 border-t border-gray-100 dark:border-stone-700 pt-1.5 mt-1.5 text-amber-600 dark:text-amber-400">
                  <span className="">{t("chat.message.tokenTotal")}</span>
                  <span className="font-medium">
                    {tokenUsage.total_tokens?.toLocaleString()} tokens
                  </span>
                </div>
              </>
            )}
            {duration && (
              <div className="flex justify-between gap-4 border-t border-gray-100 dark:border-stone-700 pt-1.5 mt-1.5">
                <span className="text-gray-500 dark:text-stone-400">
                  {t("chat.message.duration")}
                </span>
                <span className="text-gray-700 dark:text-stone-200 font-medium">
                  {(duration / 1000).toFixed(2)}s
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
}: ChatMessageProps) {
  const { t } = useTranslation();
  const isUser = message.role === "user";
  const isStreaming = message.isStreaming && !message.content;

  // If there are parts, render in order; otherwise fall back to old rendering method
  const hasParts = message.parts && message.parts.length > 0;

  // User message: bubble style, right aligned
  if (isUser) {
    console.log("[ChatMessage] Rendering user message with attachments:", {
      messageId: message.id,
      attachments: message.attachments,
    });
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
    <div className="group w-full">
      <div className="mx-auto flex flex-col max-w-3xl xl:max-w-5xl px-3 sm:px-6 mb-3 sm:mb-4">
        {/* Content */}
        <div className="flex-1 overflow-hidden min-w-0">
          {/* Header: Avatar + Role label + Stop button */}
          <div className="mb-3 flex items-center gap-2">
            <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-amber-500 to-rose-500 text-white shadow-sm">
              <Bot size={16} />
            </div>
            <span className="text-base font-semibold text-stone-900 dark:text-stone-100 font-serif">
              {t("chat.message.assistant")}
            </span>
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
                  <div className="text-xs font-medium text-stone-400 uppercase tracking-wide mb-2 dark:text-stone-500">
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
                "p-1.5 rounded-md transition-all",
                "opacity-0 group-hover:opacity-100",
                "hover:bg-gray-200 dark:hover:bg-stone-700",
                "text-gray-400 dark:text-stone-500 hover:text-gray-600 dark:hover:text-stone-300",
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
              />
            )}
            {/* Feedback buttons */}
            {sessionId && (message.runId || runId) && (
              <FeedbackButtons
                sessionId={sessionId}
                runId={message.runId || runId!}
                currentFeedback={message.feedback}
              />
            )}
            {/* Share button */}
            {sessionId && (
              <ShareButton
                sessionId={sessionId}
                sessionName={sessionName}
                runId={message.runId || runId}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Render single message part
function MessagePartRenderer({
  part,
  isStreaming,
  isLast,
}: {
  part: MessagePart;
  isStreaming?: boolean;
  isLast: boolean;
}) {
  const { t } = useTranslation();

  if (part.type === "text") {
    // Text inside subagent uses simple rendering, main agent uses Markdown
    if (part.depth && part.depth > 0) {
      return (
        <span className="text-xs text-stone-600 dark:text-stone-300 leading-relaxed">
          {part.content}
          {isStreaming && isLast && (
            <span className="inline-block h-3 w-0.5 animate-pulse bg-blue-400 ml-0.5 rounded-sm" />
          )}
        </span>
      );
    }
    return (
      <MarkdownContent
        content={part.content}
        isStreaming={isStreaming && isLast}
      />
    );
  }

  if (part.type === "tool") {
    // Detect reveal_file tool, use dedicated component
    if (part.name === "reveal_file") {
      return (
        <FileRevealItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
        />
      );
    }
    return (
      <ToolCallItem
        name={part.name}
        args={part.args}
        result={part.result}
        success={part.success}
        isPending={part.isPending}
      />
    );
  }

  if (part.type === "thinking") {
    return (
      <ThinkingBlock
        content={part.content}
        isStreaming={isStreaming && isLast && part.isStreaming}
      />
    );
  }

  if (part.type === "subagent") {
    return (
      <SubagentBlock
        agent_id={part.agent_id}
        agent_name={part.agent_name}
        input={part.input}
        result={part.result}
        success={part.success}
        isPending={part.isPending}
        parts={part.parts}
      />
    );
  }

  // Sandbox status block
  if (part.type === "sandbox") {
    return (
      <SandboxItem
        status={part.status}
        sandboxId={part.sandbox_id}
        error={part.error}
      />
    );
  }

  // Cancelled block
  if (part.type === "cancelled") {
    return (
      <div
        className={clsx(
          "flex items-center gap-2 px-4 py-2.5 rounded-xl",
          "bg-amber-50 dark:bg-amber-950/40",
          "border border-amber-200/60 dark:border-amber-800/60",
          "text-amber-700 dark:text-amber-400",
          "text-sm font-medium",
        )}
      >
        <Ban size={16} className="shrink-0" />
        <span>{t("chat.message.cancelled")}</span>
      </div>
    );
  }

  return null;
}
