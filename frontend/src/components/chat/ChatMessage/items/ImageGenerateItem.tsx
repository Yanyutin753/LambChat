import { memo, useMemo, useState, useCallback } from "react";
import { clsx } from "clsx";
import { Sparkles, ImageIcon, Tag, Layers, ImagePlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill, CopyButton, ImageViewer } from "../../../common";
import { ImageWithSkeleton } from "../ImageWithSkeleton";
import { extractText } from "./toolUtils";
import { extractGeneratedImageResults } from "./toolImageResults";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { useSessionImageGallery } from "../sessionImageGallery";
import { getFullUrl } from "../../../../services/api/config";
import { buildChatThumbUrl } from "../../../../utils/chatThumbs";

/** 面板详情：独立于 pill 渲染，实时跟随 toolCallPanelStore 数据重建 */
function ImageGenerateDetail({
  args,
  result,
  success,
  isPending,
  cancelled,
}: ToolDetailProps) {
  const { t } = useTranslation();
  const sessionImageGallery = useSessionImageGallery();
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);

  const openImagePreview = useCallback(
    (src: string) => {
      sessionImageGallery?.openImage(src);
      if (!sessionImageGallery) {
        setImageViewerSrc(src);
      }
    },
    [sessionImageGallery],
  );

  const prompt = (args.prompt as string) || "";
  const size = (args.size as string) || "";
  const quality = (args.quality as string) || "";
  const outputFormat = (args.output_format as string) || "";
  const model = (args.model as string) || "";
  const style = (args.style as string) || "";

  const inputImages: string[] = useMemo(() => {
    const raw = args.input_images;
    if (!raw) return [];
    if (Array.isArray(raw))
      return raw.filter((v): v is string => typeof v === "string");
    return [];
  }, [args.input_images]);

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
            <div className="text-sm text-theme-text font-semibold truncate">
              {t("chat.message.toolImageGenerate")}
            </div>
            <div className="text-xs text-theme-text-tertiary truncate mt-0.5">
              {t(
                "chat.message.toolImageGenerateDesc",
                "AI-powered image generation",
              )}
            </div>
          </div>
          {images.length > 0 && (
            <span className="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-theme-bg-subtle text-theme-text-secondary text-xs font-medium shadow-sm">
              <ImageIcon size={10} />
              {images.length}
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

        {/* ── Tags ── */}
        <div className="flex flex-wrap gap-1.5">
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-secondary text-xs">
            <Tag size={9} className="opacity-50" />
            {t("chat.message.toolImageTag")}
          </span>
          {model && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-secondary text-xs">
              <Layers size={9} className="opacity-50" />
              {model}
            </span>
          )}
          {size && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-secondary text-xs">
              <ImageIcon size={10} className="opacity-50" />
              {size}
            </span>
          )}
          {quality && (
            <span className="px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-secondary text-xs capitalize">
              {quality}
            </span>
          )}
          {style && (
            <span className="px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-secondary text-xs capitalize">
              {style}
            </span>
          )}
          {outputFormat && (
            <span className="px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-secondary text-xs font-mono uppercase">
              {outputFormat}
            </span>
          )}
          {inputImages.length > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-secondary text-xs">
              <ImagePlus size={10} className="opacity-50" />
              {t("chat.message.toolImageRefCount", { count: inputImages.length })}
            </span>
          )}
        </div>

        {/* ── Prompt ── */}
        {prompt && (
          <div className="relative rounded-lg tool-code-block">
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-theme-bg-subtle text-theme-text-tertiary text-xs transition-colors duration-200">
              <Sparkles size={12} className="text-theme-text-secondary" />
              <span className="min-w-0 flex-1 truncate">
                {t("chat.message.toolImagePrompt")}
              </span>
              <CopyButton
                text={prompt}
                size={12}
                className="!h-6 !w-6 !rounded-md !bg-theme-bg-card/80 !border !border-theme-border"
              />
            </div>
            <div className="px-3 py-2 text-sm text-theme-text-secondary whitespace-pre-wrap break-words leading-relaxed">
              {prompt}
            </div>
          </div>
        )}

        {/* ── Reference Images ── */}
        {inputImages.length > 0 && (
          <div className="rounded-lg border border-theme-border overflow-hidden">
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-theme-bg-subtle text-theme-text-tertiary text-xs">
              <ImagePlus size={12} className="text-theme-text-secondary" />
              <span className="min-w-0 flex-1 truncate">
                {t("chat.message.toolImageRefImages", "Reference Images")}
              </span>
              <span className="shrink-0 text-10 text-theme-text-secondary">
                {inputImages.length}
              </span>
            </div>
            <div
              className="p-2 grid gap-2"
              style={{
                gridTemplateColumns: `repeat(${Math.min(
                  inputImages.length,
                  4,
                )}, 1fr)`,
              }}
            >
              {inputImages.map((imgUrl, i) => {
                const resolvedUrl = getFullUrl(imgUrl) || imgUrl;
                return (
                  <div
                    key={i}
                    className={clsx(
                      "relative rounded-lg overflow-hidden",
                      "border border-dashed border-theme-border",
                      "hover:border-theme-text-tertiary",
                      "transition-colors cursor-pointer",
                    )}
                    onClick={() => openImagePreview(resolvedUrl)}
                  >
                    <ImageWithSkeleton
                      src={resolvedUrl}
                      thumbSrc={buildChatThumbUrl(resolvedUrl)}
                      alt={t("chat.message.toolImageRefAlt", { index: i + 1 })}
                      skipUrlResolve
                      inline
                      className="w-full aspect-square object-cover"
                    />
                    <div className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-black/50 text-white text-9 font-medium">
                      #{i + 1}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Image Gallery ── */}
        {images.length > 0 && (
          <div
            className={clsx(
              "grid gap-2.5",
              images.length === 1 ? "grid-cols-1" : "grid-cols-2",
            )}
          >
            {images.map((img, i) => (
              <div
                key={i}
                className={clsx(
                  "ai-image-generation-result group/img relative rounded-xl overflow-hidden",
                  "border border-theme-border",
                  "hover:shadow-lg hover:border-theme-text-tertiary",
                  "transition-all duration-200",
                  "cursor-pointer",
                )}
                onClick={() => openImagePreview(img.url)}
              >
                <ImageWithSkeleton
                  src={img.url}
                  thumbSrc={buildChatThumbUrl(img.url)}
                  alt={img.name}
                  skipUrlResolve
                  inline
                  className="w-full aspect-square object-cover"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent opacity-0 group-hover/img:opacity-100 transition-opacity">
                  <div className="absolute bottom-2 left-2 right-2">
                    <span className="text-white/90 text-11 font-medium truncate block drop-shadow-sm">
                      {img.name}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── Fallback Text ── */}
        {fallbackText && (
          <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words p-3 rounded-lg bg-theme-bg border border-theme-border">
            {fallbackText}
            <ToolHoverCopyButton
              text={fallbackText}
              position="result"
              copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
            />
          </pre>
        )}
      </div>

      {/* Fallback ImageViewer when session gallery context is unavailable */}
      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          isOpen={!!imageViewerSrc}
          onClose={() => setImageViewerSrc(null)}
        />
      )}
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
  const sessionImageGallery = useSessionImageGallery();
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);
  const durationFooter = (
    <ToolDurationFooter startedAt={startedAt} completedAt={completedAt} />
  );

  const openImagePreview = useCallback(
    (src: string) => {
      sessionImageGallery?.openImage(src);
      if (!sessionImageGallery) {
        setImageViewerSrc(src);
      }
    },
    [sessionImageGallery],
  );

  const prompt = (args.prompt as string) || "";
  const size = (args.size as string) || "";
  const quality = (args.quality as string) || "";

  const inputImages: string[] = useMemo(() => {
    const raw = args.input_images;
    if (!raw) return [];
    if (Array.isArray(raw))
      return raw.filter((v): v is string => typeof v === "string");
    return [];
  }, [args.input_images]);

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
        <span className="text-xs text-theme-text font-medium truncate min-w-0 flex-1 overflow-hidden">
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
        <ToolArgsBlock size="compact" wrap>
          <Sparkles size={12} className="shrink-0 text-theme-text-secondary" />
          <span className="truncate text-theme-text-secondary">
            {prompt.length > 120 ? prompt.slice(0, 117) + "…" : prompt}
          </span>
        </ToolArgsBlock>
      )}

      {/* Compact tags */}
      <div className="flex flex-wrap gap-1">
        {images.length > 0 && (
          <span className="px-1.5 py-0.5 rounded bg-theme-bg-subtle text-theme-text-secondary text-10">
            {t("chat.message.toolImageCount", { count: images.length })}
          </span>
        )}
        {inputImages.length > 0 && (
          <span className="px-1.5 py-0.5 rounded bg-theme-bg-subtle text-theme-text-secondary text-10">
            {t("chat.message.toolImageRefCount", { count: inputImages.length })}
          </span>
        )}
        {size && (
          <span className="px-1.5 py-0.5 rounded bg-theme-bg-subtle text-theme-text-secondary text-10 font-mono">
            {size}
          </span>
        )}
        {quality && (
          <span className="px-1.5 py-0.5 rounded bg-theme-bg-subtle text-theme-text-secondary text-10 capitalize">
            {quality}
          </span>
        )}
      </div>

      {/* Compact reference image thumbnails */}
      {inputImages.length > 0 && (
        <div className="flex gap-1.5 overflow-x-auto">
          {inputImages.slice(0, 4).map((imgUrl, i) => {
            const resolvedUrl = getFullUrl(imgUrl) || imgUrl;
            return (
              <div
                key={i}
                className="relative shrink-0 w-12 h-12 rounded-md overflow-hidden border border-dashed border-theme-border cursor-pointer"
                onClick={() => openImagePreview(resolvedUrl)}
              >
                <ImageWithSkeleton
                  src={resolvedUrl}
                  thumbSrc={buildChatThumbUrl(resolvedUrl)}
                  alt={t("chat.message.toolImageRefAltShort", { index: i + 1 })}
                  skipUrlResolve
                  inline
                  className="w-full h-full object-cover"
                />
                <div className="absolute top-0 left-0 px-0.5 py-px rounded-br bg-black/50 text-white text-8 leading-none font-medium">
                  {i + 1}
                </div>
              </div>
            );
          })}
          {inputImages.length > 4 && (
            <div className="shrink-0 w-12 h-12 rounded-md bg-theme-bg-subtle border border-dashed border-theme-border flex items-center justify-center text-theme-text-secondary text-10 font-medium">
              +{inputImages.length - 4}
            </div>
          )}
        </div>
      )}

      {/* Compact image grid */}
      {images.length > 0 && (
        <div className="grid grid-cols-2 gap-1.5">
          {images.slice(0, 4).map((img, i) => (
            <div
              key={i}
              className="ai-image-generation-result relative rounded-lg overflow-hidden border border-theme-border hover:border-theme-text-tertiary transition-colors cursor-pointer"
              onClick={() => openImagePreview(img.url)}
            >
              <ImageWithSkeleton
                src={img.url}
                thumbSrc={buildChatThumbUrl(img.url)}
                alt={img.name}
                skipUrlResolve
                inline
                className="w-full aspect-square object-cover"
              />
            </div>
          ))}
          {images.length > 4 && (
            <div className="absolute bottom-1 right-1 px-1.5 py-0.5 rounded bg-black/50 text-white text-9">
              +{images.length - 4}
            </div>
          )}
        </div>
      )}

      {/* Compact fallback */}
      {fallbackText && (
        <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words overflow-y-auto min-w-0">
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
        label={`${t("chat.message.toolImageGenerate")} ${
          prompt.length > 40 ? prompt.slice(0, 37) + "…" : prompt
        }`}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openToolLivePanel({
            id,
            title: t("chat.message.toolImageGenerate"),
            icon: <Sparkles size={16} />,
            status,
            subtitle:
              prompt.length > 80
                ? prompt.slice(0, 77) + "…"
                : prompt || undefined,
            fallback: detailContent || undefined,
            buildDetail: (data) => (
              <ImageGenerateDetail {...toolDetailPropsFromPanelData(data)} />
            ),
            footer: durationFooter,
          });
        }}
      >
        {compactContent}
      </CollapsiblePill>

      {/* Fallback ImageViewer when session gallery context is unavailable */}
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

export { ImageGenerateItem };
