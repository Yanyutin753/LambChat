import { TagBadge } from "../../../common/TagBadge";
import { InteractiveIcon } from "../../../common/InteractiveIcon";
import { memo, useMemo } from "react";
import { BookOpen, FileText, Scissors } from "lucide-react";
import { useTranslation } from "react-i18next";
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

function FetchSummaryChips({ summary }: { summary: WebFetchSummary }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <TagBadge icon={<FileText />}>
        {t("chat.message.toolWebFetchChars", {
          count: summary.contentChars ?? summary.content.length,
        })}
      </TagBadge>
      {summary.provider && <TagBadge>{summary.provider}</TagBadge>}
      {summary.truncated && (
        <TagBadge
          icon={<Scissors />}
          className="text-amber-600 dark:text-amber-400"
        >
          {t("chat.message.toolWebFetchTruncated")}
        </TagBadge>
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
    <div className="tool-panel-content flex h-full min-h-0 flex-col space-y-3.5 overflow-y-auto p-2 sm:p-4 [&_pre]:!max-h-none">
      {(url || summary?.provider) && (
        <a
          href={summary?.finalUrl || url}
          target="_blank"
          rel="noreferrer"
          className="tool-query-header"
        >
          <span className="tool-query-icon">
            <InteractiveIcon>
              <BookOpen
                size={14}
                className="shrink-0 text-[var(--theme-primary)]"
              />
            </InteractiveIcon>
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
        </a>
      )}

      {summary && <FetchSummaryChips summary={summary} />}

      {summary && (
        <div className="tool-result-card group/content relative min-h-0 flex-1 border border-theme-border">
          <ToolHoverCopyButton
            text={summary.content}
            position="resultCompact"
            className="z-20 pointer-events-auto"
            copyButtonClassName="tool-result-copy"
          />
          <pre className="whitespace-pre-wrap break-words font-mono text-12 leading-relaxed text-theme-text">
            {summary.content}
          </pre>
        </div>
      )}

      {summary === null && hasRawFallback && (
        <div className="group/result relative min-h-0 flex-1 text-12 text-theme-text-secondary overflow-y-auto min-w-0">
          <ToolResultContent result={result} />
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
  const pillLabel = `${titleLabel} ${
    url ? `"${hostFromUrl(url) || url}"` : ""
  }`.trim();

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
            <ToolArgsBlock size="compact" copyText={url}>
              <BookOpen
                size={12}
                className="shrink-0 text-[var(--theme-primary)]"
              />
              <span className="min-w-0 truncate font-mono font-medium text-[color-mix(in_srgb,var(--theme-primary)_78%,var(--theme-text))]">
                {truncate(url, 60)}
              </span>
            </ToolArgsBlock>
          )}

          {summary && <FetchSummaryChips summary={summary} />}

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
              <ToolResultContent result={result} />
            </div>
          )}
        </ToolInlineDetails>
      )}
    </CollapsiblePill>
  );
});

export { WebFetchItem };
