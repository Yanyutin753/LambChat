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
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolResultContent } from "./McpBlockPreview";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** 摘要行：找到 N 个工具 · 新加载 X · 已可用 Y */
function ToolSearchSummaryChips({
  summary,
  size,
}: {
  summary: ToolSearchSummary;
  size: "compact" | "detail";
}) {
  const { t } = useTranslation();
  const compact = size === "compact";
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span
        className={`inline-flex items-center gap-1 rounded-md font-medium text-sky-700 dark:text-sky-300 bg-sky-50 dark:bg-sky-950/40 ring-1 ring-sky-200/60 dark:ring-sky-800/40 ${
          compact ? "px-1.5 py-0.5 text-10" : "px-2 py-0.5 text-11"
        }`}
      >
        <Wrench size={compact ? 9 : 10} className="shrink-0 opacity-70" />
        {t("chat.message.toolSearchToolCount", { count: summary.total })}
      </span>
      {summary.newlyLoaded > 0 && (
        <span
          className={`inline-flex items-center rounded-md font-medium text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/40 ring-1 ring-emerald-200/60 dark:ring-emerald-800/40 ${
            compact ? "px-1.5 py-0.5 text-10" : "px-2 py-0.5 text-11"
          }`}
        >
          {t("chat.message.toolSearchNewlyLoaded", {
            count: summary.newlyLoaded,
          })}
        </span>
      )}
      {summary.alreadyAvailable > 0 && (
        <span
          className={`inline-flex items-center rounded-md font-medium text-theme-text-secondary bg-theme-bg-card ring-1 ring-theme-border ${
            compact ? "px-1.5 py-0.5 text-10" : "px-2 py-0.5 text-11"
          }`}
        >
          {t("chat.message.toolSearchAlreadyAvailable", {
            count: summary.alreadyAvailable,
          })}
        </span>
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
    <div className="flex h-full min-h-0 flex-col space-y-3 overflow-y-auto p-2 sm:p-4 [&_pre]:!max-h-none">
      {query && (
        <ToolArgsBlock size="detail">
          <Search
            size={14}
            className="shrink-0 text-sky-500 dark:text-sky-400"
          />
          <span className="text-sky-600 dark:text-sky-400 font-mono font-semibold">
            {query}
          </span>
        </ToolArgsBlock>
      )}

      {summary && <ToolSearchSummaryChips summary={summary} size="detail" />}

      {summary && summary.matches.length > 0 && (
        <div className="space-y-2">
          {summary.matches.map((match) => (
            <div
              key={match.name}
              className="rounded-xl bg-theme-bg border border-theme-border px-3.5 py-3 space-y-1.5 shadow-[0_1px_2px_rgb(0_0_0/0.04)]"
            >
              <div className="flex items-center gap-2 min-w-0">
                <Wrench
                  size={13}
                  className="shrink-0 text-sky-500 dark:text-sky-400"
                />
                <span className="text-sm font-semibold text-theme-text font-mono truncate">
                  {match.name}
                </span>
              </div>
              {match.description && (
                <p className="text-xs text-theme-text-secondary leading-relaxed line-clamp-3">
                  {truncate(match.description, 300)}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {hasRawFallback && (
        <div className="group/result relative flex-1 min-h-0 text-xs text-theme-text-secondary overflow-y-auto min-w-0">
          <ToolHoverCopyButton
            text={typeof result === "string" ? result : JSON.stringify(result)}
            position="resultCompact"
            className="z-20 pointer-events-auto"
            copyButtonClassName="bg-[var(--theme-bg-elevated)] shadow-sm ring-1 ring-stone-200/70 hover:bg-stone-100 dark:bg-stone-900/90 dark:ring-stone-700/70 dark:hover:bg-stone-800"
          />
          <ToolResultContent result={result} hideCopyButton />
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
  const pillLabel = `${titleLabel} ${query ? `"${truncate(query, 24)}"` : ""}${
    summary && summary.total > 0 ? ` (${summary.total})` : ""
  }`.trim();

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
        label={pillLabel}
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
              <ToolArgsBlock size="compact">
                <Search
                  size={12}
                  className="shrink-0 text-sky-500 dark:text-sky-400"
                />
                <span className="text-sky-600 dark:text-sky-400 font-mono font-medium min-w-0 truncate">
                  {truncate(query, 50)}
                </span>
              </ToolArgsBlock>
            )}

            {summary && (
              <ToolSearchSummaryChips summary={summary} size="compact" />
            )}

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
                    <span className="text-xs text-theme-text font-medium font-mono min-w-0 truncate flex-1">
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
                  <div className="text-xs text-theme-text-tertiary px-2.5">
                    {t("chat.message.toolMoreTools", {
                      count: summary.matches.length - 4,
                    })}
                  </div>
                )}
              </div>
            )}

            {hasResult && !summary && (
              <div className="group/result relative text-xs text-theme-text-secondary overflow-y-auto min-w-0">
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
    </>
  );
});

export { ToolSearchItem };
