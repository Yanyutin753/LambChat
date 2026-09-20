// video_analyze 内置工具专属 Item（对齐 ImageAnalyzeItem：CollapsiblePill +
// 专属图标 + inline 紧凑预览 + 实时面板，配色沿用工具 Item 的 teal/amber accent）
import { memo, useMemo } from "react";
import { Eye, Film, MessageSquareText, Video } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { MarkdownContent } from "../MarkdownContent";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { useToolStreamingLabel } from "./useToolStreamingLabel";
import { extractText } from "./toolUtils";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { fileNameFromUrl } from "./toolImageResults";
import { mediaProxyFallbackSrc } from "../../../documents/documentFetchCache";
import { getFullUrl } from "../../../../services/api/config";

function truncate(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1)}...`;
}

function getVideoUrls(args: Record<string, unknown>): string[] {
  const rawUrls = args.video_urls;
  if (Array.isArray(rawUrls)) {
    return rawUrls.filter((url): url is string => typeof url === "string");
  }
  return typeof rawUrls === "string" ? [rawUrls] : [];
}

/** 解析为绝对 URL + 文件名，供内联播放器使用 */
function resolveVideos(urls: string[]) {
  return urls.map((url) => ({
    url: getFullUrl(url) || url,
    name: fileNameFromUrl(url),
  }));
}

function getAnalysisText(result: string | Record<string, unknown> | undefined) {
  const text = extractText(result);
  if (!text) return "";
  try {
    const parsed = JSON.parse(text) as { analysis?: unknown; error?: unknown };
    if (typeof parsed.analysis === "string") return parsed.analysis;
    if (typeof parsed.error === "string") return parsed.error;
  } catch {
    // Plain-text tool output.
  }
  return text;
}

/** 内联视频播放卡片：直接可播，直连不可达时回退应用代理流式加载 */
function VideoPreview({
  video,
  compact,
}: {
  video: { url: string; name: string };
  compact?: boolean;
}) {
  return (
    <figure className="overflow-hidden rounded-lg border border-theme-border">
      <video
        src={video.url}
        controls
        preload="metadata"
        playsInline
        className={`w-full bg-black ${compact ? "max-h-36" : "max-h-[60dvh]"}`}
        onError={(e) => {
          const fallback = mediaProxyFallbackSrc(e.currentTarget);
          if (fallback) e.currentTarget.src = fallback;
        }}
      />
      <figcaption className="flex items-center gap-2 px-3 py-1.5 bg-theme-bg-subtle text-12 text-theme-text-secondary">
        <Film size={12} className="shrink-0 opacity-50" />
        <span className="min-w-0 flex-1 truncate">{video.name}</span>
      </figcaption>
    </figure>
  );
}

/** 面板详情：独立于 pill 渲染，实时跟随 toolCallPanelStore 数据重建 */
function VideoAnalyzeDetail({ args, result }: ToolDetailProps) {
  const videos = useMemo(() => resolveVideos(getVideoUrls(args)), [args]);
  const prompt = (args.prompt as string) || "";
  const analysis = useMemo(() => getAnalysisText(result), [result]);

  return (
    <div className="p-4 sm:p-5 space-y-4 tool-panel-content">
      {prompt && (
        <ToolArgsBlock size="detail" wrap>
          <MessageSquareText
            size={14}
            className="shrink-0 text-amber-500 dark:text-amber-400"
          />
          <span className="break-words">{prompt}</span>
        </ToolArgsBlock>
      )}
      {videos.length > 0 && (
        <div className="space-y-2">
          {videos.map((video, index) => (
            <VideoPreview key={`${video.url}-${index}`} video={video} />
          ))}
        </div>
      )}
      {analysis && (
        <div className="relative group rounded-lg tool-code-block">
          <div
            className="prose prose-stone dark:prose-invert max-w-none text-14 leading-relaxed prose-p:my-0.5 prose-headings:my-1 p-3 sm:p-4"
            style={{ color: "var(--theme-text)" }}
          >
            <MarkdownContent content={analysis} />
          </div>
          <ToolHoverCopyButton
            text={analysis}
            size={14}
            position="panel"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
          />
        </div>
      )}
    </div>
  );
}

const VideoAnalyzeItem = memo(function VideoAnalyzeItem({
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
  const videoUrls = useMemo(() => getVideoUrls(args), [args]);
  const videos = useMemo(() => resolveVideos(videoUrls), [videoUrls]);
  const prompt = (args.prompt as string) || "";
  const analysis = useMemo(() => getAnalysisText(result), [result]);
  // 参数生成中（无结果）也允许打开面板：实时等待分析结果
  const canExpand =
    videos.length > 0 || !!prompt || !!analysis || !!isPending;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const analysisBlock = analysis ? (
    <div className="relative group rounded-lg tool-code-block">
      <div
        className="prose prose-stone dark:prose-invert max-w-none text-14 leading-relaxed prose-p:my-0.5 prose-headings:my-1 p-3 sm:p-4"
        style={{ color: "var(--theme-text)" }}
      >
        <MarkdownContent content={analysis} />
      </div>
      <ToolHoverCopyButton
        text={analysis}
        size={14}
        position="panel"
        copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
      />
    </div>
  ) : null;

  const detailContent = canExpand && (
    <VideoAnalyzeDetail
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  const videoSummary =
    videos.length > 1
      ? t("chat.message.toolVideoAnalyzeCount", { count: videos.length })
      : videos[0]?.name || "";

  // 进行中：标签学「思考中」，平滑流出正在生成的参数尾部
  const { label, isStreamingLabel } = useToolStreamingLabel(
    `${t("chat.message.toolVideoAnalyze")} ${
      prompt ? truncate(prompt, 56) : truncate(videoSummary, 56)
    }`,
    args,
    { isPending, result },
  );

  return (
    <CollapsiblePill
      status={status}
      icon={<Video size={12} className="shrink-0 opacity-50" />}
      label={label}
      animatedDots={isStreamingLabel}
      variant="tool"
      formatLabel={false}
      expandable={canExpand}
      onPanelOpen={() => {
        if (!canExpand) return;
        openToolLivePanel({
          id,
          title: t("chat.message.toolVideoAnalyze"),
          icon: <Eye size={16} />,
          status,
          subtitle: videoSummary || prompt || undefined,
          fallback: detailContent || undefined,
          buildDetail: (data) => (
            <VideoAnalyzeDetail {...toolDetailPropsFromPanelData(data)} />
          ),
          footer: durationFooter,
        });
      }}
    >
      {canExpand && (
        <ToolInlineDetails>
          {prompt && (
            <ToolArgsBlock size="compact" wrap>
              <MessageSquareText
                size={12}
                className="shrink-0 text-amber-500 dark:text-amber-400"
              />
              <span className="break-words">{truncate(prompt, 160)}</span>
            </ToolArgsBlock>
          )}
          {videos.slice(0, 2).map((video, index) => (
            <VideoPreview key={`${video.url}-${index}`} video={video} compact />
          ))}
          {videos.length > 2 && (
            <div className="text-11 text-theme-text-tertiary">
              {t("chat.message.toolMoreVideos", {
                count: videos.length - 2,
              })}
            </div>
          )}
          {analysisBlock}
        </ToolInlineDetails>
      )}
    </CollapsiblePill>
  );
});

export { VideoAnalyzeItem };
