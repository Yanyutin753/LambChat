import { memo, useCallback, useMemo, useState } from "react";
import { Globe, ImageIcon, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { CollapsiblePill, ImageViewer } from "../../../common";
import { ImageWithSkeleton } from "../ImageWithSkeleton";
import {
  hostFromUrl,
  parseWebSearchResult,
  siteLabelFromUrl,
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

/** 供应商识别色点：不同搜索源一眼可辨 */
const PROVIDER_DOTS: Record<string, string> = {
  tavily: "bg-sky-400",
  brave: "bg-orange-400",
  searxng: "bg-violet-400",
};

function ProviderBadge({ provider, className }: { provider: string; className?: string }) {
  if (!provider) return null;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-md bg-theme-bg-card px-2 py-0.5 text-10 font-medium text-theme-text-secondary ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_14%,var(--theme-border))]",
        className,
      )}
    >
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

/** favicon：后端直出优先，否则 Google S2，失败回退图标；外面套主题色容器更精致 */
function ResultFavicon({
  item,
  size = 14,
  boxed = false,
}: {
  item: WebSearchResultItem;
  size?: number;
  boxed?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const host = hostFromUrl(item.url);
  const src =
    item.faviconUrl ||
    (host ? `https://www.google.com/s2/favicons?domain=${host}&sz=64` : null);

  const icon = failed || !src ? (
    <Globe size={size} className="shrink-0 text-theme-text-tertiary opacity-70" />
  ) : (
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

  if (!boxed) return icon;
  return (
    <span className="flex size-7 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-theme-bg-card ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_10%,var(--theme-border))]">
      {icon}
    </span>
  );
}

/** 相关性分数：主题色深浅分档的迷你徽章 */
function ScoreBadge({ score }: { score: number }) {
  const pct = Math.min(Math.round(score * 100), 100);
  const strong = pct >= 80;
  return (
    <span
      className={clsx(
        "inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-10 font-semibold tabular-nums",
        strong
          ? "bg-[color-mix(in_srgb,var(--theme-primary)_10%,transparent)] text-[var(--theme-primary)]"
          : "text-theme-text-tertiary bg-[color-mix(in_srgb,var(--theme-text-tertiary)_10%,transparent)]",
      )}
    >
      {pct}
    </span>
  );
}

/** 收起态来源卡：favicon + 短站点名（ChatGPT 引用卡风格），点击直达原文 */
function SourceCard({ item }: { item: WebSearchResultItem }) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1.5 rounded-lg border border-theme-border/60 bg-theme-bg-card px-2 py-1 text-12 text-theme-text-secondary transition-all duration-200 hover:border-theme-border hover:text-theme-text hover:shadow-[0_4px_12px_-10px_rgb(0_0_0/0.35)]"
    >
      <ResultFavicon item={item} size={14} />
      <span className="max-w-[110px] truncate">
        {siteLabelFromUrl(item.url) || item.url}
      </span>
    </a>
  );
}

/** 收起态图片缩略（ChatGPT 图片条风格，加载失败静默隐藏） */
function SourceThumb({
  src,
  alt,
  interactive = false,
}: {
  src: string;
  alt: string;
  interactive?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  return (
    <span
      className={clsx(
        "block h-10 w-14 shrink-0 overflow-hidden rounded-lg border border-theme-border/60 bg-theme-bg-card",
        interactive &&
          "transition-all duration-200 group-hover/thumb:border-[color-mix(in_srgb,var(--theme-primary)_36%,var(--theme-border))] group-hover/thumb:shadow-[0_6px_14px_-10px_color-mix(in_srgb,var(--theme-primary)_45%,transparent)]",
      )}
    >
      <img
        src={src}
        alt={alt}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className="h-full w-full object-cover transition-transform duration-200 group-hover/thumb:scale-105"
      />
    </span>
  );
}

/** 摘要 chips：结果数（主题色）+ 供应商 + 图片数 */
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
        className={clsx(
          "inline-flex items-center gap-1 rounded-md font-medium",
          "bg-[color-mix(in_srgb,var(--theme-primary)_9%,transparent)] text-[var(--theme-primary)] ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_16%,transparent)]",
          compact ? "px-1.5 py-0.5 text-10" : "px-2 py-0.5 text-11",
        )}
      >
        <Globe size={compact ? 9 : 10} className="shrink-0 opacity-70" />
        {t("chat.message.toolWebSearchResults", { count: summary.results.length })}
      </span>
      {summary.provider && <ProviderBadge provider={summary.provider} />}
      {summary.images.length > 0 && (
        <span
          className={clsx(
            "inline-flex items-center gap-1 rounded-md font-medium text-theme-text-secondary bg-theme-bg-card ring-1 ring-theme-border",
            compact ? "px-1.5 py-0.5 text-10" : "px-2 py-0.5 text-11",
          )}
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
    <div className="flex h-full min-h-0 flex-col space-y-3.5 overflow-y-auto p-2 sm:p-4 [&_pre]:!max-h-none">
      {/* 查询 hero：主题色染色 + 光晕，面板的视觉锚点 */}
      {(query || summary?.provider) && (
        <div className="flex items-center gap-2.5 rounded-xl border border-[color-mix(in_srgb,var(--theme-primary)_16%,var(--theme-border))] bg-[color-mix(in_srgb,var(--theme-primary)_7%,var(--theme-bg-card))] px-3 py-2.5 shadow-[0_10px_24px_-22px_color-mix(in_srgb,var(--theme-primary)_45%,transparent)]">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--theme-primary)_12%,transparent)] ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_18%,transparent)]">
            <Globe
              size={14}
              className="shrink-0 text-[var(--theme-primary)]"
            />
          </span>
          <span className="text-14 font-semibold text-theme-text min-w-0 truncate flex-1">
            {query || t("chat.message.toolWebSearch")}
          </span>
          {summary?.provider && <ProviderBadge provider={summary.provider} />}
        </div>
      )}

      {summary && <WebSearchSummaryChips summary={summary} size="detail" />}

      {summary?.answer && (
        <div className="rounded-xl border border-[color-mix(in_srgb,var(--theme-primary)_12%,var(--theme-border))] bg-[color-mix(in_srgb,var(--theme-primary)_4%,var(--theme-bg-card))] px-3.5 py-3">
          <div className="flex items-center gap-1.5 text-11 font-semibold text-[var(--theme-primary)]">
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
          {summary.results.map((item, index) => {
            const host = hostFromUrl(item.url);
            return (
              <a
                key={item.url}
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="group/card flex gap-2.5 rounded-xl bg-theme-bg border border-theme-border px-3 py-2.5 transition-all duration-200 hover:border-[color-mix(in_srgb,var(--theme-primary)_32%,var(--theme-border))] hover:shadow-[0_12px_28px_-24px_color-mix(in_srgb,var(--theme-primary)_42%,transparent)]"
              >
                <span className="flex w-5 shrink-0 items-start justify-center pt-1.5 text-10 font-mono font-semibold tabular-nums text-theme-text-tertiary">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2 min-w-0">
                    <ResultFavicon item={item} boxed />
                    <span className="text-13 font-semibold text-theme-text truncate flex-1 group-hover/card:text-[var(--theme-primary)] transition-colors">
                      {item.title || host || item.url}
                    </span>
                    {item.score !== null && <ScoreBadge score={item.score} />}
                  </div>
                  {(host || item.publishedDate) && (
                    <div className="text-10 text-sky-700/80 dark:text-sky-300/70 truncate font-mono">
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
                </div>
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
                className="group/img relative rounded-xl overflow-hidden border border-theme-border hover:border-[color-mix(in_srgb,var(--theme-primary)_36%,var(--theme-border))] hover:shadow-[0_12px_28px_-22px_color-mix(in_srgb,var(--theme-primary)_45%,transparent)] transition-all duration-200 cursor-zoom-in"
              >
                <ImageWithSkeleton
                  src={image.url}
                  alt={image.description || ""}
                  skipUrlResolve
                  inline
                  className="w-full aspect-[4/3] object-cover"
                />
                <div className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-black/50 text-white text-9 font-medium tabular-nums">
                  #{index + 1}
                </div>
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
  const sessionImageGallery = useSessionImageGallery();
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);
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
  const pillLabel = `${titleLabel} ${query ? `"${truncate(query, 24)}"` : ""}`.trim();
  // 结果数走 suffix 徽章，pill 主标签保持干净
  const countSuffix =
    summary && summary.results.length > 0 ? (
      <span className="inline-flex shrink-0 items-center rounded-full bg-black/[0.06] dark:bg-white/10 px-1.5 text-9 font-semibold tabular-nums opacity-80">
        {summary.results.length}
      </span>
    ) : undefined;

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

  const openSearchPanel = () => {
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
  };

  // 收起态预览条：把面板里的信息露出一点，制造点击欲望
  const showSourceStrip =
    !isPending && summary !== null && summary.results.length > 0;

  // 收起态缩略图点击 → 图片查看器（会话相册优先，无 Context 时本地兜底）
  const openCollapsedImagePreview = useCallback(
    (src: string) => {
      sessionImageGallery?.openImage(src);
      if (!sessionImageGallery) {
        setImageViewerSrc(src);
      }
    },
    [sessionImageGallery],
  );

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<Globe size={12} className="shrink-0 opacity-50" />}
        label={label}
        suffix={countSuffix}
        animatedDots={isStreamingLabel}
        variant="tool"
        formatLabel={false}
        expandable={canExpand}
        onPanelOpen={openSearchPanel}
      >
        {canExpand && (
          <ToolInlineDetails>
            {query && (
              <ToolArgsBlock size="compact">
                <Globe
                  size={12}
                  className="shrink-0 text-[var(--theme-primary)]"
                />
                <span className="text-[color-mix(in_srgb,var(--theme-primary)_78%,var(--theme-text))] font-mono font-medium min-w-0 truncate">
                  {truncate(query, 50)}
                </span>
              </ToolArgsBlock>
            )}

            {summary && <WebSearchSummaryChips summary={summary} size="compact" />}

            {summary && summary.results.length > 0 && (
              <div className="space-y-1">
                {summary.results.slice(0, 3).map((item, index) => (
                  <div
                    key={item.url}
                    className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-theme-bg border border-theme-border hover:border-[color-mix(in_srgb,var(--theme-primary)_28%,var(--theme-border))] transition-colors"
                  >
                    <span className="w-3 shrink-0 text-10 font-mono font-semibold tabular-nums text-theme-text-tertiary text-center">
                      {index + 1}
                    </span>
                    <ResultFavicon item={item} size={11} />
                    <span className="text-12 text-theme-text font-medium min-w-0 truncate flex-1">
                      {item.title || hostFromUrl(item.url) || item.url}
                    </span>
                    <span className="shrink-0 text-10 text-sky-700/80 dark:text-sky-300/70 truncate max-w-[110px] font-mono">
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

      {/* 收起态来源预览（ChatGPT 风格）：来源卡直达原文，缩略图/+N 打开实时面板 */}
      {showSourceStrip && (
        <div className="mt-1.5 space-y-1.5 pl-1">
          <div className="flex flex-wrap items-center gap-1.5">
            {summary.results.slice(0, 5).map((item) => (
              <SourceCard key={item.url} item={item} />
            ))}
            {summary.results.length > 5 && (
              <button
                type="button"
                onClick={openSearchPanel}
                className="inline-flex items-center rounded-lg border border-theme-border/60 bg-theme-bg-card px-2 py-1 text-12 font-medium tabular-nums text-theme-text-tertiary transition-all duration-200 hover:border-theme-border hover:text-theme-text"
              >
                +{summary.results.length - 5}
              </button>
            )}
          </div>
          {summary.images.length > 0 && (
            <div className="flex items-center gap-1.5">
              {summary.images.slice(0, 3).map((image, index) => (
                <button
                  key={`${image.url}-${index}`}
                  type="button"
                  onClick={() => openCollapsedImagePreview(image.url)}
                  title={image.description || undefined}
                  className="group/thumb cursor-zoom-in transition-transform duration-200 hover:-translate-y-0.5"
                >
                  <SourceThumb
                    src={image.url}
                    alt={image.description || ""}
                    interactive
                  />
                </button>
              ))}
              {summary.images.length > 3 && (
                <button
                  type="button"
                  onClick={openSearchPanel}
                  className="inline-flex items-center gap-1 rounded-lg px-1.5 py-1 text-11 font-medium tabular-nums text-theme-text-tertiary transition-colors hover:text-[var(--theme-primary)]"
                >
                  <ImageIcon size={11} className="opacity-70" />
                  +{summary.images.length - 3}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* 收起态本地图片查看器兜底（无会话相册 Context 时） */}
      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          isOpen={!!imageViewerSrc}
          onClose={() => setImageViewerSrc(null)}
        />
      )}
    </>
  );
});

export { WebSearchItem };
