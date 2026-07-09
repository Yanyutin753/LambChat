import { memo, useMemo } from "react";
import { clsx } from "clsx";
import {
  Brain,
  Search,
  Clock,
  AlertTriangle,
  BookOpen,
  Tag,
  User,
  MessageSquare,
  FolderGit2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { extractText } from "./toolUtils";
import { openPersistentToolPanel } from "./persistentToolPanelState";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { DetailSection } from "./DetailSection";
import {
  TYPE_STYLES,
  TYPE_DOTS,
  SOURCE_STYLES,
  SOURCE_DOTS,
} from "../../../panels/MemoryPanel/constants";

// ── Types ────────────────────────────────────────────────────────────────

interface MemoryItem {
  memory_id: string;
  user_id?: string;
  text: string;
  preview?: string;
  summary?: string;
  title?: string;
  type: string;
  source: string;
  storage_mode?: string;
  content_store_key?: string;
  created_at: string;
  score: number;
  staleness_warning?: string;
}

interface MemoryRecallResult {
  success: boolean;
  query?: string;
  search_mode?: string;
  memories?: MemoryItem[];
}

// ── Helpers ───────────────────────────────────────────────────────────────

function getTypeIcon(type: string) {
  switch (type) {
    case "user":
      return <User size={12} className="opacity-60" />;
    case "feedback":
      return <MessageSquare size={12} className="opacity-60" />;
    case "project":
      return <FolderGit2 size={12} className="opacity-60" />;
    case "reference":
      return <BookOpen size={12} className="opacity-60" />;
    default:
      return <Tag size={12} className="opacity-60" />;
  }
}

function formatDate(isoString: string): string {
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return "today";
    if (diffDays === 1) return "yesterday";
    if (diffDays < 30) return `${diffDays}d ago`;
    const diffMonths = Math.floor(diffDays / 30);
    if (diffMonths < 12) return `${diffMonths}mo ago`;
    const diffYears = Math.floor(diffMonths / 12);
    return `${diffYears}y ago`;
  } catch {
    return "";
  }
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(Math.round(score * 100), 100);
  const barColor =
    pct >= 80
      ? "bg-[var(--theme-primary)]"
      : pct >= 60
        ? "bg-[color-mix(in_srgb,var(--theme-primary)_64%,transparent)]"
        : "bg-[color-mix(in_srgb,var(--theme-text-tertiary)_62%,transparent)]";
  const textColor =
    pct >= 80
      ? "text-[var(--theme-primary)]"
      : pct >= 60
        ? "text-theme-text-secondary"
        : "text-theme-text-tertiary";
  return (
    <div className="flex items-center gap-1.5 w-full">
      <div className="flex-1 h-1.5 rounded-full bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg))] overflow-hidden ring-1 ring-inset ring-[color-mix(in_srgb,var(--theme-primary)_8%,transparent)]">
        <div
          className={clsx(
            "h-full rounded-full transition-all duration-500",
            barColor,
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span
        className={clsx(
          "text-[11px] tabular-nums font-semibold w-6 text-right tracking-tight",
          textColor,
        )}
      >
        {pct}
      </span>
    </div>
  );
}

// ── MemoryRecallItem ─────────────────────────────────────────────────────

const MemoryRecallItem = memo(function MemoryRecallItem({
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
  startedAt?: string;
  completedAt?: string;
}) {
  const { t } = useTranslation();
  const durationFooter = (
    <ToolDurationFooter startedAt={startedAt} completedAt={completedAt} />
  );

  const query = (args.query as string) || "";

  const parsed = useMemo((): MemoryRecallResult | null => {
    const text = extractText(result);
    if (!text) return null;
    try {
      const raw = JSON.parse(text);
      if (raw?.memories && Array.isArray(raw.memories)) return raw;
      return raw;
    } catch {
      return null;
    }
  }, [result]);

  const memories: MemoryItem[] = useMemo(() => {
    if (!parsed?.memories) return [];
    return parsed.memories;
  }, [parsed]);

  const searchMode = parsed?.search_mode || "hybrid";
  const searchModeLabel = t(`memory.searchMode.${searchMode}`, searchMode);
  const resultQuery = parsed?.query || query;

  const canExpand = !!resultQuery || memories.length > 0 || !!result;
  const pillStatus = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  // ── Panel detail content ──

  const detailContent = canExpand && (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      {/* Query summary header */}
      {resultQuery && (
        <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-[color-mix(in_srgb,var(--theme-primary)_7%,var(--theme-bg-card))] border border-[color-mix(in_srgb,var(--theme-primary)_16%,var(--theme-border))] shadow-[0_10px_24px_-22px_color-mix(in_srgb,var(--theme-primary)_45%,transparent)]">
          <Search size={14} className="text-[var(--theme-primary)] shrink-0" />
          <span className="text-sm sm:text-base text-theme-text truncate flex-1">
            {resultQuery}
          </span>
          {searchMode && (
            <span className="shrink-0 text-[10px] px-2 py-0.5 rounded-md bg-theme-bg-card ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_14%,var(--theme-border))] text-theme-text-secondary font-medium">
              {searchModeLabel}
            </span>
          )}
        </div>
      )}

      {/* Memory cards */}
      {memories.length > 0 && (
        <DetailSection
          title={t("chat.message.toolMemoryRecallCount", {
            count: memories.length,
          })}
          icon={<Brain size={12} />}
          defaultExpanded={true}
          badge={
            <span className="text-[11px] text-theme-text-tertiary tabular-nums">
              {memories.length}
            </span>
          }
        >
          <div className="grid auto-grid-cols gap-3">
            {memories.map((mem, i) => {
              const typeStyle = TYPE_STYLES[mem.type] || TYPE_STYLES.user;
              const typeDot = TYPE_DOTS[mem.type] || TYPE_DOTS.user;
              const sourceStyle = SOURCE_STYLES[mem.source] || "";
              const sourceDot = SOURCE_DOTS[mem.source] || "";
              return (
                <div
                  key={mem.memory_id || i}
                  className={clsx(
                    "group/mem rounded-xl overflow-hidden border bg-theme-bg-card",
                    "shadow-[0_1px_2px_rgb(0_0_0/0.04)] hover:shadow-[0_12px_28px_-24px_color-mix(in_srgb,var(--theme-primary)_42%,transparent)] transition-all duration-200",
                    "border-theme-border",
                  )}
                >
                  <div className="px-4 py-3.5 space-y-3">
                    {/* Header: title + badges */}
                    <div className="flex items-start gap-2">
                      <div className="flex-1 min-w-0">
                        {mem.title && (
                          <div className="text-sm sm:text-base font-semibold text-theme-text truncate leading-snug tracking-tight">
                            {mem.title}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Summary / content preview */}
                    {(mem.summary || mem.preview) && (
                      <p className="text-xs sm:text-sm text-theme-text-secondary/80 leading-relaxed line-clamp-3">
                        {mem.summary || mem.preview}
                      </p>
                    )}

                    {/* Score bar */}
                    <ScoreBar score={mem.score} />

                    {/* Footer: type badge + source + date */}
                    <div className="flex items-center gap-2 flex-wrap">
                      {/* Type badge */}
                      <span
                        className={clsx(
                          "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium",
                          typeStyle,
                        )}
                      >
                        <span
                          className={clsx("w-1.5 h-1.5 rounded-full", typeDot)}
                        />
                        {getTypeIcon(mem.type)}
                        {t(`memory.type.${mem.type}`, mem.type)}
                      </span>

                      {/* Source badge */}
                      {sourceStyle && (
                        <span
                          className={clsx(
                            "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium",
                            sourceStyle,
                          )}
                        >
                          <span
                            className={clsx(
                              "w-1.5 h-1.5 rounded-full",
                              sourceDot,
                            )}
                          />
                          {t(`memory.source.${mem.source}`, mem.source)}
                        </span>
                      )}

                      {/* Date */}
                      <span className="inline-flex items-center gap-1 text-xs text-theme-text-tertiary ml-auto">
                        <Clock size={10} className="opacity-50" />
                        {formatDate(mem.created_at)}
                      </span>
                    </div>

                    {/* Staleness warning */}
                    {mem.staleness_warning && (
                      <div className="flex items-start gap-1.5 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200/50 dark:border-amber-800/30">
                        <AlertTriangle
                          size={13}
                          className="text-amber-500 dark:text-amber-400 shrink-0 mt-0.5"
                        />
                        <span className="text-xs text-amber-700 dark:text-amber-300 leading-relaxed">
                          {mem.staleness_warning}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </DetailSection>
      )}

      {/* Raw result fallback */}
      {result && memories.length === 0 && !resultQuery && (
        <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words p-3 rounded-lg bg-theme-bg border border-theme-border">
          {(() => {
            const text = extractText(result);
            return text.length > 600 ? text.slice(0, 597) + "…" : text;
          })()}
          <ToolHoverCopyButton
            text={extractText(result)}
            position="result"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
          />
        </pre>
      )}
    </div>
  );

  // ── Inline (compact) view ──

  const pillLabel =
    memories.length > 0
      ? `${t("chat.message.toolMemoryRecall")} ${
          resultQuery
            ? `"${
                resultQuery.length > 30
                  ? resultQuery.slice(0, 27) + "…"
                  : resultQuery
              }"`
            : ""
        } (${memories.length})`
      : t("chat.message.toolMemoryRecall");

  return (
    <>
      <CollapsiblePill
        status={pillStatus}
        icon={<Brain size={12} className="shrink-0 opacity-50" />}
        label={pillLabel}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openPersistentToolPanel({
            title: t("chat.message.toolMemoryRecall"),
            icon: <Brain size={16} />,
            status: pillStatus,
            subtitle: resultQuery
              ? resultQuery.length > 80
                ? resultQuery.slice(0, 77) + "…"
                : resultQuery
              : undefined,
            children: detailContent,
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            {/* Compact query + count */}
            {resultQuery && (
              <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-[color-mix(in_srgb,var(--theme-primary)_6%,var(--theme-bg-card))] border border-[color-mix(in_srgb,var(--theme-primary)_12%,var(--theme-border))]">
                <Search
                  size={12}
                  className="text-[var(--theme-primary)] shrink-0"
                />
                <span className="text-xs text-theme-text-secondary truncate flex-1">
                  {resultQuery.length > 50
                    ? resultQuery.slice(0, 47) + "…"
                    : resultQuery}
                </span>
              </div>
            )}

            {/* Compact memory chips */}
            {memories.length > 0 && (
              <div className="space-y-1">
                {memories.slice(0, 5).map((mem, i) => {
                  const typeStyle = TYPE_STYLES[mem.type] || TYPE_STYLES.user;
                  return (
                    <div
                      key={mem.memory_id || i}
                      className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-theme-bg border border-theme-border hover:border-[color-mix(in_srgb,var(--theme-text-secondary)_12%,var(--theme-border))] transition-colors"
                    >
                      <span
                        className={clsx(
                          "inline-flex items-center px-1.5 py-[2px] rounded text-[10px] font-medium",
                          typeStyle,
                        )}
                      >
                        {t(`memory.type.${mem.type}`, mem.type)}
                      </span>
                      <span className="text-xs text-theme-text-secondary truncate flex-1">
                        {mem.title ||
                          (mem.summary
                            ? mem.summary.slice(0, 40)
                            : (mem.preview || "").slice(0, 40))}
                      </span>
                      <span className="text-[10px] tabular-nums text-theme-text-tertiary shrink-0">
                        {Math.round(mem.score * 100)}
                      </span>
                    </div>
                  );
                })}
                {memories.length > 5 && (
                  <div className="text-xs text-theme-text-tertiary px-2.5">
                    +{memories.length - 5} more
                  </div>
                )}
              </div>
            )}

            {result && memories.length === 0 && !resultQuery && (
              <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words overflow-y-auto min-w-0">
                {(() => {
                  const text = extractText(result);
                  return text.length > 300 ? text.slice(0, 297) + "…" : text;
                })()}
                <ToolHoverCopyButton
                  text={extractText(result)}
                  position="resultCompact"
                />
              </pre>
            )}
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { MemoryRecallItem };
