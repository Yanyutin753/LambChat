import { memo, useEffect, useRef, useState, useCallback } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Minimize2,
  Loader2,
  AlertCircle,
} from "lucide-react";

interface PptPreviewProps {
  url: string;
  arrayBuffer?: ArrayBuffer | null;
  fileName: string;
}

const PptPreview = memo(function PptPreview({
  url,
  arrayBuffer,
  fileName,
}: PptPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const slideContainerRef = useRef<HTMLDivElement>(null);
  const previewerRef = useRef<{
    renderSingleSlide: (slideIndex: number) => void;
    slideCount: number;
  } | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentSlide, setCurrentSlide] = useState(1);
  const [totalSlides, setTotalSlides] = useState(0);
  const [scale, setScale] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);

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

  // Handle wheel zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    setScale((prev) => Math.min(Math.max(prev + delta, 0.5), 3));
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
        setScale((prev) => Math.min(Math.max(prev + delta, 0.5), 3));
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

  // Navigation - slides are 1-indexed for UI, but 0-indexed for pptx-preview
  const goToSlide = useCallback(
    (index: number) => {
      if (index < 1 || index > totalSlides) return;
      setCurrentSlide(index);
      previewerRef.current?.renderSingleSlide(index - 1); // Convert to 0-indexed
    },
    [totalSlides],
  );

  const nextSlide = useCallback(() => {
    goToSlide(currentSlide + 1);
  }, [currentSlide, goToSlide]);

  const prevSlide = useCallback(() => {
    goToSlide(currentSlide - 1);
  }, [currentSlide, goToSlide]);

  // Zoom controls
  const zoomIn = useCallback(() => {
    setScale((prev) => Math.min(prev + 0.2, 3));
  }, []);

  const zoomOut = useCallback(() => {
    setScale((prev) => Math.max(prev - 0.2, 0.5));
  }, []);

  const resetZoom = useCallback(() => {
    setScale(1);
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
    if (!isPptx || !arrayBuffer || !slideContainerRef.current) return;

    const initPreview = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const { init } = await import("pptx-preview");

        const container = slideContainerRef.current;
        if (!container) return;

        // Get container width for responsive sizing
        const containerWidth = container.clientWidth || 800;

        const previewer = init(container, {
          width: containerWidth,
        });

        previewerRef.current = previewer;

        await previewer.preview(arrayBuffer);

        setTotalSlides(previewer.slideCount);
        setCurrentSlide(1);
        setIsLoading(false);
      } catch (err) {
        console.error("Failed to initialize pptx-preview:", err);
        setError(
          err instanceof Error ? err.message : "Failed to load presentation",
        );
        setIsLoading(false);
      }
    };

    initPreview();
  }, [isPptx, arrayBuffer]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      previewerRef.current = null;
    };
  }, []);

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

  // Error state
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[400px] p-8">
        <AlertCircle className="w-12 h-12 text-red-500 mb-4" />
        <p className="text-red-600 dark:text-red-400 font-medium mb-2">
          Failed to load presentation
        </p>
        <p className="text-sm text-stone-500 dark:text-stone-400 text-center">
          {error}
        </p>
      </div>
    );
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[400px]">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500 mb-4" />
        <p className="text-stone-500 dark:text-stone-400">
          Loading presentation...
        </p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex flex-col h-full bg-stone-100 dark:bg-stone-900"
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-white dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700">
        {/* Navigation */}
        <div className="flex items-center gap-2">
          <button
            onClick={prevSlide}
            disabled={currentSlide <= 1}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 disabled:opacity-50 disabled:cursor-not-allowed"
            title="Previous slide"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <span className="text-sm text-stone-600 dark:text-stone-300 min-w-[80px] text-center">
            {currentSlide} / {totalSlides}
          </span>
          <button
            onClick={nextSlide}
            disabled={currentSlide >= totalSlides}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 disabled:opacity-50 disabled:cursor-not-allowed"
            title="Next slide"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>

        {/* Zoom controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={zoomOut}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700"
            title="Zoom out"
          >
            <ZoomOut className="w-5 h-5" />
          </button>
          <span
            onClick={resetZoom}
            className="text-sm text-stone-600 dark:text-stone-300 min-w-[50px] text-center cursor-pointer hover:bg-stone-100 dark:hover:bg-stone-700 px-2 py-1 rounded"
            title="Reset zoom"
          >
            {Math.round(scale * 100)}%
          </span>
          <button
            onClick={zoomIn}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700"
            title="Zoom in"
          >
            <ZoomIn className="w-5 h-5" />
          </button>
        </div>

        {/* Fullscreen toggle */}
        <button
          onClick={toggleFullscreen}
          className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700"
          title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
        >
          {isFullscreen ? (
            <Minimize2 className="w-5 h-5" />
          ) : (
            <Maximize2 className="w-5 h-5" />
          )}
        </button>
      </div>

      {/* Main content area with sidebar */}
      <div className="flex flex-1 overflow-hidden">
        {/* Thumbnails sidebar */}
        <div className="w-[120px] bg-white dark:bg-stone-800 border-r border-stone-200 dark:border-stone-700 overflow-y-auto p-2 flex flex-col gap-2">
          {Array.from({ length: totalSlides }, (_, i) => (
            <button
              key={i + 1}
              onClick={() => goToSlide(i + 1)}
              className={`w-full aspect-video rounded border-2 transition-all ${
                currentSlide === i + 1
                  ? "border-blue-500 dark:border-blue-400"
                  : "border-stone-200 dark:border-stone-700 hover:border-stone-300 dark:hover:border-stone-600"
              }`}
            >
              <div className="w-full h-full bg-stone-100 dark:bg-stone-700 rounded flex items-center justify-center text-xs text-stone-500 dark:text-stone-400">
                {i + 1}
              </div>
            </button>
          ))}
        </div>

        {/* Slide viewer */}
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
              ref={slideContainerRef}
              className="bg-white dark:bg-stone-800 shadow-lg"
            />
          </div>
        </div>
      </div>
    </div>
  );
});

export default PptPreview;
