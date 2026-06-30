import {
  useEffect,
  useState,
  useCallback,
  useMemo,
  useRef,
  useLayoutEffect,
} from "react";
import { clsx } from "clsx";
import {
  CheckCircle,
  XCircle,
  Ban,
  ChevronRight,
  ChevronDown,
  Brain,
  Bot,
  Box,
  Loader2,
  Palette,
  Code2,
  FlaskConical,
  Search,
  PenTool,
  Database,
  ShieldCheck,
  Star,
  type LucideIcon,
} from "lucide-react";
import { getFluentEmojiCDN } from "@lobehub/fluent-emoji";
import { useTranslation } from "react-i18next";
import { LoadingSpinner, CollapsiblePill, CopyButton } from "../../common";
import { ImageWithSkeleton } from "./ImageWithSkeleton";
import type { CollapsibleStatus } from "../../common";
import { PersonaAvatarIcon } from "../../persona/PersonaAvatarIcon";
import {
  getEmojiAvatarUrl,
  isEmojiAvatar,
  isPersonaImageAvatar,
} from "../../persona/personaAvatar";
import type { MessagePart } from "../../../types";
import { MarkdownContent } from "./MarkdownContent";
import { MessagePartRenderer } from "./MessagePartRenderer";
import { getFullUrl } from "../../../services/api/config";
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
  startSubagentPanelScrollToBottom,
  shouldAutoScrollSubagentPanel,
} from "./subagentPanelScroll";
import {
  dismissSubagentPanelAutoOpen,
  isSubagentPanelAutoOpenDismissed,
  resetSubagentPanelAutoOpenDismissal,
  shouldAutoOpenSubagentPanel,
  shouldExpandSubagentProcessByDefault,
} from "./subagentPanelControl";
import { formatDateTime, formatDuration } from "../../../utils/datetime";
import type { PluginRuntimeContributionStates } from "../../../extensions/coreContributions";

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

type SubagentRoleIconKind =
  | "design"
  | "code"
  | "test"
  | "research"
  | "writing"
  | "data"
  | "review"
  | "grading"
  | "general";

type SubagentRoleIconMeta = {
  kind: SubagentRoleIconKind;
  icon: LucideIcon;
  className: string;
  bgClassName: string;
  emoji?: string;
};

const SUBAGENT_ROLE_ICON_META: Record<
  SubagentRoleIconKind,
  SubagentRoleIconMeta
> = {
  design: {
    kind: "design",
    icon: Palette,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  code: {
    kind: "code",
    icon: Code2,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  test: {
    kind: "test",
    icon: FlaskConical,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  research: {
    kind: "research",
    icon: Search,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  writing: {
    kind: "writing",
    icon: PenTool,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  data: {
    kind: "data",
    icon: Database,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  review: {
    kind: "review",
    icon: ShieldCheck,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
  },
  grading: {
    kind: "grading",
    icon: Star,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
    emoji: "⭐",
  },
  general: {
    kind: "general",
    icon: Bot,
    className: "text-[var(--theme-primary)]",
    bgClassName: "bg-[var(--theme-primary-light)]",
    emoji: "🤖",
  },
};

// eslint-disable-next-line react-refresh/only-export-components
export function getSubagentRoleIconMeta(
  agentName: string,
): SubagentRoleIconMeta {
  const name = agentName.toLowerCase();
  if (/(设计|design|视觉|ui|ux|brand|creative)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.design;
  }
  if (
    /(code|coding|dev|developer|engineer|frontend|backend|程序|开发|工程)/i.test(
      name,
    )
  ) {
    return SUBAGENT_ROLE_ICON_META.code;
  }
  if (/(test|qa|quality|验收|测试)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.test;
  }
  if (/(research|search|investigate|analysis|分析|研究|调研)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.research;
  }
  if (/(write|writer|copy|content|editor|文案|写作|编辑)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.writing;
  }
  if (/(data|database|db|analytics|数据)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.data;
  }
  if (/(review|security|audit|critic|审查|审核|安全)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.review;
  }
  if (/(rubric|grading|grader|评分|评审)/i.test(name)) {
    return SUBAGENT_ROLE_ICON_META.grading;
  }
  return SUBAGENT_ROLE_ICON_META.general;
}

// eslint-disable-next-line react-refresh/only-export-components
export function getSubagentAvatarImageUrl(
  avatar: string | null | undefined,
): string | null {
  if (isEmojiAvatar(avatar)) {
    return getEmojiAvatarUrl(avatar);
  }
  if (isPersonaImageAvatar(avatar)) {
    return getFullUrl(avatar) ?? avatar;
  }
  return null;
}

function SubagentStatusIcon({
  status,
  className,
  size = 13,
}: {
  status: SubagentPanelData["status"] | "pending" | undefined;
  className?: string;
  size?: number;
}) {
  if (status === "running") {
    return (
      <Loader2
        size={size}
        className={clsx(
          "text-amber-500 dark:text-amber-400 animate-spin",
          className,
        )}
      />
    );
  }
  if (status === "complete") {
    return (
      <CheckCircle
        size={size}
        className={clsx("text-emerald-500 dark:text-emerald-400", className)}
      />
    );
  }
  if (status === "error") {
    return (
      <XCircle
        size={size}
        className={clsx("text-red-500 dark:text-red-400", className)}
      />
    );
  }
  if (status === "cancelled") {
    return (
      <Ban
        size={size}
        className={clsx("text-stone-400 dark:text-stone-500", className)}
      />
    );
  }
  return (
    <ChevronRight
      size={size}
      className={clsx("text-stone-400 dark:text-stone-500", className)}
    />
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function buildSubagentPanelState(data: SubagentPanelData) {
  const effectiveStatus =
    data.status ||
    (data.isPending ? "running" : data.success ? "complete" : "error");
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
  const subtitle = data.startedAt ? formatDateTime(data.startedAt) : undefined;

  return {
    effectiveStatus,
    panelStatus,
    subtitle: subtitle || undefined,
    panelKey: createSubagentPanelKey(data.agentId),
    formattedAgentName: formatSubagentName(data.agentName),
  };
}

function createSubagentPanelFooter(subtitle: string | undefined) {
  if (!subtitle) return undefined;
  return (
    <div className="flex justify-end border-t border-theme-border bg-theme-bg-card px-3 py-2 sm:px-4">
      <span
        className="shrink-0 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-theme-bg-subtle px-1.5 text-[10px] font-semibold leading-none text-theme-text-secondary"
        title={subtitle}
      >
        {subtitle}
      </span>
    </div>
  );
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

  resetSubagentPanelAutoOpenDismissal();
  openPersistentToolPanel({
    title: formattedAgentName,
    icon: <Bot size={16} />,
    status: panelStatus,
    panelKey,
    children: <SubagentPanelContent agentId={agentId} />,
    footer: createSubagentPanelFooter(subtitle),
    onUserClose: dismissSubagentPanelAutoOpen,
  });

  return true;
}

// ==========================================
// Collapsible section for panel content
// ==========================================

function extractPartsText(parts: MessagePart[]): string {
  return parts
    .map((p) => {
      if (p.type === "text" || p.type === "thinking") return p.content;
      if (p.type === "tool")
        return `[${p.name}]${p.result != null ? " " + String(p.result) : ""}`;
      if (p.type === "subagent")
        return `[${p.agent_name}]${p.result ? " " + p.result : ""}`;
      return "";
    })
    .filter(Boolean)
    .join("\n\n");
}

export function CollapsibleSection({
  title,
  defaultExpanded = true,
  action,
  variant = "default",
  children,
}: {
  title: string;
  defaultExpanded?: boolean;
  action?: React.ReactNode;
  variant?: "default" | "error";
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const isError = variant === "error";
  const toggleExpanded = useCallback(() => setExpanded((v) => !v), []);

  return (
    <div
      className={clsx(
        "collapsible-section-card p-3 sm:p-4 rounded-lg sm:rounded-xl",
        isError
          ? "collapsible-section-card--error bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-900/50"
          : "collapsible-section-card--default bg-theme-bg-card border border-theme-border shadow-sm",
      )}
    >
      <div className="flex items-center justify-between w-full gap-2">
        <button
          type="button"
          aria-expanded={expanded}
          onClick={toggleExpanded}
          className="flex items-center gap-1.5 flex-1 min-w-0 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--theme-primary)]/50 rounded-md"
        >
          <ChevronDown
            size={12}
            className={clsx(
              "transition-transform duration-200",
              isError
                ? "text-red-500 dark:text-red-400"
                : "text-theme-text-tertiary",
              !expanded && "-rotate-90",
            )}
          />
          <span
            className={clsx(
              "text-xs uppercase tracking-wider font-medium",
              isError
                ? "text-red-600 dark:text-red-400"
                : "text-theme-text-tertiary",
            )}
          >
            {title}
          </span>
        </button>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {expanded && (
        <div className="mt-2 animate-[fade-in_150ms_ease-out]">{children}</div>
      )}
    </div>
  );
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
  const programmaticScrollRef = useRef(false);
  const stopAutoScrollRef = useRef<(() => void) | null>(null);

  const markProgrammaticScroll = useCallback(() => {
    programmaticScrollRef.current = true;
    window.setTimeout(() => {
      programmaticScrollRef.current = false;
    }, 0);
  }, []);

  const stopAutoScroll = useCallback(() => {
    stopAutoScrollRef.current?.();
    stopAutoScrollRef.current = null;
  }, []);

  const startAutoScroll = useCallback(() => {
    stopAutoScroll();
    stopAutoScrollRef.current = startSubagentPanelScrollToBottom({
      scroller: scrollRef.current,
      footer: bottomRef.current,
      shouldAbort: () => userScrolledUpRef.current,
      onAutoScroll: markProgrammaticScroll,
    });
  }, [markProgrammaticScroll, stopAutoScroll]);

  useEffect(() => {
    return () => stopAutoScroll();
  }, [stopAutoScroll]);

  const scrollToBottom = useCallback(() => {
    startAutoScroll();
  }, [startAutoScroll]);

  const handleScroll = useCallback(() => {
    const scroller = scrollRef.current;
    if (!scroller || programmaticScrollRef.current) return;
    userScrolledUpRef.current = !isNearSubagentPanelBottom(scroller);
    if (userScrolledUpRef.current) {
      stopAutoScroll();
    }
  }, [stopAutoScroll]);

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
  }, [data, scrollToBottom]);

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
        startAutoScroll();
      }
    });

    observer.observe(scroller);
    if (contentRef.current) {
      observer.observe(contentRef.current);
    }

    return () => observer.disconnect();
  }, [startAutoScroll]);

  if (!data) return null;

  const effectiveStatus =
    data.status ||
    (data.isPending ? "running" : data.success ? "complete" : "error");

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="h-full min-h-0 overflow-y-auto p-2 sm:p-4"
    >
      <div ref={contentRef} className="space-y-3">
        {data.input && (
          <CollapsibleSection
            title={t("chat.message.args")}
            action={<CopyButton text={data.input} />}
          >
            <div className="text-sm text-stone-600 dark:text-stone-300 leading-relaxed">
              <MarkdownContent content={data.input} />
            </div>
          </CollapsibleSection>
        )}
        {data.parts && data.parts.length > 0 && (
          <CollapsibleSection
            title={t("chat.message.processing")}
            defaultExpanded={shouldExpandSubagentProcessByDefault(
              effectiveStatus,
            )}
            action={<CopyButton text={extractPartsText(data.parts)} />}
          >
            <div className="space-y-2">
              {data.parts.map((part, index) => (
                <MessagePartRenderer
                  key={index}
                  part={part}
                  messageId={createSubagentAnchorOwnerId(agentId)}
                  partIndex={index}
                  isStreaming={data.isPending}
                  isLast={index === data.parts!.length - 1}
                  runtimePlugins={data.runtimePlugins}
                />
              ))}
            </div>
          </CollapsibleSection>
        )}
        {data.error && effectiveStatus === "error" && (
          <CollapsibleSection
            title={t("chat.message.error")}
            action={<CopyButton text={data.error} />}
            variant="error"
          >
            <div className="text-xs text-red-700 dark:text-red-300 leading-relaxed">
              {data.error}
            </div>
          </CollapsibleSection>
        )}
        {data.result && effectiveStatus === "complete" && (
          <CollapsibleSection
            title={t("chat.message.result")}
            action={<CopyButton text={data.result} />}
          >
            <div className="text-sm text-stone-700 dark:text-stone-300 leading-relaxed">
              <MarkdownContent content={data.result} />
            </div>
          </CollapsibleSection>
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

  // Show a brief preview of the reasoning content in the pill label
  const preview = useMemo(() => {
    if (isStreaming || !content) return "";
    const text = content.replace(/\n+/g, " ").trim();
    return text.length > 80 ? text.slice(0, 80) + "…" : text;
  }, [content, isStreaming]);

  const label = isStreaming
    ? t("chat.message.thinking")
    : preview || t("chat.message.thought");

  return (
    <CollapsiblePill
      status={status}
      icon={<Brain size={12} className="shrink-0 opacity-50" />}
      label={label}
      formatLabel={false}
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
  agent_avatar,
  input,
  result,
  success,
  isPending,
  parts,
  startedAt,
  completedAt,
  status,
  error,
  runtimePlugins,
}: {
  agent_id: string;
  agent_name: string;
  agent_avatar?: string;
  input: string;
  result?: string;
  success?: boolean;
  isPending?: boolean;
  parts?: MessagePart[];
  startedAt?: number;
  completedAt?: number;
  status?: "pending" | "running" | "complete" | "error" | "cancelled";
  error?: string;
  runtimePlugins?: PluginRuntimeContributionStates;
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
    runtimePlugins,
  });
  const { t } = useTranslation();
  const roleIconMeta = getSubagentRoleIconMeta(formattedAgentName);
  const RoleIcon = roleIconMeta.icon;
  const agentAvatarUrl = getSubagentAvatarImageUrl(agent_avatar);

  // Stable serialization of parts for effect dependency — array reference
  // changes every render from the parent but content only changes on real updates.
  const partsKey = useMemo(() => JSON.stringify(parts ?? []), [parts]);

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
      runtimePlugins,
    });

    // Auto-open only when no panel is open; multiple running subagents should not steal focus.
    if (isPersistentToolPanelOpen(panelKey)) {
      updatePersistentToolPanel(
        (prev) => ({
          ...prev,
          status: panelStatus,
          footer: createSubagentPanelFooter(subtitle),
        }),
        panelKey,
      );
    } else if (
      shouldAutoOpenSubagentPanel({
        status: effectiveStatus,
        anyPanelOpen: isPersistentToolPanelOpen(),
        autoOpenDismissed: isSubagentPanelAutoOpenDismissed(),
      })
    ) {
      openPersistentToolPanel({
        title: formattedAgentName,
        icon: <RoleIcon size={16} />,
        status: panelStatus,
        panelKey,
        children: <SubagentPanelContent agentId={agent_id} />,
        footer: createSubagentPanelFooter(subtitle),
        auto: true,
        onUserClose: dismissSubagentPanelAutoOpen,
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
    partsKey,
    startedAt,
    completedAt,
    effectiveStatus,
    panelStatus,
    subtitle,
    formattedAgentName,
    RoleIcon,
    panelKey,
    runtimePlugins,
  ]);

  useEffect(() => {
    return () => {
      subagentPanelStore.delete(agent_id);
    };
  }, [agent_id]);

  const handleOpenInPanel = useCallback(() => {
    resetSubagentPanelAutoOpenDismissal();
    openPersistentToolPanel({
      title: formattedAgentName,
      icon: <RoleIcon size={16} />,
      status: panelStatus,
      panelKey,
      children: <SubagentPanelContent agentId={agent_id} />,
      footer: createSubagentPanelFooter(subtitle),
      onUserClose: dismissSubagentPanelAutoOpen,
    });
  }, [formattedAgentName, RoleIcon, panelStatus, subtitle, panelKey, agent_id]);

  return (
    <div
      className={clsx(
        "my-1.5 rounded-xl overflow-hidden min-w-0 group relative",
        "ring-1 ring-stone-300/80 dark:ring-stone-600/60 transition-all duration-250",
        "bg-theme-bg-card",
      )}
    >
      <div
        className={clsx(
          "absolute right-2.5 top-2.5 z-[1] flex h-5 w-5 items-center justify-center rounded-full",
          "shadow-sm ring-1",
          effectiveStatus === "running" &&
            "bg-amber-100/80 dark:bg-amber-900/30 ring-amber-300/70 dark:ring-amber-700/50",
          effectiveStatus === "complete" &&
            "bg-emerald-100/80 dark:bg-emerald-900/30 ring-emerald-300/70 dark:ring-emerald-700/50",
          effectiveStatus === "error" &&
            "bg-red-100/80 dark:bg-red-900/30 ring-red-300/70 dark:ring-red-900/45",
          effectiveStatus === "cancelled" &&
            "bg-stone-200/60 dark:bg-stone-700/50 ring-stone-300/60 dark:ring-stone-600/50",
          (!effectiveStatus || effectiveStatus === "pending") &&
            "bg-stone-100 dark:bg-stone-800 ring-stone-200 dark:ring-stone-700",
        )}
        aria-label={t("chat.subagentStatus", {
          status: effectiveStatus || "pending",
        })}
      >
        <SubagentStatusIcon status={effectiveStatus} size={11} />
      </div>
      <div
        className="flex items-center gap-3 px-3.5 py-2.5 pr-10 cursor-pointer transition-colors duration-150 hover:bg-theme-bg-card/60 dark:hover:bg-theme-bg-card/10"
        onClick={handleOpenInPanel}
      >
        <div
          className={clsx(
            "relative flex h-8 w-8 items-center justify-center rounded-lg shrink-0 overflow-hidden",
            "ring-1 ring-inset ring-black/5 dark:ring-white/10",
            agentAvatarUrl
              ? "bg-white dark:bg-stone-800"
              : roleIconMeta.bgClassName,
          )}
        >
          {!agentAvatarUrl && roleIconMeta.emoji ? (
            <ImageWithSkeleton
              src={getFluentEmojiCDN(roleIconMeta.emoji!, { type: "3d" })}
              alt={roleIconMeta.emoji}
              skipUrlResolve
              inline
              loading="eager"
              style={{ objectFit: "contain" }}
            />
          ) : !agentAvatarUrl ? (
            <RoleIcon size={15} className={roleIconMeta.className} />
          ) : null}
          {agentAvatarUrl && (
            <div className="absolute inset-0 overflow-hidden rounded-full">
              <ImageWithSkeleton
                src={agentAvatarUrl}
                alt=""
                skipUrlResolve
                inline
                loading="lazy"
              />
            </div>
          )}
          {agent_avatar && !agentAvatarUrl && (
            <PersonaAvatarIcon
              avatar={agent_avatar}
              size={15}
              className="absolute"
            />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <span
            className={clsx(
              "text-[13px] font-medium truncate block",
              "text-theme-text",
            )}
          >
            {formattedAgentName}
          </span>
          {input && (
            <p className="text-[11px] text-theme-text-tertiary truncate mt-px">
              {input}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// Sandbox status block component
export function SandboxItem({
  status,
  sandboxId,
  error,
  startedAt,
  completedAt,
}: {
  status: "starting" | "ready" | "error" | "cancelled";
  sandboxId?: string;
  error?: string;
  startedAt?: string;
  completedAt?: string;
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  // Compute duration string when timing data is available
  const durationText = (() => {
    if (startedAt) {
      const startMs = new Date(startedAt).getTime();
      const endMs = completedAt
        ? new Date(completedAt).getTime()
        : status !== "starting"
          ? Date.now()
          : undefined;
      if (endMs != null && endMs > startMs) {
        return formatDuration(endMs - startMs);
      }
    }
    return undefined;
  })();

  const hasDetails =
    (status === "ready" && (sandboxId || durationText)) ||
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
        <div className="mt-1 ml-4 pl-3 border-l-2 border-theme-border max-h-40 overflow-y-auto">
          {status === "ready" && (
            <div className="text-xs text-theme-text pl-1 py-0.5 font-mono flex items-center gap-1.5">
              {sandboxId && (
                <span>{t("chat.sandboxId", { id: sandboxId })}</span>
              )}
              {durationText && (
                <span>
                  {t("chat.sandbox.elapsed", { duration: durationText })}
                </span>
              )}
            </div>
          )}
          {status === "error" && (
            <div className="text-xs text-red-600 dark:text-red-400 pl-1 py-0.5">
              {error || t("chat.sandboxInitFailed")}
              {durationText &&
                ` · ${t("chat.sandbox.elapsed", { duration: durationText })}`}
            </div>
          )}
          {status === "cancelled" && (
            <div className="text-xs text-amber-600 dark:text-amber-400 pl-1 py-1">
              {t("chat.cancelled")}
              {durationText &&
                ` · ${t("chat.sandbox.elapsed", { duration: durationText })}`}
            </div>
          )}
        </div>
      )}
    </CollapsiblePill>
  );
}
