import { memo, useMemo } from "react";
import { BookOpen, FileText, Scissors } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { CollapsiblePill } from "../../../common";
import {
  hostFromUrl,
  parseWebFetchResult,
  type WebFetchSummary,
} from "./webFetchResult";

import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { useToolStreamingLabel } from "./useToolStreamingLabel";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolResultContent } from "./McpBlockPreview";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** 供应商识别色点（对齐 WebSearchItem 的 PROVIDER_DOTS 语义） */
const PROVIDER_DOTS: Record<string, string> = {
  direct: "bg-emerald-400",
  tavily: "bg-sky-400",
  firecrawl: "bg-orange-400",
  exa: "bg-teal-400",
  jina: "bg-violet-400",
};

function ProviderBadge({ provider }: { provider: string }) {
  if (!provider) return null;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-theme-bg-card px-2 py-0.5 text-10 font-medium text-theme-text-secondary ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_14%,var(--theme-border))]">
      <span
        className={clsx(
          "size-1.5 rounded-full",
          PROVIDER_DOTS[provider] ?? "bg-theme-text-tertiary",
        )}
      />
      {provider}
    </span>
  );
}

/** 摘要 chips：字符数（主题色）+ 供应商 + 截断标记 */
function FetchSummaryChips({
  summary,
  size,
}: {
  summary: WebFetchSummary;
  size: "compact" | "detail";
}) {
  const { t } = useTranslation();
  const compact = size === "compact";
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span
        className={clsx(
          "inline-flex items-center gap-1 rounded-md font-medium",
          "bg-[color-mix(in_srgb,var(--theme-primary)_9%,transparent)] text-[var(--theme-primary)] ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_16%,transparent)]",
          compact ? "px-1.5 py-0.5 text-10" : "px-2 py-0.5 text-11",
        )}
      >
        <FileText size={compact ? 9 : 10} className="shrink-0 opacity-70" />
        {t("chat.message.toolWebFetchChars", {
          count: summary.contentChars ?? summary.content.length,
        })}
      </span>
      <ProviderBadge provider={summary.provider} />
      {summary.truncated && (
        <span className="inline-flex items-center gap-1 rounded-md bg-theme-bg-card px-1.5 py-0.5 text-10 font-medium text-amber-600 dark:text-amber-400 ring-1 ring-theme-border">
          <Scissors size={compact ? 9 : 10} className="shrink-0 opacity-70" />
          {t("chat.message.toolWebFetchTruncated")}
        </span>
      )}
    </div>
  );
}

/** 面板详情：实时跟随 toolCallPanelStore 数据重建（结果到达即刷新） */
function WebFetchDetail({ args, result }: ToolDetailProps) {
  const { t } = useTranslation();
  const url = (args.url as string) || "";
  const summary = useMemo(() => parseWebFetchResult(result), [result]);
  const hasRawFallback = !!result && summary === null;
  const host = hostFromUrl(url);

  return (
    <div className="flex h-full min-h-0 flex-col space-y-3.5 overflow-y-auto p-2 sm:p-4 [&_pre]:!max-h-none">
      {/* URL hero：主题色染色 + 光晕，面板的视觉锚点 */}
      {(url || summary?.provider) && (
        <a
          href={summary?.finalUrl || url}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2.5 rounded-xl border border-[color-mix(in_srgb,var(--theme-primary)_16%,var(--theme-border))] bg-[color-mix(in_srgb,var(--theme-primary)_7%,var(--theme-bg-card))] px-3 py-2.5 shadow-[0_10px_24px_-22px_color-mix(in_srgb,var(--theme-primary)_45%,transparent)] transition-colors hover:border-[color-mix(in_srgb,var(--theme-primary)_30%,var(--theme-border))]"
        >
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--theme-primary)_12%,transparent)] ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_18%,transparent)]">
            <BookOpen size={14} className="shrink-0 text-[var(--theme-primary)]" />
          </span>
          <span className="min-w-0 flex-1">
            {summary?.title && (
              <span className="block truncate text-14 font-semibold text-theme-text">
                {summary.title}
              </span>
            )}
            <span className="block truncate text-11 font-mono text-sky-700/80 dark:text-sky-300/70">
              {host || url}
            </span>
          </span>
          {summary && <ProviderBadge provider={summary.provider} />}
        </a>
      )}

      {summary && <FetchSummaryChips summary={summary} size="detail" />}

      {summary && (
        <div className="group/content relative min-h-0 flex-1 rounded-xl bg-theme-bg border border-theme-border px-3.5 py-3">
          <ToolHoverCopyButton
            text={summary.content}
            position="resultCompact"
            className="z-20 pointer-events-auto"
            copyButtonClassName="bg-[var(--theme-bg-elevated)] shadow-sm ring-1 ring-stone-200/70 hover:bg-stone-100 dark:bg-stone-900/90 dark:ring-stone-700/70 dark:hover:bg-stone-800"
          />
          <pre className="whitespace-pre-wrap break-words font-mono text-12 leading-relaxed text-theme-text">
            {summary.content}
          </pre>
        </div>
      )}

      {summary === null && hasRawFallback && (
        <div className="group/result relative min-h-0 flex-1 text-12 text-theme-text-secondary overflow-y-auto min-w-0">
          <ToolHoverCopyButton
            text={typeof result === "string" ? result : JSON.stringify(result)}
            position="resultCompact"
            className="z-20 pointer-events-auto"
            copyButtonClassName="bg-[var(--theme-bg-elevated)] shadow-sm ring-1 ring-stone-200/70 hover:bg-stone-100 dark:bg-stone-900/90 dark:ring-stone-700/70 dark:hover:bg-stone-800"
          />
          <ToolResultContent result={result} hideCopyButton />
        </div>
      )}

      {!summary && !hasRawFallback && (
        <div className="px-1 text-12 text-theme-text-tertiary">
          {t("chat.message.toolWebFetchWaiting")}
        </div>
      )}
    </div>
  );
}

const WebFetchItem = memo(function WebFetchItem({
  id,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
  id?: string;
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
  const url = (args.url as string) || "";
  const summary = useMemo(() => parseWebFetchResult(result), [result]);
  const hasResult = result !== undefined;
  const canExpand = !!url || hasResult || isPending;

  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const titleLabel = t("chat.message.toolWebFetch");
  const pillLabel = `${titleLabel} ${url ? `"${truncate(hostFromUrl(url) || url, 24)}"` : ""}`.trim();

  const { label, isStreamingLabel } = useToolStreamingLabel(pillLabel, args, {
    isPending,
    result,
  });

  const detailContent = canExpand && (
    <WebFetchDetail
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  const openFetchPanel = () => {
    if (!canExpand) return;
    openToolLivePanel({
      id,
      title: titleLabel,
      icon: <BookOpen size={16} />,
      status,
      subtitle: url || undefined,
      fallback: detailContent || undefined,
      buildDetail: (data) => (
        <WebFetchDetail {...toolDetailPropsFromPanelData(data)} />
      ),
      footer: durationFooter,
    });
  };

  return (
    <CollapsiblePill
      status={status}
      icon={<BookOpen size={12} className="shrink-0 opacity-50" />}
      label={label}
      animatedDots={isStreamingLabel}
      variant="tool"
      formatLabel={false}
      expandable={canExpand}
      onPanelOpen={openFetchPanel}
    >
      {canExpand && (
        <ToolInlineDetails>
          {url && (
            <ToolArgsBlock size="compact">
              <BookOpen
                size={12}
                className="shrink-0 text-[var(--theme-primary)]"
              />
              <span className="min-w-0 truncate font-mono font-medium text-[color-mix(in_srgb,var(--theme-primary)_78%,var(--theme-text))]">
                {truncate(url, 60)}
              </span>
            </ToolArgsBlock>
          )}

          {summary && <FetchSummaryChips summary={summary} size="compact" />}

          {summary && (
            <div className="rounded-lg bg-theme-bg px-2.5 py-1.5 text-12 leading-relaxed text-theme-text-secondary ring-1 ring-theme-border">
              {summary.title && (
                <span className="mb-0.5 block truncate font-medium text-theme-text">
                  {summary.title}
                </span>
              )}
              <span className="line-clamp-2 font-mono">
                {truncate(summary.content, 260)}
              </span>
            </div>
          )}

          {hasResult && !summary && (
            <div className="group/result relative min-w-0 overflow-y-auto text-12 text-theme-text-secondary">
              <ToolHoverCopyButton
                text={
                  typeof result === "string"
                    ? result
                    : JSON.stringify(result, null, 2)
                }
                position="resultCompact"
                className="z-20 pointer-events-auto"
                copyButtonClassName="bg-[var(--theme-bg-elevated)] shadow-sm ring-1 ring-stone-200/70 hover:bg-stone-100 dark:bg-stone-900/90 dark:ring-stone-700/70 dark:hover:bg-stone-800"
              />
              <ToolResultContent result={result} hideCopyButton />
            </div>
          )}
        </ToolInlineDetails>
      )}
    </CollapsiblePill>
  );
});

export { WebFetchItem };
