import { memo, useCallback, useMemo, useState } from "react";
import { Globe, ImageIcon, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill, ImageViewer } from "../../../common";
import { ImageWithSkeleton } from "../ImageWithSkeleton";
import {
  hostFromUrl,
  parseWebSearchResult,
  type WebSearchResultItem,
  type WebSearchSummary,
} from "./webSearchResult";

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
import { useSessionImageGallery } from "../sessionImageGallery";

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** favicon：优先后端直出的 favicon_url，否则走 Google S2，失败回退图标。 */
function ResultFavicon({
  item,
  size = 14,
}: {
  item: WebSearchResultItem;
  size?: number;
}) {
  const [failed, setFailed] = useState(false);
  const host = hostFromUrl(item.url);
  const src =
    item.faviconUrl ||
    (host ? `https://www.google.com/s2/favicons?domain=${host}&sz=64` : null);

  if (failed || !src) {
    return (
      <Globe size={size} className="shrink-0 text-theme-text-tertiary opacity-70" />
    );
  }
  return (
    <img
      src={src}
      width={size}
      height={size}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="shrink-0 rounded-[3px]"
    />
  );
}

/** 摘要 chips：供应商 + 结果数 + 图片数 */
function WebSearchSummaryChips({
  summary,
  size,
}: {
  summary: WebSearchSummary;
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
        <Globe size={compact ? 9 : 10} className="shrink-0 opacity-70" />
        {t("chat.message.toolWebSearchResults", { count: summary.results.length })}
      </span>
      {summary.provider && (
        <span
          className={`inline-flex items-center rounded-md font-medium text-theme-text-secondary bg-theme-bg-card ring-1 ring-theme-border ${
            compact ? "px-1.5 py-0.5 text-10" : "px-2 py-0.5 text-11"
          }`}
        >
          {summary.provider}
        </span>
      )}
      {summary.images.length > 0 && (
        <span
          className={`inline-flex items-center gap-1 rounded-md font-medium text-theme-text-secondary bg-theme-bg-card ring-1 ring-theme-border ${
            compact ? "px-1.5 py-0.5 text-10" : "px-2 py-0.5 text-11"
          }`}
        >
          <ImageIcon size={compact ? 9 : 10} className="shrink-0 opacity-70" />
          {t("chat.message.toolWebSearchImages", { count: summary.images.length })}
        </span>
      )}
    </div>
  );
}

/** 面板详情：实时跟随 toolCallPanelStore 数据重建（结果到达即刷新） */
function WebSearchDetail({ args, result }: ToolDetailProps) {
  const { t } = useTranslation();
  const sessionImageGallery = useSessionImageGallery();
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);
  const query = (args.query as string) || "";
  const summary = useMemo(() => parseWebSearchResult(result), [result]);
  const hasRawFallback = !!result && summary === null;

  const openImagePreview = useCallback(
    (src: string) => {
      sessionImageGallery?.openImage(src);
      if (!sessionImageGallery) {
        setImageViewerSrc(src);
      }
    },
    [sessionImageGallery],
  );

  return (
    <div className="flex h-full min-h-0 flex-col space-y-3 overflow-y-auto p-2 sm:p-4 [&_pre]:!max-h-none">
      {query && (
        <ToolArgsBlock size="detail">
          <Globe size={14} className="shrink-0 text-sky-500 dark:text-sky-400" />
          <span className="text-sky-600 dark:text-sky-400 font-mono font-semibold">
            {query}
          </span>
        </ToolArgsBlock>
      )}

      {summary && <WebSearchSummaryChips summary={summary} size="detail" />}

      {summary?.answer && (
        <div className="rounded-xl border border-sky-200/60 dark:border-sky-800/40 bg-sky-50/70 dark:bg-sky-950/30 px-3.5 py-3">
          <div className="flex items-center gap-1.5 text-11 font-semibold text-sky-700 dark:text-sky-300">
            <Sparkles size={12} className="shrink-0 opacity-70" />
            {t("chat.message.toolWebSearchAnswer")}
          </div>
          <p className="mt-1.5 text-13 text-theme-text leading-relaxed">
            {summary.answer}
          </p>
        </div>
      )}

      {summary && summary.results.length === 0 && (
        <div className="text-12 text-theme-text-tertiary px-1">
          {t("chat.message.toolWebSearchNoResults")}
        </div>
      )}

      {summary && summary.results.length > 0 && (
        <div className="space-y-2">
          {summary.results.map((item) => {
            const host = hostFromUrl(item.url);
            return (
              <a
                key={item.url}
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="block rounded-xl bg-theme-bg border border-theme-border px-3.5 py-3 space-y-1.5 shadow-[0_1px_2px_rgb(0_0_0/0.04)] hover:border-sky-300 dark:hover:border-sky-700 transition-colors"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <ResultFavicon item={item} />
                  <span className="text-14 font-semibold text-theme-text truncate flex-1">
                    {item.title || host || item.url}
                  </span>
                  {item.score !== null && (
                    <span className="shrink-0 text-10 text-theme-text-tertiary font-mono">
                      {Math.round(item.score * 100)}%
                    </span>
                  )}
                </div>
                {(host || item.publishedDate) && (
                  <div className="text-10 text-theme-text-tertiary truncate font-mono">
                    {host}
                    {host && item.publishedDate ? " · " : ""}
                    {item.publishedDate ?? ""}
                  </div>
                )}
                {item.snippet && (
                  <p className="text-12 text-theme-text-secondary leading-relaxed line-clamp-2">
                    {truncate(item.snippet, 320)}
                  </p>
                )}
              </a>
            );
          })}
        </div>
      )}

      {summary && summary.images.length > 0 && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-11 font-medium text-theme-text-secondary px-0.5">
            <ImageIcon size={12} className="shrink-0 opacity-70" />
            {t("chat.message.toolWebSearchImages", { count: summary.images.length })}
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {summary.images.slice(0, 9).map((image, index) => (
              <button
                key={`${image.url}-${index}`}
                type="button"
                onClick={() => openImagePreview(image.url)}
                className="group/img relative rounded-xl overflow-hidden border border-theme-border hover:border-sky-300 dark:hover:border-sky-700 transition-colors cursor-zoom-in"
              >
                <ImageWithSkeleton
                  src={image.url}
                  alt={image.description || ""}
                  skipUrlResolve
                  inline
                  className="w-full aspect-[4/3] object-cover"
                />
                {image.description && (
                  <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/55 to-transparent px-2 pb-1.5 pt-4 opacity-0 group-hover/img:opacity-100 transition-opacity">
                    <span className="block text-white/90 text-10 leading-snug line-clamp-2 text-left drop-shadow-sm">
                      {truncate(image.description, 90)}
                    </span>
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {hasRawFallback && (
        <div className="group/result relative flex-1 min-h-0 text-12 text-theme-text-secondary overflow-y-auto min-w-0">
          <ToolHoverCopyButton
            text={typeof result === "string" ? result : JSON.stringify(result)}
            position="resultCompact"
            className="z-20 pointer-events-auto"
            copyButtonClassName="bg-[var(--theme-bg-elevated)] shadow-sm ring-1 ring-stone-200/70 hover:bg-stone-100 dark:bg-stone-900/90 dark:ring-stone-700/70 dark:hover:bg-stone-800"
          />
          <ToolResultContent result={result} hideCopyButton />
        </div>
      )}

      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          isOpen={!!imageViewerSrc}
          onClose={() => setImageViewerSrc(null)}
        />
      )}
    </div>
  );
}

const WebSearchItem = memo(function WebSearchItem({
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
  const summary = useMemo(() => parseWebSearchResult(result), [result]);
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

  const titleLabel = t("chat.message.toolWebSearch");
  const pillLabel = `${titleLabel} ${query ? `"${truncate(query, 24)}"` : ""}${
    summary && summary.results.length > 0 ? ` (${summary.results.length})` : ""
  }`.trim();

  // 进行中：标签平滑流出正在生成的参数尾部
  const { label, isStreamingLabel } = useToolStreamingLabel(pillLabel, args, {
    isPending,
    result,
  });

  const detailContent = canExpand && (
    <WebSearchDetail
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
        icon={<Globe size={12} className="shrink-0 opacity-50" />}
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
            icon: <Globe size={16} />,
            status,
            subtitle: query || undefined,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <WebSearchDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {canExpand && (
          <ToolInlineDetails>
            {query && (
              <ToolArgsBlock size="compact">
                <Globe
                  size={12}
                  className="shrink-0 text-sky-500 dark:text-sky-400"
                />
                <span className="text-sky-600 dark:text-sky-400 font-mono font-medium min-w-0 truncate">
                  {truncate(query, 50)}
                </span>
              </ToolArgsBlock>
            )}

            {summary && <WebSearchSummaryChips summary={summary} size="compact" />}

            {summary && summary.results.length > 0 && (
              <div className="space-y-1">
                {summary.results.slice(0, 3).map((item) => (
                  <div
                    key={item.url}
                    className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-theme-bg border border-theme-border"
                  >
                    <ResultFavicon item={item} size={11} />
                    <span className="text-12 text-theme-text font-medium min-w-0 truncate flex-1">
                      {item.title || hostFromUrl(item.url) || item.url}
                    </span>
                    <span className="shrink-0 text-10 text-theme-text-tertiary truncate max-w-[110px] font-mono">
                      {hostFromUrl(item.url)}
                    </span>
                  </div>
                ))}
                {summary.results.length > 3 && (
                  <div className="text-12 text-theme-text-tertiary px-2.5">
                    {t("chat.message.toolWebSearchMore", {
                      count: summary.results.length - 3,
                    })}
                  </div>
                )}
              </div>
            )}

            {summary && summary.results.length === 0 && (
              <div className="text-12 text-theme-text-tertiary px-2.5">
                {t("chat.message.toolWebSearchNoResults")}
              </div>
            )}

            {hasResult && !summary && (
              <div className="group/result relative text-12 text-theme-text-secondary overflow-y-auto min-w-0">
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

export { WebSearchItem };
