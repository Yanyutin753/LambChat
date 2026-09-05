import { memo, useMemo } from "react";
import { History, Search, User, MessageSquareText, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { extractText } from "./toolUtils";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";

// ── Types ────────────────────────────────────────────────────────────────

interface HistorySearchItem {
  session_id: string;
  run_id?: string | null;
  session_name?: string | null;
  completed_at?: string | null;
  user_message_preview?: string | null;
  assistant_final_preview?: string | null;
  match_source?: string | null;
}

interface HistoryDetailTurn {
  run_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  user_message?: string | null;
  assistant_final?: string | null;
}

interface ParsedHistory {
  kind: "search" | "detail";
  items?: HistorySearchItem[];
  turns?: HistoryDetailTurn[];
  sessionName?: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────

function parseHistoryResult(result: unknown): ParsedHistory | null {
  const text = extractText(result as never);
  if (!text) return null;
  try {
    const raw = JSON.parse(text);
    if (Array.isArray(raw?.items)) {
      return { kind: "search", items: raw.items as HistorySearchItem[] };
    }
    if (Array.isArray(raw?.turns)) {
      return {
        kind: "detail",
        turns: raw.turns as HistoryDetailTurn[],
        sessionName: raw?.session?.name,
      };
    }
    return null;
  } catch {
    return null;
  }
}

function formatHistoryDate(iso?: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function matchSourceLabel(
  source: string | null | undefined,
  t: (key: string) => string,
): string | null {
  if (source === "user") return t("chat.message.toolHistoryMatchUser");
  if (source === "assistant")
    return t("chat.message.toolHistoryMatchAssistant");
  if (source === "both") return t("chat.message.toolHistoryMatchBoth");
  return null;
}

// ── Shared fragments ─────────────────────────────────────────────────────

function HistoryQueryChip({
  toolName,
  args,
  size,
}: {
  toolName: string;
  args: Record<string, unknown>;
  size: "compact" | "detail";
}) {
  const query = (args.query as string) || "";
  const sessionId = (args.session_id as string) || "";
  const isSearch = toolName === "search_conversation_history";
  const isDetail = toolName === "get_conversation_detail";
  const value = isDetail ? sessionId : query;
  if (!value) return null;

  return (
    <ToolArgsBlock size={size}>
      {isSearch ? (
        <Search
          size={size === "detail" ? 14 : 12}
          className="shrink-0 text-sky-500 dark:text-sky-400"
        />
      ) : (
        <History
          size={size === "detail" ? 14 : 12}
          className="shrink-0 text-sky-500 dark:text-sky-400"
        />
      )}
      <span className="text-sky-600 dark:text-sky-400 font-mono font-medium min-w-0 truncate">
        {isSearch ? truncate(value, 80) : truncate(value, 36)}
      </span>
    </ToolArgsBlock>
  );
}

function PreviewLine({
  icon,
  label,
  text,
}: {
  icon: React.ReactNode;
  label: string;
  text: string;
}) {
  if (!text) return null;
  return (
    <div className="flex items-start gap-1.5 min-w-0">
      <span className="inline-flex items-center gap-1 shrink-0 text-10 font-medium text-theme-text-tertiary uppercase tracking-wide mt-0.5">
        {icon}
        {label}
      </span>
      <span className="text-xs text-theme-text-secondary leading-relaxed min-w-0 break-words line-clamp-2">
        {text}
      </span>
    </div>
  );
}

// ── Panel detail ─────────────────────────────────────────────────────────

/** 面板详情：实时跟随 toolCallPanelStore 数据重建（结果到达即刷新） */
function ConversationHistoryDetail({
  toolName,
  args,
  result,
}: ToolDetailProps & { toolName: string }) {
  const { t } = useTranslation();
  const parsed = useMemo(() => parseHistoryResult(result), [result]);
  const hasRawFallback = !!result && !parsed;

  return (
    <div className="flex h-full min-h-0 flex-col space-y-3 overflow-y-auto p-2 sm:p-4 [&_pre]:!max-h-none">
      <HistoryQueryChip toolName={toolName} args={args} size="detail" />

      {parsed?.kind === "search" && parsed.items && parsed.items.length > 0 && (
        <div className="space-y-2">
          {parsed.items.map((item, i) => {
            const badge = matchSourceLabel(item.match_source, t);
            return (
              <div
                key={item.session_id + (item.run_id || "") + i}
                className="rounded-xl bg-theme-bg border border-theme-border px-3.5 py-3 space-y-2 shadow-[0_1px_2px_rgb(0_0_0/0.04)]"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-sm font-semibold text-theme-text truncate flex-1">
                    {item.session_name || item.session_id}
                  </span>
                  {badge && (
                    <span className="shrink-0 text-10 px-2 py-0.5 rounded-md bg-sky-50 dark:bg-sky-950/40 ring-1 ring-sky-200/60 dark:ring-sky-800/40 text-sky-600 dark:text-sky-400 font-medium">
                      {badge}
                    </span>
                  )}
                  {item.completed_at && (
                    <span className="shrink-0 inline-flex items-center gap-1 text-10 tabular-nums text-theme-text-tertiary">
                      <Clock size={10} className="opacity-50" />
                      {formatHistoryDate(item.completed_at)}
                    </span>
                  )}
                </div>
                <PreviewLine
                  icon={<User size={10} />}
                  label={t("chat.message.toolHistoryUser")}
                  text={truncate(item.user_message_preview || "", 160)}
                />
                <PreviewLine
                  icon={<MessageSquareText size={10} />}
                  label={t("chat.message.toolHistoryAssistant")}
                  text={truncate(item.assistant_final_preview || "", 200)}
                />
              </div>
            );
          })}
        </div>
      )}

      {parsed?.kind === "detail" && parsed.turns && parsed.turns.length > 0 && (
        <div className="space-y-2">
          {parsed.sessionName && (
            <div className="text-sm font-semibold text-theme-text px-1">
              {parsed.sessionName}
            </div>
          )}
          {parsed.turns.map((turn, i) => (
            <div
              key={turn.run_id || i}
              className="rounded-xl bg-theme-bg border border-theme-border px-3.5 py-3 space-y-2 shadow-[0_1px_2px_rgb(0_0_0/0.04)]"
            >
              <PreviewLine
                icon={<User size={10} />}
                label={t("chat.message.toolHistoryUser")}
                text={turn.user_message || ""}
              />
              <PreviewLine
                icon={<MessageSquareText size={10} />}
                label={t("chat.message.toolHistoryAssistant")}
                text={turn.assistant_final || ""}
              />
            </div>
          ))}
        </div>
      )}

      {hasRawFallback && (
        <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words p-3 rounded-lg bg-theme-bg border border-theme-border">
          {truncate(extractText(result as never), 600)}
          <ToolHoverCopyButton
            text={extractText(result as never)}
            position="result"
          />
        </pre>
      )}
    </div>
  );
}

// ── Item ─────────────────────────────────────────────────────────────────

const ConversationHistoryItem = memo(function ConversationHistoryItem({
  id,
  toolName,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
  id?: string;
  toolName: string;
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

  const isSearch = toolName === "search_conversation_history";
  const isDetail = toolName === "get_conversation_detail";
  const query = (args.query as string) || "";
  const sessionId = (args.session_id as string) || "";

  const parsed = useMemo(() => parseHistoryResult(result), [result]);
  const items = parsed?.kind === "search" ? parsed.items || [] : [];
  const turns = parsed?.kind === "detail" ? parsed.turns || [] : [];

  // 参数生成中（无 result）也允许打开面板：实时等待结果
  const canExpand =
    !!query || !!sessionId || items.length > 0 || turns.length > 0 || isPending;

  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const count = isSearch ? items.length : turns.length;
  const titleLabel = isSearch
    ? t("chat.message.toolHistorySearch")
    : t("chat.message.toolHistoryDetail");
  const sessionName =
    parsed?.kind === "detail" ? parsed.sessionName : undefined;

  const pillLabel = isSearch
    ? `${titleLabel} ${query ? `"${truncate(query, 24)}"` : ""}${
        count > 0 ? ` (${count})` : ""
      }`.trim()
    : `${titleLabel} ${
        sessionName || (sessionId ? truncate(sessionId, 14) : "")
      }`.trim();

  const detailContent = canExpand && (
    <ConversationHistoryDetail
      toolName={toolName}
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  // ── Inline (compact) view ──

  const inlinePreviewLimit = isDetail ? 2 : 3;
  const inlineRows = isSearch
    ? items.slice(0, inlinePreviewLimit).map((item, i) => (
        <div
          key={item.session_id + (item.run_id || "") + i}
          className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-theme-bg border border-theme-border"
        >
          <span className="text-xs text-theme-text min-w-0 truncate flex-1 font-medium">
            {item.session_name || item.session_id}
          </span>
          <span className="text-10 text-theme-text-tertiary tabular-nums shrink-0">
            {formatHistoryDate(item.completed_at)}
          </span>
        </div>
      ))
    : turns.slice(0, 2).map((turn, i) => (
        <div
          key={turn.run_id || i}
          className="px-2.5 py-1.5 rounded-lg bg-theme-bg border border-theme-border space-y-1"
        >
          <div className="text-xs text-theme-text min-w-0 truncate">
            {turn.user_message || "—"}
          </div>
          <div className="text-xs text-theme-text-tertiary min-w-0 truncate">
            {turn.assistant_final || "—"}
          </div>
        </div>
      ));

  return (
    <CollapsiblePill
      status={status}
      icon={<History size={12} className="shrink-0 opacity-50" />}
      label={pillLabel}
      variant="tool"
      formatLabel={false}
      expandable={canExpand}
      onPanelOpen={() => {
        if (!canExpand) return;
        openToolLivePanel({
          id,
          title: titleLabel,
          icon: <History size={16} />,
          status,
          subtitle: isSearch ? query || undefined : sessionName || sessionId,
          fallback: detailContent || undefined,
          buildDetail: (data) => (
            <ConversationHistoryDetail
              toolName={toolName}
              {...toolDetailPropsFromPanelData(data)}
            />
          ),
          footer: durationFooter,
        });
      }}
    >
      {canExpand && (
        <ToolInlineDetails>
          <HistoryQueryChip toolName={toolName} args={args} size="compact" />
          {inlineRows}
          {count > inlinePreviewLimit && (
            <div className="text-xs text-theme-text-tertiary px-2.5">
              {t(
                isSearch
                  ? "chat.message.toolHistoryMoreSessions"
                  : "chat.message.toolHistoryMoreTurns",
                {
                  count: count - inlinePreviewLimit,
                },
              )}
            </div>
          )}
        </ToolInlineDetails>
      )}
    </CollapsiblePill>
  );
});

export { ConversationHistoryItem };
