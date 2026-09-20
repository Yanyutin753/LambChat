import { memo, useMemo } from "react";
import { Eye, MessageSquareText, ScanSearch } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { MarkdownContent } from "../MarkdownContent";
import { ImageWithSkeleton } from "../ImageWithSkeleton";
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
import { useImagePreviewFallback } from "./imagePreviewFallback";
import { fileNameFromUrl } from "./toolImageResults";
import { getFullUrl } from "../../../../services/api/config";
import { buildChatThumbUrl } from "../../../../utils/chatThumbs";

function truncate(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1)}...`;
}

function getImageUrls(args: Record<string, unknown>): string[] {
  const rawUrls = args.image_urls;
  if (Array.isArray(rawUrls)) {
    return rawUrls.filter((url): url is string => typeof url === "string");
  }
  return typeof rawUrls === "string" ? [rawUrls] : [];
}

/** 解析为绝对 URL + 文件名，供缩略图网格与查看器使用 */
function resolveImages(urls: string[]) {
  return urls.map((url) => {
    const resolved = getFullUrl(url) || url;
    return { url: resolved, name: fileNameFromUrl(url) };
  });
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

/** 面板详情：独立于 pill 渲染，实时跟随 toolCallPanelStore 数据重建 */
function ImageAnalyzeDetail({ args, result }: ToolDetailProps) {
  const { t } = useTranslation();
  const { openImage, viewer } = useImagePreviewFallback();
  const images = useMemo(() => resolveImages(getImageUrls(args)), [args]);
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
      {images.length > 0 && (
        <div
          className="grid gap-2"
          style={{
            gridTemplateColumns: `repeat(${Math.min(images.length, 4)}, 1fr)`,
          }}
        >
          {images.map((image, index) => (
            <button
              type="button"
              key={`${image.url}-${index}`}
              className="group/img relative rounded-lg overflow-hidden border border-theme-border hover:border-theme-text-tertiary hover:shadow-lg transition-all duration-200 cursor-zoom-in"
              title={image.name}
              aria-label={t("chat.message.toolImageAnalyzeAlt", {
                index: index + 1,
              })}
              onClick={() => openImage(image.url, image.name)}
            >
              <ImageWithSkeleton
                src={image.url}
                thumbSrc={buildChatThumbUrl(image.url)}
                alt={t("chat.message.toolImageAnalyzeAlt", {
                  index: index + 1,
                })}
                skipUrlResolve
                inline
                className="w-full aspect-square object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent opacity-0 group-hover/img:opacity-100 transition-opacity pointer-events-none">
                <span className="absolute bottom-1.5 left-1.5 right-1.5 text-white/90 text-10 font-medium truncate drop-shadow-sm block">
                  {image.name}
                </span>
              </div>
            </button>
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
      {viewer}
    </div>
  );
}

const ImageAnalyzeItem = memo(function ImageAnalyzeItem({
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
  const { openImage, viewer } = useImagePreviewFallback();
  const durationFooter = (
    <ToolDurationFooter startedAt={startedAt} completedAt={completedAt} />
  );
  const imageUrls = useMemo(() => getImageUrls(args), [args]);
  const images = useMemo(() => resolveImages(imageUrls), [imageUrls]);
  const prompt = (args.prompt as string) || "";
  const analysis = useMemo(() => getAnalysisText(result), [result]);
  // 参数生成中（无结果）也允许打开面板：实时等待分析结果
  const canExpand =
    images.length > 0 || !!prompt || !!analysis || !!isPending;
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
    <ImageAnalyzeDetail
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  const imageSummary =
    images.length > 1
      ? t("chat.message.toolImageAnalyzeCount", { count: images.length })
      : images[0]?.name || "";

  // 进行中：标签学「思考中」，平滑流出正在生成的参数尾部
  const { label, isStreamingLabel } = useToolStreamingLabel(
    `${t("chat.message.toolImageAnalyze")} ${
      prompt ? truncate(prompt, 56) : truncate(imageSummary, 56)
    }`,
    args,
    { isPending, result },
  );

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<ScanSearch size={12} className="shrink-0 opacity-50" />}
        label={label}
        animatedDots={isStreamingLabel}
        variant="tool"
        formatLabel={false}
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: t("chat.message.toolImageAnalyze"),
            icon: <Eye size={16} />,
            status,
            subtitle: imageSummary || prompt || undefined,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <ImageAnalyzeDetail {...toolDetailPropsFromPanelData(data)} />
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
            {images.length > 0 && (
              <div className="grid grid-cols-4 gap-1.5">
                {images.slice(0, 4).map((image, index) => (
                  <button
                    type="button"
                    key={`${image.url}-${index}`}
                    className="relative rounded-md overflow-hidden border border-theme-border hover:border-theme-text-tertiary transition-colors cursor-zoom-in"
                    title={image.name}
                    aria-label={t("chat.message.toolImageAnalyzeAlt", {
                      index: index + 1,
                    })}
                    onClick={() => openImage(image.url, image.name)}
                  >
                    <ImageWithSkeleton
                      src={image.url}
                      thumbSrc={buildChatThumbUrl(image.url)}
                      alt={t("chat.message.toolImageAnalyzeAlt", {
                        index: index + 1,
                      })}
                      skipUrlResolve
                      inline
                      className="w-full aspect-square object-cover"
                    />
                  </button>
                ))}
                {images.length > 4 && (
                  <div
                    className="rounded-md bg-theme-bg-subtle border border-theme-border flex items-center justify-center text-theme-text-secondary text-11 font-medium aspect-square"
                    title={t("chat.message.toolMoreImages", {
                      count: images.length - 4,
                    })}
                  >
                    +{images.length - 4}
                  </div>
                )}
              </div>
            )}
            {analysisBlock}
          </ToolInlineDetails>
        )}
      </CollapsiblePill>
      {viewer}
    </>
  );
});

export { ImageAnalyzeItem };
