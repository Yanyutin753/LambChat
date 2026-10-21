import { TagBadge } from "../../../common/TagBadge";
import { memo, useMemo } from "react";
import { Search, Wrench } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import {
  parseToolSearchResult,
  type ToolSearchSummary,
} from "./toolSearchResult";

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

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** 摘要行：找到 N 个工具 · 新加载 X · 已可用 Y */
function ToolSearchSummaryChips({ summary }: { summary: ToolSearchSummary }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <TagBadge icon={<Wrench />}>
        {t("chat.message.toolSearchToolCount", { count: summary.total })}
      </TagBadge>
      {summary.newlyLoaded > 0 && (
        <TagBadge>
          {t("chat.message.toolSearchNewlyLoaded", {
            count: summary.newlyLoaded,
          })}
        </TagBadge>
      )}
      {summary.alreadyAvailable > 0 && (
        <TagBadge>
          {t("chat.message.toolSearchAlreadyAvailable", {
            count: summary.alreadyAvailable,
          })}
        </TagBadge>
      )}
    </div>
  );
}

/** 面板详情：实时跟随 toolCallPanelStore 数据重建（搜索结果到达即刷新） */
function ToolSearchDetail({ args, result }: ToolDetailProps) {
  const query = (args.query as string) || "";
  const summary = useMemo(() => parseToolSearchResult(result), [result]);
  const hasRawFallback = !!result && summary === null;

  return (
    <div className="tool-panel-content flex h-full min-h-0 flex-col space-y-3 overflow-y-auto p-2 sm:p-4 [&_pre]:!max-h-none">
      {query && (
        <ToolArgsBlock size="detail" copyText={query}>
          <Search
            size={14}
            className="shrink-0 text-sky-500 dark:text-sky-400"
          />
          <span className="text-sky-600 dark:text-sky-400 font-medium">
            {query}
          </span>
        </ToolArgsBlock>
      )}

      {summary && <ToolSearchSummaryChips summary={summary} />}
      {summary?.availability && (
        <ToolResultContent result={summary.availability} hideCopyButton />
      )}

      {summary && summary.matches.length > 0 && (
        <div className="space-y-2">
          {summary.matches.map((match) => (
            <div
              key={match.name}
              className="tool-result-card rounded-xl bg-theme-bg border border-theme-border px-3.5 py-3 space-y-1.5 shadow-[0_1px_2px_rgb(0_0_0/0.04)]"
            >
              <div className="flex items-center gap-2 min-w-0">
                <Wrench
                  size={13}
                  className="shrink-0 text-sky-500 dark:text-sky-400"
                />
                <span className="text-14 font-semibold text-theme-text font-mono truncate">
                  {match.name}
                </span>
              </div>
              {match.description && (
                <p className="text-12 text-theme-text-secondary leading-relaxed line-clamp-3">
                  {truncate(match.description, 300)}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {hasRawFallback && (
        <div className="group/result relative flex-1 min-h-0 text-12 text-theme-text-secondary overflow-y-auto min-w-0">
          <ToolResultContent result={result} />
        </div>
      )}
    </div>
  );
}

const ToolSearchItem = memo(function ToolSearchItem({
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
  const query = (args.query as string) || "";
  const summary = useMemo(() => parseToolSearchResult(result), [result]);
  const hasResult = result !== undefined;
  // 参数生成中（无 result）也允许打开面板：实时等待搜索结果
  const canExpand = !!query || hasResult || isPending;

  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const titleLabel = t("chat.message.toolSearchTools");
  const pillLabel = `${titleLabel} ${query ? `"${query}"` : ""}${
    summary && summary.total > 0 ? ` (${summary.total})` : ""
  }`.trim();

  // 进行中：标签学「思考中」，平滑流出正在生成的参数尾部
  const { label, isStreamingLabel } = useToolStreamingLabel(pillLabel, args, {
    isPending,
    result,
  });

  const detailContent = canExpand && (
    <ToolSearchDetail
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<Search size={12} className="shrink-0 opacity-50" />}
        label={label}
        animatedDots={isStreamingLabel}
        variant="tool"
        formatLabel={false}
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: titleLabel,
            icon: <Search size={16} />,
            status,
            subtitle: query || undefined,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <ToolSearchDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            {query && (
              <ToolArgsBlock size="compact" copyText={query}>
                <Search
                  size={12}
                  className="shrink-0 text-sky-500 dark:text-sky-400"
                />
                <span className="text-sky-600 dark:text-sky-400 font-medium min-w-0 truncate">
                  {truncate(query, 50)}
                </span>
              </ToolArgsBlock>
            )}

            {summary && <ToolSearchSummaryChips summary={summary} />}

            {summary && summary.matches.length > 0 && (
              <div className="space-y-1">
                {summary.matches.slice(0, 4).map((match) => (
                  <div
                    key={match.name}
                    className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-theme-bg border border-theme-border"
                  >
                    <Wrench
                      size={11}
                      className="shrink-0 text-sky-500 dark:text-sky-400 opacity-70"
                    />
                    <span className="text-12 text-theme-text font-medium font-mono min-w-0 truncate flex-1">
                      {match.name}
                    </span>
                    {match.description && (
                      <span className="shrink-0 text-10 text-theme-text-tertiary truncate max-w-[120px]">
                        {truncate(
                          match.description.split(/[.。]/)[0] || "",
                          36,
                        )}
                      </span>
                    )}
                  </div>
                ))}
                {summary.matches.length > 4 && (
                  <div className="text-12 text-theme-text-tertiary px-2.5">
                    {t("chat.message.toolMoreTools", {
                      count: summary.matches.length - 4,
                    })}
                  </div>
                )}
              </div>
            )}

            {hasResult && !summary && (
              <div className="group/result relative text-12 text-theme-text-secondary overflow-y-auto min-w-0">
                <ToolResultContent result={result} />
              </div>
            )}
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
    </>
  );
});

export { ToolSearchItem };
