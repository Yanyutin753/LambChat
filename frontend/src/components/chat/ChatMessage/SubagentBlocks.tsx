import { useEffect, useState } from "react";
import { clsx } from "clsx";
import {
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronRight,
  Brain,
  Users,
  Wrench,
  Box,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner, CollapsiblePill } from "../../common";
import type { CollapsibleStatus } from "../../common";
import type { MessagePart } from "../../../types";
import { MarkdownContent, truncateText } from "./MarkdownContent";

// Thinking Block - thinking process display (ChatGPT style)
export function ThinkingBlock({
  content,
  isStreaming,
  isPending,
  success,
  hasResult,
}: {
  content: string;
  isStreaming?: boolean;
  isPending?: boolean;
  success?: boolean;
  hasResult?: boolean;
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="my-1">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={clsx(
          "inline-flex items-center gap-1 px-2.5 py-2 rounded-full text-xs font-medium",
          "transition-all bg-stone-200 dark:bg-stone-700",
          "text-stone-600 dark:text-stone-300",
          "hover:bg-stone-300 dark:hover:bg-stone-600 cursor-pointer",
        )}
      >
        {/* Status indicator */}
        {isPending ? (
          <LoadingSpinner size="sm" className="shrink-0" />
        ) : success ? (
          <CheckCircle size={12} className="shrink-0" />
        ) : hasResult ? (
          <XCircle size={12} className="shrink-0" />
        ) : null}

        {/* Thinking icon */}
        <Brain
          size={12}
          className="shrink-0 text-stone-500 dark:text-stone-400"
        />

        <span className="font-mono">
          {isStreaming || isPending
            ? t("chat.message.thinking")
            : t("chat.message.thought")}
        </span>
        {isStreaming && (
          <span className="flex items-center gap-[2px] ml-1">
            <span className="w-0.5 h-1 bg-stone-500 dark:bg-stone-400 rounded-full animate-[wave_0.6s_ease-in-out_infinite]" />
            <span className="w-0.5 h-1.5 bg-stone-500 dark:bg-stone-400 rounded-full animate-[wave_0.6s_ease-in-out_infinite_0.1s]" />
            <span className="w-0.5 h-1 bg-stone-500 dark:bg-stone-400 rounded-full animate-[wave_0.6s_ease-in-out_infinite_0.2s]" />
          </span>
        )}
        <ChevronRight
          size={12}
          className={clsx(
            "shrink-0 transition-transform duration-200 text-stone-500 dark:text-stone-400",
            isExpanded && "rotate-90",
          )}
        />
      </button>

      <div
        className={clsx(
          "grid transition-all duration-200 ease-out",
          isExpanded
            ? "grid-rows-[1fr] opacity-100 mt-1"
            : "grid-rows-[0fr] opacity-0",
        )}
      >
        <div className="overflow-hidden">
          <div className="ml-4 pl-3 border-l-2 border-stone-300 dark:border-stone-600">
            <div className="text-xs text-stone-600 dark:text-stone-300 leading-relaxed pl-1 pt-2">
              <MarkdownContent content={content} isStreaming={isStreaming} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Subagent Block - subagent call display (ChatGPT style minimal design)
export function SubagentBlock({
  agent_name,
  input,
  result,
  success,
  isPending,
  parts,
}: {
  agent_id: string;
  agent_name: string;
  input: string;
  result?: string;
  success?: boolean;
  isPending?: boolean;
  parts?: MessagePart[];
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);
  const hasContent = (parts && parts.length > 0) || result;

  // Auto collapse when completed
  useEffect(() => {
    if (isPending === false) {
      setIsExpanded(false);
    }
  }, [isPending]);

  return (
    <div
      className={clsx(
        "my-3 rounded-xl overflow-hidden transition-all duration-200",
        "border border-stone-200 dark:border-stone-700",
        "bg-white dark:bg-stone-900",
      )}
    >
      {/* Header - minimal design */}
      <button
        onClick={() => hasContent && setIsExpanded(!isExpanded)}
        className={clsx(
          "w-full px-4 py-3 flex items-center gap-3 transition-colors",
          "hover:bg-stone-50 dark:hover:bg-stone-800/50",
          hasContent && "cursor-pointer",
        )}
      >
        {/* Status icon - compact and refined */}
        <div
          className={clsx(
            "flex h-7 w-7 items-center justify-center rounded-lg",
            isPending
              ? "bg-blue-100 dark:bg-blue-900/40"
              : success
                ? "bg-emerald-100 dark:bg-emerald-900/40"
                : "bg-stone-100 dark:bg-stone-800",
          )}
        >
          {isPending ? (
            <LoadingSpinner
              size="sm"
              className="text-blue-600 dark:text-blue-400"
            />
          ) : success ? (
            <CheckCircle
              size={14}
              className="text-stone-600 dark:text-stone-300"
            />
          ) : (
            <Users size={14} className="text-stone-500 dark:text-stone-400" />
          )}
        </div>

        <div className="flex-1 min-w-0 text-left">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-stone-800 dark:text-stone-200 truncate">
              {agent_name}
            </span>
            {isPending && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400 font-medium">
                {t("chat.message.running")}
              </span>
            )}
          </div>
          {input && !isExpanded && (
            <p className="text-xs text-stone-500 dark:text-stone-400 truncate mt-0.5 max-w-md">
              {input}
            </p>
          )}
        </div>

        {/* Expand button */}
        {hasContent && (
          <div className="text-stone-400 dark:text-stone-500">
            {isExpanded ? (
              <ChevronDown size={18} />
            ) : (
              <ChevronRight size={18} />
            )}
          </div>
        )}
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-4 pb-4 space-y-3">
          {/* Separator */}
          <div className="border-t border-stone-100 dark:border-stone-800" />

          {/* Task description */}
          {input && (
            <div className="text-sm text-stone-600 dark:text-stone-300 leading-relaxed">
              <MarkdownContent content={input} />
            </div>
          )}

          {/* Subagent internal content */}
          {parts && parts.length > 0 && (
            <div className="space-y-2 pl-3 border-l-2 border-stone-200 dark:border-stone-700">
              {parts.map((part, index) => (
                <SubagentContentRenderer
                  key={index}
                  part={part}
                  isStreaming={isPending}
                  isLast={index === parts.length - 1}
                />
              ))}
            </div>
          )}

          {/* Result */}
          {result && !isPending && (
            <div className="p-3 rounded-lg bg-stone-50 dark:bg-stone-800/50 border border-stone-100 dark:border-stone-700">
              <div className="text-xs text-stone-500 dark:text-stone-400 mb-1.5 font-medium">
                {t("chat.message.result")}
              </div>
              <div className="text-xs text-stone-700 dark:text-stone-300 max-h-48 overflow-y-auto leading-relaxed">
                <MarkdownContent content={result} />
              </div>
            </div>
          )}

          {/* Waiting state */}
          {isPending && !parts?.length && (
            <div className="flex items-center gap-2 py-2 text-stone-500 dark:text-stone-400">
              <LoadingSpinner size="sm" />
              <span className="text-sm">{t("chat.message.executing")}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Subagent internal tool call component (separately extracted to follow hooks rules)
function SubagentToolItem({
  part,
}: {
  part: Extract<MessagePart, { type: "tool" }>;
}) {
  const { t } = useTranslation();

  // Determine status based on part state
  let status: CollapsibleStatus = "idle";
  if (part.isPending) {
    status = "loading";
  } else if (part.success) {
    status = "success";
  } else if (part.result) {
    status = "error";
  }

  const hasArgs = part.args && Object.keys(part.args).length > 0;
  const hasResult = !!part.result;
  const canExpand = hasArgs || hasResult;

  return (
    <div className="rounded-lg overflow-hidden">
      <CollapsiblePill
        status={status}
        icon={<Wrench size={12} className="shrink-0 opacity-50" />}
        label={part.name}
        variant="tool"
        expandable={canExpand}
      >
        {canExpand && (
          <div className="px-3 pb-2 space-y-2 border-t border-stone-200/50 dark:border-stone-600/50">
            {hasArgs && (
              <div>
                <div className="text-xs text-stone-400 dark:text-stone-500 mb-1">
                  {t("chat.message.parameters")}
                </div>
                <pre className="text-xs text-stone-600 dark:text-stone-300 bg-stone-50 dark:bg-stone-800 rounded p-1.5 overflow-auto">
                  {JSON.stringify(part.args, null, 2)}
                </pre>
              </div>
            )}
            {hasResult && (
              <div>
                <div className="text-xs text-stone-400 dark:text-stone-500 mb-1">
                  {t("chat.message.result")}
                </div>
                <pre className="text-xs text-stone-600 dark:text-stone-300 bg-stone-50 dark:bg-stone-800 rounded p-1.5 max-h-24 overflow-auto">
                  {truncateText(part.result || "", 500)}
                </pre>
              </div>
            )}
          </div>
        )}
      </CollapsiblePill>
    </div>
  );
}

// Sandbox status block component
export function SandboxItem({
  status,
  sandboxId,
  error,
}: {
  status: "starting" | "ready" | "error";
  sandboxId?: string;
  error?: string;
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  const hasDetails =
    (status === "ready" && sandboxId) || (status === "error" && error);

  const pillStatus: CollapsibleStatus =
    status === "starting"
      ? "loading"
      : status === "ready"
        ? "success"
        : "error";

  return (
    <CollapsiblePill
      status={pillStatus}
      icon={<Box size={12} className="shrink-0 opacity-50" />}
      label={t("chat.sandbox.name")}
      expandable={!!hasDetails}
      onExpandChange={setIsExpanded}
    >
      {isExpanded && hasDetails && (
        <div className="mt-1 ml-4 pl-3 border-l-2 border-stone-300 dark:border-stone-600">
          {status === "ready" && sandboxId && (
            <div className="text-xs text-stone-600 dark:text-stone-300 pl-1 py-1 font-mono">
              ID: {sandboxId}
            </div>
          )}
          {status === "error" && error && (
            <div className="text-xs text-red-600 dark:text-red-400 pl-1 py-1">
              {error}
            </div>
          )}
        </div>
      )}
    </CollapsiblePill>
  );
}

// Subagent internal content renderer (independent from main agent rendering logic)
export function SubagentContentRenderer({
  part,
  isStreaming,
  isLast,
}: {
  part: MessagePart;
  isStreaming?: boolean;
  isLast: boolean;
}) {
  // Text - use markdown rendering
  if (part.type === "text") {
    return (
      <div className="text-sm text-stone-600 dark:text-stone-300 leading-relaxed">
        <MarkdownContent
          content={part.content || ""}
          isStreaming={isStreaming && isLast}
        />
      </div>
    );
  }

  // Tool call - use independent component
  if (part.type === "tool") {
    return <SubagentToolItem part={part} />;
  }

  // Thinking - use ThinkingBlock component
  if (part.type === "thinking") {
    return (
      <ThinkingBlock
        content={part.content || ""}
        isStreaming={isStreaming && isLast && part.isStreaming}
      />
    );
  }

  // Nested subagent (recursive)
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

  return null;
}
