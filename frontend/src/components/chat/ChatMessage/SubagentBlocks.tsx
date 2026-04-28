import {
  useEffect,
  useState,
  useCallback,
  useRef,
  useLayoutEffect,
} from "react";
import { clsx } from "clsx";
import {
  CheckCircle,
  XCircle,
  Ban,
  ChevronRight,
  Brain,
  Users,
  Box,
  Loader2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner, CollapsiblePill } from "../../common";
import type { CollapsibleStatus } from "../../common";
import type { MessagePart } from "../../../types";
import { MarkdownContent } from "./MarkdownContent";
import { MessagePartRenderer } from "./MessagePartRenderer";
import {
  createSubagentAnchorOwnerId,
  createSubagentPanelKey,
} from "./messagePartAnchors";
import {
  openPersistentToolPanel,
  updatePersistentToolPanel,
  isPersistentToolPanelOpen,
} from "./items/persistentToolPanelState";
import {
  subagentPanelStore,
  type SubagentPanelData,
} from "./subagentPanelStore";
import {
  isNearSubagentPanelBottom,
  shouldAutoScrollSubagentPanel,
} from "./subagentPanelScroll";
import { shouldAutoOpenSubagentPanel } from "./subagentPanelControl";

function useSubagentPanelData(agentId: string): SubagentPanelData | undefined {
  const [, forceRender] = useState(0);

  useEffect(() => {
    const listener = () => forceRender((n) => n + 1);
    return subagentPanelStore.subscribe(agentId, listener);
  }, [agentId]);

  return subagentPanelStore.get(agentId);
}

function formatSubagentName(agentName: string): string {
  return agentName
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function buildSubagentPanelState(data: SubagentPanelData) {
  const effectiveStatus =
    data.status ||
    (data.isPending ? "running" : data.success ? "complete" : "error");
  const timestamp = data.completedAt ?? data.startedAt;
  const elapsed = data.completedAt
    ? getElapsedTime(data.startedAt, data.completedAt)
    : null;
  const panelStatus: CollapsibleStatus =
    effectiveStatus === "running"
      ? "loading"
      : effectiveStatus === "complete"
        ? "success"
        : effectiveStatus === "error"
          ? "error"
          : effectiveStatus === "cancelled"
            ? "cancelled"
            : "idle";
  const subtitle = [
    timestamp ? formatTimestamp(timestamp) : undefined,
    elapsed || undefined,
  ]
    .filter(Boolean)
    .join(" · ");

  return {
    effectiveStatus,
    panelStatus,
    subtitle: subtitle || undefined,
    panelKey: createSubagentPanelKey(data.agentId),
    formattedAgentName: formatSubagentName(data.agentName),
  };
}

// eslint-disable-next-line react-refresh/only-export-components
export function openSubagentPanelByAgentId(agentId: string): boolean {
  const data = subagentPanelStore.get(agentId);
  if (!data) {
    return false;
  }

  const { panelStatus, subtitle, panelKey, formattedAgentName } =
    buildSubagentPanelState(data);

  if (isPersistentToolPanelOpen(panelKey)) {
    return true;
  }

  openPersistentToolPanel({
    title: formattedAgentName,
    icon: <Users size={16} />,
    status: panelStatus,
    subtitle,
    panelKey,
    children: <SubagentPanelContent agentId={agentId} />,
  });

  return true;
}

// ==========================================
// Subagent panel content (reactive)
// ==========================================

function SubagentPanelContent({ agentId }: { agentId: string }) {
  const { t } = useTranslation();
  const data = useSubagentPanelData(agentId);
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, []);

  const handleScroll = useCallback(() => {
    const scroller = scrollRef.current;
    if (!scroller) return;
    userScrolledUpRef.current = !isNearSubagentPanelBottom(scroller);
  }, []);

  useLayoutEffect(() => {
    if (
      !shouldAutoScrollSubagentPanel({
        scroller: scrollRef.current,
        userScrolledUp: userScrolledUpRef.current,
      })
    ) {
      return;
    }

    scrollToBottom();
  });

  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller || typeof ResizeObserver === "undefined") {
      return;
    }

    const observer = new ResizeObserver(() => {
      if (
        shouldAutoScrollSubagentPanel({
          scroller,
          userScrolledUp: userScrolledUpRef.current,
        })
      ) {
        scrollToBottom();
      }
    });

    observer.observe(scroller);
    if (contentRef.current) {
      observer.observe(contentRef.current);
    }

    return () => observer.disconnect();
  }, [scrollToBottom]);

  if (!data) return null;

  const effectiveStatus =
    data.status ||
    (data.isPending ? "running" : data.success ? "complete" : "error");

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="max-h-full overflow-y-auto p-2 sm:p-4"
    >
      <div ref={contentRef} className="space-y-3">
        {data.input && (
          <div className="p-3 sm:p-4 rounded-lg sm:rounded-xl bg-stone-100 dark:bg-stone-700/50">
            <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-2 font-medium">
              {t("chat.message.args")}
            </div>
            <div className="text-sm text-stone-600 dark:text-stone-300 leading-relaxed">
              <MarkdownContent content={data.input} />
            </div>
          </div>
        )}
        {data.parts && data.parts.length > 0 && (
          <div className="space-y-2 pl-3 border-l-2 border-stone-200 dark:border-stone-700">
            {data.parts.map((part, index) => (
              <MessagePartRenderer
                key={index}
                part={part}
                messageId={createSubagentAnchorOwnerId(agentId)}
                partIndex={index}
                isStreaming={data.isPending}
                isLast={index === data.parts!.length - 1}
              />
            ))}
          </div>
        )}
        {data.error && effectiveStatus === "error" && (
          <div className="p-3 sm:p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50">
            <div className="text-xs text-red-600 dark:text-red-400 font-medium mb-1">
              {t("chat.message.error")}
            </div>
            <div className="text-xs text-red-700 dark:text-red-300 leading-relaxed">
              {data.error}
            </div>
          </div>
        )}
        {data.result && effectiveStatus === "complete" && (
          <div className="p-3 sm:p-4 rounded-lg sm:rounded-xl bg-stone-100 dark:bg-stone-700/50">
            <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-2 font-medium">
              {t("chat.message.result")}
            </div>
            <div className="text-sm text-stone-700 dark:text-stone-300 leading-relaxed">
              <MarkdownContent content={data.result} />
            </div>
          </div>
        )}
        {data.isPending && !data.parts?.length && (
          <div className="flex items-center gap-2 text-stone-500 dark:text-stone-400">
            <LoadingSpinner size="sm" />
            <span className="text-sm">{t("chat.message.executing")}</span>
          </div>
        )}
        <div ref={bottomRef} className="h-px" />
      </div>
    </div>
  );
}

// ==========================================
// Utility
// ==========================================

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

function formatTimestamp(ts: number): string {
  const d = new Date(ts);
  const YY = String(d.getFullYear()).padStart(4, "0");
  const MM = String(d.getMonth() + 1).padStart(2, "0");
  const DD = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${YY}-${MM}-${DD} ${hh}:${mm}:${ss}`;
}

// Thinking Block - pill button, content in sidebar panel
export function ThinkingBlock({
  content,
  isStreaming,
  panelKey,
}: {
  content: string;
  isStreaming?: boolean;
  panelKey?: string;
}) {
  const { t } = useTranslation();

  const status: CollapsibleStatus = isStreaming ? "loading" : "success";

  useEffect(() => {
    if (!isPersistentToolPanelOpen(panelKey)) return;
    updatePersistentToolPanel(
      (prev) => ({
        ...prev,
        status,
        children: (
          <div className="p-3 sm:p-4 [&_.markdown-preview]:thinking-content">
            <MarkdownContent content={content} isStreaming={isStreaming} />
          </div>
        ),
      }),
      panelKey,
    );
  }, [content, isStreaming, panelKey, status]);

  return (
    <CollapsiblePill
      status={status}
      icon={
        <Brain
          size={12}
          className="shrink-0 text-stone-500 dark:text-stone-400"
        />
      }
      label={
        isStreaming ? t("chat.message.thinking") : t("chat.message.thought")
      }
      variant="thinking"
      animatedDots={isStreaming}
      expandable={!!content}
      onPanelOpen={() => {
        openPersistentToolPanel({
          title: t("chat.message.thought"),
          icon: <Brain size={16} />,
          status,
          panelKey,
          children: (
            <div className="p-3 sm:p-4 [&_.markdown-preview]:thinking-content">
              <MarkdownContent content={content} isStreaming={isStreaming} />
            </div>
          ),
        });
      }}
    />
  );
}

// Subagent Block - compact card, content always in sidebar panel
export function SubagentBlock({
  agent_id,
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
  const {
    effectiveStatus,
    panelStatus,
    subtitle,
    panelKey,
    formattedAgentName,
  } = buildSubagentPanelState({
    agentId: agent_id,
    agentName: agent_name,
    input,
    result,
    success,
    error,
    isPending,
    parts,
    startedAt,
    completedAt,
    status,
  });
  const elapsed = completedAt ? getElapsedTime(startedAt, completedAt) : null;

  // Keep sidebar panel data in sync
  useEffect(() => {
    subagentPanelStore.set({
      agentId: agent_id,
      agentName: agent_name,
      input,
      result,
      success,
      error,
      isPending,
      parts,
      startedAt,
      completedAt,
      status: effectiveStatus as SubagentPanelData["status"],
    });

    // Auto-open only when no panel is open; multiple running subagents should not steal focus.
    if (isPersistentToolPanelOpen(panelKey)) {
      updatePersistentToolPanel(
        (prev) => ({
          ...prev,
          status: panelStatus,
          subtitle,
        }),
        panelKey,
      );
    } else if (
      shouldAutoOpenSubagentPanel({
        status: effectiveStatus,
        anyPanelOpen: isPersistentToolPanelOpen(),
      })
    ) {
      openPersistentToolPanel({
        title: formattedAgentName,
        icon: <Users size={16} />,
        status: panelStatus,
        subtitle,
        panelKey,
        children: <SubagentPanelContent agentId={agent_id} />,
        auto: true,
      });
    }
  }, [
    agent_id,
    agent_name,
    input,
    result,
    success,
    error,
    isPending,
    parts,
    startedAt,
    completedAt,
    effectiveStatus,
    panelStatus,
    subtitle,
    formattedAgentName,
    panelKey,
  ]);

  useEffect(() => {
    return () => {
      subagentPanelStore.delete(agent_id);
    };
  }, [agent_id]);

  const handleOpenInPanel = useCallback(() => {
    openPersistentToolPanel({
      title: formattedAgentName,
      icon: <Users size={16} />,
      status: panelStatus,
      subtitle,
      panelKey,
      children: <SubagentPanelContent agentId={agent_id} />,
    });
  }, [formattedAgentName, panelStatus, subtitle, panelKey, agent_id]);

  return (
    <div
      className={clsx(
        "my-1.5 rounded-xl overflow-hidden min-w-0 group",
        "border transition-all duration-200",
        effectiveStatus === "running" &&
          "border-stone-200/60 dark:border-stone-700/40 bg-stone-50/50 dark:bg-stone-800/30",
        effectiveStatus === "complete" &&
          "border-stone-200/60 dark:border-stone-700/40 bg-stone-50/50 dark:bg-stone-800/30",
        effectiveStatus === "error" &&
          "border-red-200/60 dark:border-red-900/40 bg-gradient-to-r from-red-50/60 to-transparent dark:from-red-950/20",
        effectiveStatus === "cancelled" &&
          "border-stone-200/60 dark:border-stone-700/40 bg-stone-50/50 dark:bg-stone-800/30",
        (!effectiveStatus || effectiveStatus === "pending") &&
          "border-stone-200/60 dark:border-stone-700/40",
      )}
    >
      <div
        className="flex items-center gap-3 px-3.5 py-2.5 cursor-pointer transition-colors hover:bg-white/60 dark:hover:bg-white/5"
        onClick={handleOpenInPanel}
      >
        <div
          className={clsx(
            "flex h-7 w-7 items-center justify-center rounded-lg shrink-0",
            effectiveStatus === "running" && "bg-amber-500/10",
            effectiveStatus === "complete" && "bg-emerald-500/10",
            effectiveStatus === "error" && "bg-red-500/10",
            effectiveStatus === "cancelled" && "bg-amber-500/10",
            (!effectiveStatus || effectiveStatus === "pending") &&
              "bg-stone-500/10",
          )}
        >
          {effectiveStatus === "running" ? (
            <Loader2
              size={13}
              className="text-amber-500 dark:text-amber-400 animate-spin"
            />
          ) : effectiveStatus === "complete" ? (
            <CheckCircle
              size={13}
              className="text-emerald-500 dark:text-emerald-400"
            />
          ) : effectiveStatus === "error" ? (
            <XCircle size={13} className="text-red-500 dark:text-red-400" />
          ) : effectiveStatus === "cancelled" ? (
            <Ban size={13} className="text-amber-500 dark:text-amber-400" />
          ) : (
            <ChevronRight
              size={13}
              className="text-stone-400 dark:text-stone-500"
            />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <span
            className={clsx(
              "text-[13px] font-medium truncate block",
              effectiveStatus === "running" &&
                "text-stone-700 dark:text-stone-300",
              effectiveStatus === "complete" &&
                "text-stone-700 dark:text-stone-300",
              effectiveStatus === "error" && "text-red-700 dark:text-red-300",
              effectiveStatus === "cancelled" &&
                "text-stone-700 dark:text-stone-300",
              (!effectiveStatus || effectiveStatus === "pending") &&
                "text-stone-600 dark:text-stone-400",
            )}
          >
            {formattedAgentName}
          </span>
          {input && (
            <p className="text-[11px] text-stone-400 dark:text-stone-500 truncate mt-px">
              {input}
            </p>
          )}
        </div>

        {elapsed && (
          <span
            className={clsx(
              "text-[11px] shrink-0 tabular-nums tracking-tight px-1.5 py-0.5 rounded-md",
              effectiveStatus === "running" &&
                "text-stone-400 dark:text-stone-500 bg-stone-500/5",
              effectiveStatus === "complete" &&
                "text-stone-400 dark:text-stone-500 bg-stone-500/5",
              effectiveStatus === "error" &&
                "text-red-400 dark:text-red-500 bg-red-500/5",
              effectiveStatus === "cancelled" &&
                "text-stone-400 dark:text-stone-500 bg-stone-500/5",
            )}
          >
            {elapsed}
          </span>
        )}
      </div>
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
      label={
        status === "starting"
          ? t("chat.sandbox.initializing")
          : status === "ready"
            ? t("chat.sandbox.ready")
            : t("chat.sandbox.name")
      }
      expandable={!!hasDetails}
      onExpandChange={setIsExpanded}
      animatedDots={status === "starting"}
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
