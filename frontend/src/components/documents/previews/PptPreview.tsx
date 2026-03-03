import { memo, useEffect, useRef, useState, useCallback } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Minimize2,
  AlertCircle,
  Grid3X3,
} from "lucide-react";
import { LoadingSpinner } from "../../common/LoadingSpinner";

interface PptPreviewProps {
  url: string;
  arrayBuffer?: ArrayBuffer | null;
  fileName: string;
  t: (key: string, options?: Record<string, unknown>) => string;
}

const PptPreview = memo(function PptPreview({
  url,
  arrayBuffer,
  fileName,
  t,
}: PptPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const renderContainerRef = useRef<HTMLDivElement>(null);
  const previewerRef = useRef<{
    renderSingleSlide: (slideIndex: number) => void;
    renderNextSlide: () => void;
    renderPreSlide: () => void;
    slideCount: number;
    currentIndex: number;
    destroy: () => void;
  } | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentSlide, setCurrentSlide] = useState(1);
  const [totalSlides, setTotalSlides] = useState(0);
  const [scale, setScale] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showThumbnails, setShowThumbnails] = useState(false);

  // Drag/pan state
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [translate, setTranslate] = useState({ x: 0, y: 0 });

  // Touch zoom state
  const [touchStart, setTouchStart] = useState<{
    x: number;
    y: number;
    distance: number;
  } | null>(null);

  // Determine file type
  const isPptx = fileName.toLowerCase().endsWith(".pptx");

  // Zoom limits - lower minimum for mobile to see full slide
  const MIN_SCALE = 0.25;
  const MAX_SCALE = 3;

  // Handle wheel zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    setScale((prev) => Math.min(Math.max(prev + delta, MIN_SCALE), MAX_SCALE));
  }, []);

  // Handle touch zoom
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      setTouchStart({
        x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
        y: (e.touches[0].clientY + e.touches[1].clientY) / 2,
        distance: Math.sqrt(dx * dx + dy * dy),
      });
    }
  }, []);

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (e.touches.length === 2 && touchStart) {
        e.preventDefault();
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const delta = (distance - touchStart.distance) / 200;
        setScale((prev) =>
          Math.min(Math.max(prev + delta, MIN_SCALE), MAX_SCALE),
        );
        setTouchStart({ ...touchStart, distance });
      }
    },
    [touchStart],
  );

  const handleTouchEnd = useCallback(() => {
    setTouchStart(null);
  }, []);

  // Handle mouse drag to pan
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.button !== 0) return;
      setIsDragging(true);
      setDragStart({ x: e.clientX - translate.x, y: e.clientY - translate.y });
    },
    [translate],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDragging) return;
      setTranslate({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    },
    [isDragging, dragStart],
  );

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Navigation - slides are 1-indexed for UI
  const goToSlide = useCallback(
    (index: number) => {
      if (index < 1 || index > totalSlides) return;
      if (!previewerRef.current) {
        console.warn("[PptPreview] Previewer not initialized");
        return;
      }

      const previewer = previewerRef.current;
      const targetIndex = index - 1; // Convert to 0-based for renderSingleSlide

      console.log(
        "[PptPreview] Going to slide",
        index,
        "targetIndex:",
        targetIndex,
        "currentIndex:",
        previewer.currentIndex,
      );

      // Use renderNextSlide/renderPreSlide for adjacent slides for better performance
      if (index === currentSlide + 1) {
        previewer.renderNextSlide();
      } else if (index === currentSlide - 1) {
        previewer.renderPreSlide();
      } else {
        // For non-adjacent slides, use renderSingleSlide
        previewer.renderSingleSlide(targetIndex);
      }

      setCurrentSlide(index);
    },
    [totalSlides, currentSlide],
  );

  const nextSlide = useCallback(() => {
    if (currentSlide < totalSlides) {
      goToSlide(currentSlide + 1);
    }
  }, [currentSlide, totalSlides, goToSlide]);

  const prevSlide = useCallback(() => {
    if (currentSlide > 1) {
      goToSlide(currentSlide - 1);
    }
  }, [currentSlide, goToSlide]);

  // Zoom controls
  const zoomIn = useCallback(() => {
    setScale((prev) => Math.min(prev + 0.2, MAX_SCALE));
  }, []);

  const zoomOut = useCallback(() => {
    setScale((prev) => Math.max(prev - 0.2, MIN_SCALE));
  }, []);

  const fitToScreen = useCallback(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    const containerWidth = container.clientWidth;
    const containerHeight = container.clientHeight - 60; // Account for toolbar

    // Slide dimensions (16:9 aspect ratio)
    const slideWidth = 960;
    const slideHeight = 540;

    // Calculate scale to fit
    const scaleX = containerWidth / slideWidth;
    const scaleY = containerHeight / slideHeight;
    const fitScale = Math.min(scaleX, scaleY) * 0.95; // 5% padding

    setScale(Math.max(fitScale, MIN_SCALE));
    setTranslate({ x: 0, y: 0 });
  }, []);

  // Fullscreen toggle
  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;

    if (!isFullscreen) {
      containerRef.current.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  }, [isFullscreen]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
    };
  }, []);

  // Initialize pptx-preview for .pptx files
  useEffect(() => {
    if (!isPptx || !arrayBuffer || !renderContainerRef.current) return;

    const initPreview = async () => {
      setIsLoading(true);
      setError(null);
      setTranslate({ x: 0, y: 0 });

      try {
        const { init } = await import("pptx-preview");

        const container = renderContainerRef.current;
        if (!container) {
          throw new Error("Render container not found");
        }

        // Clear previous content
        container.innerHTML = "";

        const previewWidth = 960;
        const previewHeight = 540;

        console.log(
          "[PptPreview] Initializing with dimensions:",
          previewWidth,
          "x",
          previewHeight,
        );

        const previewer = init(container, {
          width: previewWidth,
          height: previewHeight,
        });

        previewerRef.current = previewer;

        console.log("[PptPreview] Loading presentation...");
        await previewer.preview(arrayBuffer);
        console.log(
          "[PptPreview] Presentation loaded, slideCount:",
          previewer.slideCount,
          "currentIndex:",
          previewer.currentIndex,
        );

        setTotalSlides(previewer.slideCount);
        setCurrentSlide(1);
        setIsLoading(false);
      } catch (err) {
        console.error("Failed to initialize pptx-preview:", err);
        setError(
          err instanceof Error
            ? err.message
            : t("documents.failedToLoadPresentation"),
        );
        setIsLoading(false);
      }
    };

    initPreview();
  }, [isPptx, arrayBuffer, t]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (previewerRef.current) {
        try {
          previewerRef.current.destroy?.();
        } catch {
          // Ignore destroy errors
        }
        previewerRef.current = null;
      }
    };
  }, []);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") {
        prevSlide();
      } else if (e.key === "ArrowRight") {
        nextSlide();
      } else if (e.key === "Escape" && showThumbnails) {
        setShowThumbnails(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [prevSlide, nextSlide, showThumbnails]);

  // For .ppt files, use Office Online iframe
  if (!isPptx) {
    const officeUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(
      url,
    )}`;

    return (
      <div className="h-full w-full flex flex-col">
        <iframe
          src={officeUrl}
          className="flex-1 w-full min-h-[400px] border-0"
          title="PowerPoint Preview"
        />
      </div>
    );
  }

  return (
    <div ref={containerRef} className="flex flex-col h-full bg-black relative">
      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-black">
          <LoadingSpinner size="lg" className="mb-4" />
          <p className="text-white/60 text-sm">
            {t("documents.loadingPresentation")}
          </p>
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-black p-8">
          <AlertCircle className="w-12 h-12 text-red-400 mb-4" />
          <p className="text-white font-medium mb-2">
            {t("documents.failedToLoadPresentation")}
          </p>
          <p className="text-sm text-white/50 text-center max-w-md">{error}</p>
        </div>
      )}

      {/* Bottom navigation bar - ChatGPT style */}
      <div className="absolute bottom-0 left-0 right-0 z-10 p-3 bg-gradient-to-t from-black/80 to-transparent">
        <div className="flex items-center justify-center gap-2">
          {/* Thumbnails toggle - Desktop only */}
          <button
            onClick={() => setShowThumbnails(!showThumbnails)}
            className={`hidden sm:flex p-2 rounded-lg transition-colors ${
              showThumbnails
                ? "bg-white/20 text-white"
                : "bg-white/10 text-white/70 hover:bg-white/20 hover:text-white"
            }`}
            title={t("documents.thumbnails")}
          >
            <Grid3X3 className="w-5 h-5" />
          </button>

          {/* Navigation controls */}
          <div className="flex items-center gap-1 bg-white/10 rounded-full p-1">
            <button
              onClick={prevSlide}
              disabled={currentSlide <= 1}
              className="p-2 rounded-full text-white/70 hover:text-white hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-2 px-3">
              <input
                type="number"
                value={currentSlide}
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  if (!isNaN(val)) goToSlide(val);
                }}
                className="w-10 text-center bg-transparent text-white text-sm font-medium border-none outline-none"
                min={1}
                max={totalSlides}
              />
              <span className="text-white/50 text-sm">/ {totalSlides}</span>
            </div>

            <button
              onClick={nextSlide}
              disabled={currentSlide >= totalSlides}
              className="p-2 rounded-full text-white/70 hover:text-white hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>

          {/* Zoom controls */}
          <div className="flex items-center gap-1 bg-white/10 rounded-full p-1">
            <button
              onClick={zoomOut}
              className="p-2 rounded-full text-white/70 hover:text-white hover:bg-white/10 transition-all"
              title={t("documents.zoomOut")}
            >
              <ZoomOut className="w-4 h-4" />
            </button>
            <button
              onClick={fitToScreen}
              className="px-2 text-white/70 hover:text-white text-xs font-medium min-w-[48px] transition-colors"
              title={t("documents.fitToScreen")}
            >
              {Math.round(scale * 100)}%
            </button>
            <button
              onClick={zoomIn}
              className="p-2 rounded-full text-white/70 hover:text-white hover:bg-white/10 transition-all"
              title={t("documents.zoomIn")}
            >
              <ZoomIn className="w-4 h-4" />
            </button>
          </div>

          {/* Fullscreen toggle */}
          <button
            onClick={toggleFullscreen}
            className="p-2 rounded-lg bg-white/10 text-white/70 hover:bg-white/20 hover:text-white transition-colors"
            title={
              isFullscreen
                ? t("documents.exitFullscreen")
                : t("documents.fullscreen")
            }
          >
            {isFullscreen ? (
              <Minimize2 className="w-5 h-5" />
            ) : (
              <Maximize2 className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>

      {/* Thumbnails sidebar - Desktop slide-in panel */}
      {showThumbnails && (
        <>
          {/* Backdrop */}
          <div
            className="hidden sm:block fixed inset-0 z-15 bg-black/50"
            onClick={() => setShowThumbnails(false)}
          />

          {/* Sidebar */}
          <div className="hidden sm:flex flex-col fixed left-0 top-0 bottom-0 w-64 z-20 bg-stone-900 border-r border-white/10 shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <h3 className="text-white font-medium text-sm">
                {t("documents.slides")}
              </h3>
              <button
                onClick={() => setShowThumbnails(false)}
                className="p-1 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition-colors"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {Array.from({ length: totalSlides }, (_, i) => (
                <button
                  key={i + 1}
                  onClick={() => {
                    goToSlide(i + 1);
                    setShowThumbnails(false);
                  }}
                  className={`w-full rounded-lg overflow-hidden transition-all ${
                    currentSlide === i + 1
                      ? "ring-2 ring-blue-500 ring-offset-2 ring-offset-stone-900"
                      : "hover:bg-white/5"
                  }`}
                >
                  <div className="aspect-video bg-stone-800 flex items-center justify-center">
                    <span className="text-white/40 text-sm font-medium">
                      {i + 1}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Mobile thumbnails bottom sheet */}
      {showThumbnails && (
        <div className="sm:hidden fixed inset-0 z-20">
          <div
            className="absolute inset-0 bg-black/70"
            onClick={() => setShowThumbnails(false)}
          />
          <div className="absolute bottom-0 left-0 right-0 bg-stone-900 rounded-t-2xl max-h-[60vh] overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <h3 className="text-white font-medium">
                {t("documents.slides")}
              </h3>
              <button
                onClick={() => setShowThumbnails(false)}
                className="p-2 rounded-full text-white/50 hover:text-white hover:bg-white/10"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 grid grid-cols-3 gap-3 overflow-y-auto max-h-[50vh]">
              {Array.from({ length: totalSlides }, (_, i) => (
                <button
                  key={i + 1}
                  onClick={() => {
                    goToSlide(i + 1);
                    setShowThumbnails(false);
                  }}
                  className={`rounded-lg overflow-hidden transition-all ${
                    currentSlide === i + 1
                      ? "ring-2 ring-blue-500"
                      : "opacity-70"
                  }`}
                >
                  <div className="aspect-video bg-stone-800 flex items-center justify-center">
                    <span className="text-white/60 text-xs font-medium">
                      {i + 1}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Main slide viewer */}
      <div
        className="flex-1 overflow-hidden flex items-center justify-center"
        style={{
          cursor: isDragging ? "grabbing" : "grab",
        }}
        onWheel={handleWheel}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
      >
        <div
          style={{
            transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
            transformOrigin: "center center",
            transition: isDragging ? "none" : "transform 0.2s ease-out",
          }}
        >
          <div
            ref={renderContainerRef}
            className="rounded-lg overflow-hidden shadow-2xl"
            style={{ width: 960, height: 540 }}
          />
        </div>
      </div>
    </div>
  );
});

export default PptPreview;
