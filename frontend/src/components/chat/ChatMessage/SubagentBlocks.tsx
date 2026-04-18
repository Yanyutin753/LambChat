import { useEffect, useState } from "react";
import { clsx } from "clsx";
import {
  CheckCircle,
  XCircle,
  Ban,
  ChevronDown,
  ChevronRight,
  Brain,
  Users,
  Box,
  Clock,
  Loader2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner, CollapsiblePill } from "../../common";
import type { CollapsibleStatus } from "../../common";
import type { MessagePart } from "../../../types";
import { MarkdownContent } from "./MarkdownContent";
import { MessagePartRenderer } from "./MessagePartRenderer";

/**
 * Calculate elapsed time between start and end (precise to milliseconds)
 */
function getElapsedTime(
  startedAt: number | undefined,
  completedAt: number | undefined,
): string | null {
  if (!startedAt) return null;
  const end = completedAt ?? Date.now();
  const ms = end - startedAt;
  if (ms < 1000) return `${ms}ms`;
  const totalSeconds = Math.floor(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}

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
          "inline-flex items-center gap-1 sm:gap-2 px-2.5 py-2 rounded-full text-xs font-medium",
          "transition-colors bg-stone-200 dark:bg-stone-700",
          "text-stone-600 dark:text-stone-300",
          "hover:bg-stone-300 dark:hover:bg-stone-600 cursor-pointer",
        )}
      >
        {/* Status indicator */}
        {isPending ? (
          <LoadingSpinner
            size="sm"
            className="shrink-0"
            color="text-[var(--theme-primary)]"
          />
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

      {isExpanded && (
        <div className="mt-1 animate-[fade-in_150ms_ease-out]">
          <div className="ml-4 pl-3 border-l-2 border-stone-300 dark:border-stone-600">
            <div className="text-xs text-stone-600 dark:text-stone-300 leading-relaxed pl-1 pt-2">
              <MarkdownContent content={content} isStreaming={isStreaming} />
            </div>
          </div>
        </div>
      )}
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
  startedAt,
  completedAt,
  status,
  error,
}: {
  agent_id: string;
  agent_name: string;
  input: string;
  result?: string;
  success?: boolean;
  isPending?: boolean;
  parts?: MessagePart[];
  startedAt?: number;
  completedAt?: number;
  status?: "pending" | "running" | "complete" | "error" | "cancelled";
  error?: string;
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);
  const hasContent = (parts && parts.length > 0) || result;

  // Live elapsed time while running
  const [liveElapsed, setLiveElapsed] = useState<string | null>(null);

  useEffect(() => {
    if (!startedAt || completedAt) {
      // Task not started or already completed - clear live timer
      setLiveElapsed(null);
      return;
    }

    // Update immediately
    setLiveElapsed(getElapsedTime(startedAt, completedAt));

    // Update every second while running
    const interval = setInterval(() => {
      setLiveElapsed(getElapsedTime(startedAt, completedAt));
    }, 1000);

    return () => clearInterval(interval);
  }, [startedAt, completedAt]);

  // Final elapsed time when completed
  const elapsed = completedAt
    ? getElapsedTime(startedAt, completedAt)
    : liveElapsed;

  // Determine effective status
  const effectiveStatus =
    status || (isPending ? "running" : success ? "complete" : "error");

  // Format agent name: capitalize first letter and convert underscores to spaces
  const formattedAgentName = agent_name
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");

  // Auto collapse when completed
  useEffect(() => {
    if (isPending === false) {
      setIsExpanded(false);
    }
  }, [isPending]);

  return (
    <div
      className={clsx(
        "my-3 rounded-xl overflow-hidden min-w-0 min-h-0",
        "border border-stone-200 dark:border-stone-700",
        "bg-white dark:bg-stone-900",
        effectiveStatus === "error" && "border-red-200 dark:border-red-900/50",
        effectiveStatus === "cancelled" &&
          "border-amber-200 dark:border-amber-900/50",
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
            effectiveStatus === "running"
              ? "bg-blue-100 dark:bg-blue-900/40"
              : effectiveStatus === "complete"
                ? "bg-emerald-100 dark:bg-emerald-900/40"
                : effectiveStatus === "error"
                  ? "bg-red-100 dark:bg-red-900/40"
                  : effectiveStatus === "cancelled"
                    ? "bg-amber-100 dark:bg-amber-900/40"
                    : "bg-stone-100 dark:bg-stone-800",
          )}
        >
          {effectiveStatus === "running" ? (
            <Loader2
              size={14}
              className="text-blue-600 dark:text-blue-400 animate-spin"
            />
          ) : effectiveStatus === "complete" ? (
            <CheckCircle
              size={14}
              className="text-emerald-600 dark:text-emerald-400"
            />
          ) : effectiveStatus === "error" ? (
            <XCircle size={14} className="text-red-600 dark:text-red-400" />
          ) : effectiveStatus === "cancelled" ? (
            <Ban size={14} className="text-amber-600 dark:text-amber-400" />
          ) : (
            <Users size={14} className="text-stone-500 dark:text-stone-400" />
          )}
        </div>

        <div className="flex-1 min-w-0 text-left">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-stone-800 dark:text-stone-200 truncate">
              {formattedAgentName}
            </span>
          </div>
          {input && !isExpanded && (
            <p className="text-xs text-stone-500 dark:text-stone-400 truncate mt-0.5 max-w-md whitespace-nowrap">
              {input}
            </p>
          )}
        </div>

        {/* Elapsed time */}
        {elapsed && (
          <div className="flex items-center gap-1 text-xs text-stone-400 dark:text-stone-500">
            <Clock size={12} />
            <span>{elapsed}</span>
          </div>
        )}

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
        <div className="px-4 pb-4 space-y-3 max-h-[500px] overflow-y-auto">
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
            <div className="space-y-2 pl-3 border-l-2 border-stone-200 dark:border-stone-700 overflow-y-auto min-w-0">
              {parts.map((part, index) => (
                <MessagePartRenderer
                  key={index}
                  part={part}
                  isStreaming={isPending}
                  isLast={index === parts.length - 1}
                />
              ))}
            </div>
          )}

          {/* Error message */}
          {error && effectiveStatus === "error" && (
            <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50">
              <div className="text-xs text-red-600 dark:text-red-400 font-medium mb-1">
                {t("chat.message.error")}
              </div>
              <div className="text-xs text-red-700 dark:text-red-300 leading-relaxed">
                {error}
              </div>
            </div>
          )}

          {/* Result */}
          {result && effectiveStatus === "complete" && (
            <div className="p-3 rounded-lg bg-stone-50 dark:bg-stone-800/50 border border-stone-100 dark:border-stone-700">
              <div className="text-xs text-stone-500 dark:text-stone-400 mb-1.5 font-medium">
                {t("chat.message.result")}
              </div>
              <div className="text-xs text-stone-700 dark:text-stone-300 overflow-y-auto leading-relaxed">
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

// Sandbox status block component
export function SandboxItem({
  status,
  sandboxId,
  error,
}: {
  status: "starting" | "ready" | "error" | "cancelled";
  sandboxId?: string;
  error?: string;
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  const hasDetails =
    (status === "ready" && sandboxId) ||
    (status === "error" && error) ||
    status === "cancelled";

  const pillStatus: CollapsibleStatus =
    status === "starting"
      ? "loading"
      : status === "ready"
        ? "success"
        : status === "cancelled"
          ? "cancelled"
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
        <div className="mt-1 ml-4 pl-3 border-l-2 border-stone-300 dark:border-stone-600 max-h-40 overflow-y-auto">
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
          {status === "cancelled" && (
            <div className="text-xs text-amber-600 dark:text-amber-400 pl-1 py-1">
              {t("chat.cancelled")}
            </div>
          )}
        </div>
      )}
    </CollapsiblePill>
  );
}
