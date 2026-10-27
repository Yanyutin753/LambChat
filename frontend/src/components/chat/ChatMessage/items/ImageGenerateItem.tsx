import { TagBadge } from "../../../common/TagBadge";
import { memo, useMemo } from "react";
import { clsx } from "clsx";
import { Sparkles, ImageIcon, Tag, Layers, ImagePlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill, CopyButton, formatFileSize } from "../../../common";
import { ImageWithSkeleton } from "../ImageWithSkeleton";
import { useToolStreamingLabel } from "./useToolStreamingLabel";
import { extractText } from "./toolUtils";
import {
  extractGeneratedImageResults,
  getGeneratedImageModel,
} from "./toolImageResults";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { useImagePreviewFallback } from "./imagePreviewFallback";
import { getFullUrl } from "../../../../services/api/config";
import { buildChatThumbUrl } from "../../../../utils/chatThumbs";

function resolveInputImages(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((value): value is string => typeof value === "string")
    .map((url) => getFullUrl(url) || url);
}

/** 面板详情：独立于 pill 渲染，实时跟随 toolCallPanelStore 数据重建 */
function ImageGenerateDetail({
  args,
  result,
  success,
  isPending,
  cancelled,
}: ToolDetailProps) {
  const { t } = useTranslation();

  const prompt = (args.prompt as string) || "";
  const size = (args.size as string) || "";
  const quality = (args.quality as string) || "";
  const outputFormat = (args.output_format as string) || "";
  const model = getGeneratedImageModel(result, args.model);
  const style = (args.style as string) || "";

  const inputImages = useMemo(
    () => resolveInputImages(args.input_images),
    [args.input_images],
  );

  const images = useMemo(() => {
    let parsed: unknown = result;
    if (typeof result === "string") {
      try {
        parsed = JSON.parse(result);
      } catch {
        return [];
      }
    }
    return extractGeneratedImageResults(parsed);
  }, [result]);

  // 参考图 + 生成图按卡片内顺序翻页
  const previewSiblings = useMemo(
    () => [
      ...inputImages.map((src) => ({ src })),
      ...images.map((img) => ({ src: img.url, alt: img.name })),
    ],
    [inputImages, images],
  );
  const { openImage, viewer } = useImagePreviewFallback(previewSiblings);

  const fallbackText = useMemo(() => {
    if (images.length > 0) return "";
    const text = extractText(result);
    if (!text) return "";
    try {
      const obj = JSON.parse(text);
      if (obj.revised_prompt) return obj.revised_prompt as string;
      if (obj.error) return obj.error as string;
    } catch {
      // not JSON
    }
    return text;
  }, [result, images.length]);

  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  return (
    <>
      <div className="ai-image-generation p-4 sm:p-5 space-y-3 tool-panel-content">
        {/* ── Character Card Header ── */}
        <div
          className={clsx(
            "ai-image-generation__header flex items-center gap-3 rounded-xl p-3",
            "border border-theme-border bg-theme-bg-card transition-colors",
          )}
        >
          <div className="ai-image-generation__icon w-10 h-10 sm:w-11 sm:h-11 rounded-lg flex items-center justify-center shrink-0 text-violet-500">
            <ImageIcon size={20} aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-14 font-serif text-theme-text font-semibold truncate">
              {t("chat.message.toolImageGenerate")}
            </div>
            <div className="text-12 text-theme-text-tertiary truncate mt-0.5">
              {t(
                "chat.message.toolImageGenerateDesc",
                "AI-powered image generation",
              )}
            </div>
          </div>
          {images.length > 0 && (
            <span className="shrink-0 inline-flex items-center gap-2 text-theme-text-secondary">
              <ImageIcon size={10} />
              <span className="count-badge">{Math.min(images.length, 99)}</span>
            </span>
          )}
        </div>

        {isPending && images.length === 0 && (
          <div
            className="ai-image-generation-frame"
            data-state={status}
            role="status"
            aria-label={t("chat.message.generatingImage", "Generating image")}
          >
            <div className="ig-canvas">
              <span className="ig-dots" aria-hidden />
              <span className="ig-glow" aria-hidden />
              {size && <span className="ig-res">{size}</span>}
            </div>
            <div className="ig-meta">
              <span className="ig-label">
                {t("chat.message.generatingImage", "Generating image")}
              </span>
              {prompt && (
                <span className="ig-prompt">
                  "{prompt.length > 80 ? prompt.slice(0, 77) + "…" : prompt}"
                </span>
              )}
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-1.5">
          <TagBadge icon={<Tag />}>{t("chat.message.toolImageTag")}</TagBadge>
          {model && <TagBadge icon={<Layers />}>{model}</TagBadge>}
          {size && <TagBadge icon={<ImageIcon />}>{size}</TagBadge>}
          {quality && <TagBadge className="capitalize">{quality}</TagBadge>}
          {style && <TagBadge className="capitalize">{style}</TagBadge>}
          {outputFormat && (
            <TagBadge className="font-mono uppercase">{outputFormat}</TagBadge>
          )}
          {inputImages.length > 0 && (
            <TagBadge icon={<ImagePlus />}>
              {t("chat.message.toolImageRefCount", {
                count: inputImages.length,
              })}
            </TagBadge>
          )}
        </div>

        {/* ── Prompt ── */}
        {prompt && (
          <div className="tool-surface">
            <div className="tool-surface__header">
              <Sparkles size={12} className="text-theme-text-secondary" />
              <span className="tool-surface__title min-w-0 flex-1 truncate">
                {t("chat.message.toolImagePrompt")}
              </span>
              <CopyButton text={prompt} size={12} />
            </div>
            <div className="tool-surface__body text-14 text-theme-text-secondary whitespace-pre-wrap break-words leading-relaxed">
              {prompt}
            </div>
          </div>
        )}

        {/* ── Reference Images ── */}
        {inputImages.length > 0 && (
          <div className="tool-surface">
            <div className="tool-surface__header text-12">
              <ImagePlus size={12} className="text-theme-text-secondary" />
              <span className="tool-surface__title min-w-0 flex-1 truncate">
                {t("chat.message.toolImageRefImages", "Reference Images")}
              </span>
              <span className="shrink-0 text-10 text-theme-text-secondary">
                {inputImages.length}
              </span>
            </div>
            <div className="p-2 flex gap-1.5 overflow-x-auto">
              {inputImages.map((imgUrl, i) => (
                <button
                  type="button"
                  key={`${imgUrl}-${i}`}
                  aria-label={t("chat.message.toolImageRefAlt", {
                    index: i + 1,
                  })}
                  className={clsx(
                    "relative shrink-0 w-12 h-12 rounded-md overflow-hidden",
                    "border border-theme-border focus-visible:outline focus-visible:outline-2 focus-visible:outline-theme-primary",
                    "hover:border-theme-text-tertiary",
                    "transition-colors cursor-pointer",
                  )}
                  onClick={() => openImage(imgUrl)}
                >
                  <ImageWithSkeleton
                    src={imgUrl}
                    thumbSrc={buildChatThumbUrl(imgUrl)}
                    alt={t("chat.message.toolImageRefAlt", { index: i + 1 })}
                    skipUrlResolve
                    inline
                    className="w-full h-full object-cover"
                  />
                  <div className="absolute top-0 left-0 px-0.5 py-px rounded-br bg-black/50 text-white text-8 leading-none font-medium">
                    {i + 1}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Image Gallery ── */}
        {images.length > 0 && (
          <div
            className={clsx(
              "grid w-md max-w-full gap-2.5",
              images.length === 1 ? "grid-cols-1" : "grid-cols-2",
            )}
          >
            {images.map((img, i) => (
              <figure
                key={i}
                className={clsx(
                  "ai-image-generation-result group/img relative rounded-xl overflow-hidden",
                  "border border-theme-border",
                  "hover:border-theme-text-tertiary",
                  "transition-colors duration-200",
                )}
              >
                <ImageWithSkeleton
                  src={img.url}
                  thumbSrc={buildChatThumbUrl(img.url)}
                  alt={img.name}
                  skipUrlResolve
                  inline
                  className="w-full h-auto object-contain bg-theme-bg-subtle"
                  onClick={() => openImage(img.url, img.name)}
                />
                <figcaption className="flex items-center gap-2 border-t border-theme-border bg-theme-bg px-2 py-1.5 text-12 text-theme-text-secondary">
                  <span className="min-w-0 flex-1 truncate" title={img.name}>
                    {img.name}
                  </span>
                  {img.size != null && (
                    <span className="shrink-0 tabular-nums">
                      {formatFileSize(img.size)}
                    </span>
                  )}
                </figcaption>
              </figure>
            ))}
          </div>
        )}

        {/* ── Fallback Text ── */}
        {fallbackText && (
          <pre className="group/result relative text-12 text-theme-text-tertiary whitespace-pre-wrap break-words p-3 rounded-lg bg-theme-bg border border-theme-border">
            {fallbackText}
            <ToolHoverCopyButton text={fallbackText} position="result" />
          </pre>
        )}
      </div>

      {viewer}
    </>
  );
}

const ImageGenerateItem = memo(function ImageGenerateItem({
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

  const prompt = (args.prompt as string) || "";
  const size = (args.size as string) || "";
  const quality = (args.quality as string) || "";
  const model = getGeneratedImageModel(result, args.model);

  const inputImages = useMemo(
    () => resolveInputImages(args.input_images),
    [args.input_images],
  );

  const images = useMemo(() => {
    let parsed: unknown = result;
    if (typeof result === "string") {
      try {
        parsed = JSON.parse(result);
      } catch {
        return [];
      }
    }
    return extractGeneratedImageResults(parsed);
  }, [result]);

  const previewSiblings = useMemo(
    () => [
      ...inputImages.map((src) => ({ src })),
      ...images.map((img) => ({ src: img.url, alt: img.name })),
    ],
    [inputImages, images],
  );
  const { openImage, viewer } = useImagePreviewFallback(previewSiblings);

  const fallbackText = useMemo(() => {
    if (images.length > 0) return "";
    const text = extractText(result);
    if (!text) return "";
    try {
      const obj = JSON.parse(text);
      if (obj.revised_prompt) return obj.revised_prompt as string;
      if (obj.error) return obj.error as string;
    } catch {
      // not JSON
    }
    return text;
  }, [result, images.length]);

  const canExpand =
    !!isPending ||
    !!prompt ||
    images.length > 0 ||
    !!fallbackText ||
    inputImages.length > 0;
  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  // 进行中：标签学「思考中」，平滑流出正在生成的参数尾部
  const { label, isStreamingLabel } = useToolStreamingLabel(
    `${t("chat.message.toolImageGenerate")} ${prompt}`,
    args,
    { isPending, result },
  );

  // ── detail (panel) content ─────────────────────────────────────────

  const detailContent = canExpand && (
    <ImageGenerateDetail
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  // pill 与收起态「+N」角标共用：面板里展示全部参考图与生成图
  const openPanel = () => {
    if (!canExpand) return;
    openToolLivePanel({
      id,
      title: t("chat.message.toolImageGenerate"),
      icon: <Sparkles size={16} />,
      status,
      subtitle:
        prompt.length > 80 ? prompt.slice(0, 77) + "…" : prompt || undefined,
      fallback: detailContent || undefined,
      buildDetail: (data) => (
        <ImageGenerateDetail {...toolDetailPropsFromPanelData(data)} />
      ),
      footer: durationFooter,
    });
  };

  // ── compact (inline) content ────────────────────────────────────────

  const compactContent = canExpand && (
    <ToolInlineDetails>
      {/* Mini character card */}
      <div className="ai-image-generation__compact-header flex items-center gap-2 px-2 py-1.5 rounded-lg mb-2 border border-theme-border bg-theme-bg-card">
        <ImageIcon
          size={14}
          className="shrink-0 text-theme-text-secondary"
          aria-hidden="true"
        />
        <span className="text-12 text-theme-text font-medium truncate min-w-0 flex-1 overflow-hidden">
          {t("chat.message.toolImageGenerate")}
        </span>
        {images.length > 0 && (
          <span className="ml-auto shrink-0 text-10 text-theme-text-secondary">
            {t("chat.message.toolImageImgCount", { count: images.length })}
          </span>
        )}
      </div>

      {isPending && images.length === 0 && (
        <div
          className="ai-image-generation-frame mb-2"
          data-state={status}
          role="status"
          aria-label={t("chat.message.generatingImage", "Generating image")}
        >
          <div className="ig-canvas ig-canvas--compact">
            <span className="ig-dots" aria-hidden />
            <span className="ig-glow" aria-hidden />
            {size && <span className="ig-res">{size}</span>}
          </div>
          <div className="ig-meta">
            <span className="ig-label">
              {t("chat.message.generatingImage", "Generating image")}
            </span>
            {prompt && (
              <span className="ig-prompt">
                "{prompt.length > 60 ? prompt.slice(0, 57) + "…" : prompt}"
              </span>
            )}
          </div>
        </div>
      )}

      {/* Compact prompt (only when not pending) */}
      {!isPending && prompt && (
        <ToolArgsBlock size="compact" copyText={prompt} wrap>
          <Sparkles size={12} className="shrink-0 text-theme-text-secondary" />
          <span className="truncate text-theme-text-secondary">
            {prompt.length > 120 ? prompt.slice(0, 117) + "…" : prompt}
          </span>
        </ToolArgsBlock>
      )}

      <div className="flex flex-wrap gap-1.5">
        {model && <TagBadge title={model}>{model}</TagBadge>}
        {images.length > 0 && (
          <TagBadge>
            {t("chat.message.toolImageCount", { count: images.length })}
          </TagBadge>
        )}
        {inputImages.length > 0 && (
          <TagBadge>
            {t("chat.message.toolImageRefCount", { count: inputImages.length })}
          </TagBadge>
        )}
        {size && <TagBadge className="font-mono">{size}</TagBadge>}
        {quality && <TagBadge className="capitalize">{quality}</TagBadge>}
      </div>

      {/* Compact reference image thumbnails */}
      {inputImages.length > 0 && (
        <div className="flex gap-1.5 overflow-x-auto">
          {inputImages.slice(0, 4).map((imgUrl, i) => (
            <button
              type="button"
              key={`${imgUrl}-${i}`}
              aria-label={t("chat.message.toolImageRefAltShort", {
                index: i + 1,
              })}
              className="relative shrink-0 w-12 h-12 rounded-md overflow-hidden border border-dashed border-theme-border cursor-pointer transition-colors hover:border-theme-text-tertiary focus-visible:outline focus-visible:outline-2 focus-visible:outline-theme-primary"
              onClick={() => openImage(imgUrl)}
            >
              <ImageWithSkeleton
                src={imgUrl}
                thumbSrc={buildChatThumbUrl(imgUrl)}
                alt={t("chat.message.toolImageRefAltShort", { index: i + 1 })}
                skipUrlResolve
                inline
                className="w-full h-full object-cover"
              />
              <div className="absolute top-0 left-0 px-0.5 py-px rounded-br bg-black/50 text-white text-8 leading-none font-medium">
                {i + 1}
              </div>
            </button>
          ))}
          {inputImages.length > 4 && (
            <button
              type="button"
              onClick={openPanel}
              aria-label={t("chat.message.toolMoreImages", {
                count: inputImages.length - 4,
              })}
              title={t("chat.message.toolMoreImages", {
                count: inputImages.length - 4,
              })}
              className="shrink-0 w-12 h-12 rounded-md bg-theme-bg-subtle border border-dashed border-theme-border flex items-center justify-center text-theme-text-secondary text-10 font-medium tabular-nums cursor-pointer transition-colors hover:border-theme-text-tertiary hover:text-theme-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-theme-primary"
            >
              +{inputImages.length - 4}
            </button>
          )}
        </div>
      )}

      {/* Compact image grid */}
      {images.length > 0 && (
        <div className="grid w-full max-w-md grid-cols-2 gap-1.5">
          {images.slice(0, 4).map((img, i) => (
            <figure
              key={i}
              className="ai-image-generation-result relative rounded-lg overflow-hidden border border-theme-border hover:border-theme-text-tertiary transition-colors cursor-pointer"
            >
              <ImageWithSkeleton
                src={img.url}
                thumbSrc={buildChatThumbUrl(img.url)}
                alt={img.name}
                skipUrlResolve
                inline
                className="w-full h-auto object-contain"
                onClick={() => openImage(img.url, img.name)}
              />
              <figcaption className="flex items-center gap-2 border-t border-theme-border bg-theme-bg px-2 py-1.5 text-12 text-theme-text-secondary">
                <span className="min-w-0 flex-1 truncate" title={img.name}>
                  {img.name}
                </span>
                {img.size != null && (
                  <span className="shrink-0 tabular-nums">
                    {formatFileSize(img.size)}
                  </span>
                )}
              </figcaption>
              {/* 最后一格盖「+N」：收起态只放 4 张，其余在面板里看全 */}
              {i === 3 && images.length > 4 && (
                <button
                  type="button"
                  onClick={openPanel}
                  aria-label={t("chat.message.toolMoreImages", {
                    count: images.length - 4,
                  })}
                  title={t("chat.message.toolMoreImages", {
                    count: images.length - 4,
                  })}
                  className="absolute inset-0 flex items-center justify-center bg-black/55 text-white text-16 font-semibold tabular-nums cursor-pointer transition-colors hover:bg-black/65 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-white"
                >
                  +{images.length - 4}
                </button>
              )}
            </figure>
          ))}
        </div>
      )}

      {/* Compact fallback */}
      {fallbackText && (
        <pre className="group/result relative text-12 text-theme-text-tertiary whitespace-pre-wrap break-words overflow-y-auto min-w-0">
          {fallbackText.length > 300
            ? fallbackText.slice(0, 297) + "…"
            : fallbackText}
          <ToolHoverCopyButton text={fallbackText} position="resultCompact" />
        </pre>
      )}
    </ToolInlineDetails>
  );

  return (
    <>
      <CollapsiblePill
        status={status}
        icon={<Sparkles size={12} className="shrink-0 opacity-50" />}
        label={label}
        suffix={model || undefined}
        animatedDots={isStreamingLabel}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={openPanel}
      >
        {compactContent}
      </CollapsiblePill>

      {viewer}
    </>
  );
});

export { ImageGenerateItem };
