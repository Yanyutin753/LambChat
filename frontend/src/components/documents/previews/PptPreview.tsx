import { memo, useEffect, useRef, useState } from "react";
import { FileWarning } from "lucide-react";
import { pptxToHtml } from "@jvmr/pptx-to-html";
import type { TFunction } from "i18next";
import FileFallbackPanel from "./FileFallbackPanel";
import { extractPptxSlideTexts, type PptTextSlide } from "./pptTextPreview";
import { normalizePptxRenderedHtml } from "./pptHtmlPreview";
import {
  DocumentViewerFrame,
  ScaledDocumentContent,
} from "./DocumentViewerFrame";

interface PptPreviewProps {
  url: string;
  arrayBuffer?: ArrayBuffer | null;
  fileName: string;
  t: TFunction;
}

const PPT_PREVIEW_WIDTH = 960;
const PPT_PREVIEW_HEIGHT = 540;
const PPT_SLIDE_GAP = 20;

const PptPreview = memo(function PptPreview({
  url,
  arrayBuffer,
  fileName,
  t,
}: PptPreviewProps) {
  const renderRef = useRef<HTMLDivElement | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [textSlides, setTextSlides] = useState<PptTextSlide[]>([]);
  const [contentHeight, setContentHeight] = useState(PPT_PREVIEW_HEIGHT);

  useEffect(() => {
    const renderTarget = renderRef.current;
    if (!renderTarget || !arrayBuffer) {
      setLoading(false);
      setLoadFailed(true);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setLoadFailed(false);
    setTextSlides([]);
    setContentHeight(PPT_PREVIEW_HEIGHT);
    renderTarget.innerHTML = "";

    pptxToHtml(arrayBuffer.slice(0), {
      width: PPT_PREVIEW_WIDTH,
      height: PPT_PREVIEW_HEIGHT,
      scaleToFit: true,
      letterbox: true,
    })
      .then(async (slidesHtml) => {
        if (cancelled) return;

        if (slidesHtml.length > 0) {
          renderTarget.innerHTML = slidesHtml
            .map(
              (slideHtml) =>
                `<div class="ppt-html-preview-slide">${normalizePptxRenderedHtml(
                  slideHtml,
                )}</div>`,
            )
            .join("");
          setContentHeight(
            renderTarget.scrollHeight ||
              slidesHtml.length * PPT_PREVIEW_HEIGHT +
                Math.max(0, slidesHtml.length - 1) * PPT_SLIDE_GAP,
          );
          setLoading(false);
          return;
        }

        const slides = await extractPptxSlideTexts(arrayBuffer.slice(0));
        if (cancelled) return;
        setTextSlides(slides);
        setLoadFailed(slides.length === 0);
        setLoading(false);
      })
      .catch(async (error) => {
        console.error("Failed to render PPT preview:", error);
        if (cancelled) return;

        try {
          const slides = await extractPptxSlideTexts(arrayBuffer.slice(0));
          if (cancelled) return;
          setTextSlides(slides);
          setLoadFailed(slides.length === 0);
          setLoading(false);
        } catch (fallbackError) {
          console.error("Failed to extract PPT text preview:", fallbackError);
          if (cancelled) return;
          setLoadFailed(true);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      renderTarget.innerHTML = "";
    };
  }, [arrayBuffer]);

  if (!loading && textSlides.length > 0) {
    return (
      <div className="h-full min-h-[400px] w-full overflow-auto bg-stone-100 px-4 py-5 dark:bg-stone-950 sm:px-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {textSlides.map((slide) => (
            <section
              key={slide.index}
              className="rounded-lg bg-white p-5 shadow-sm ring-1 ring-black/5 dark:bg-stone-900 dark:ring-white/10"
            >
              <div className="mb-3 text-xs font-medium uppercase tracking-wide text-stone-400 dark:text-stone-500">
                {t("documents.pptSlideLabel", "幻灯片 {{count}}", {
                  count: slide.index,
                })}
              </div>
              <p className="whitespace-pre-wrap text-sm leading-6 text-stone-700 dark:text-stone-200">
                {slide.text}
              </p>
            </section>
          ))}
        </div>
      </div>
    );
  }

  if (loadFailed) {
    return (
      <FileFallbackPanel
        icon={FileWarning}
        iconBg="bg-amber-100 dark:bg-amber-900/40"
        iconColor="text-amber-600 dark:text-amber-300"
        title={t("documents.pptPreviewUnavailable", "PPT 预览不可用")}
        description={t(
          "documents.pptPreviewUnavailableHint",
          "当前浏览器无法直接渲染这个演示文稿。旧版 .ppt 或复杂版式可能需要下载后用 PowerPoint、WPS 或 Keynote 打开。",
        )}
        downloadUrl={url}
        fileName={fileName}
        downloadLabel={t("documents.downloadFile")}
      />
    );
  }

  return (
    <DocumentViewerFrame
      naturalWidth={PPT_PREVIEW_WIDTH}
      loading={loading}
      ariaLabel={`PowerPoint - ${fileName}`}
    >
      {({ displayScale }) => (
        <ScaledDocumentContent
          naturalWidth={PPT_PREVIEW_WIDTH}
          naturalHeight={contentHeight}
          displayScale={displayScale}
          contentRef={renderRef}
          className="flex flex-col gap-5"
        />
      )}
    </DocumentViewerFrame>
  );
});

export default PptPreview;
