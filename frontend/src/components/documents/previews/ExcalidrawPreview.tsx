import { memo, useEffect, useMemo, useState, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { ImageWithSkeleton } from "../../chat/ChatMessage/ImageWithSkeleton";
import { ViewerDropdownMenuItem } from "../../common";
import { ViewerTopBar } from "../../common/ViewerTopBar";
import { ViewerToolbar } from "../../common/ViewerToolbar";
import { ViewerTopBarButton } from "../../common/ViewerTopBarButton";
import { downloadBlob } from "../../common/viewerDownload";
import { AlertCircle, X, Download } from "lucide-react";

// Types for Excalidraw
interface ExcalidrawElement {
  id: string;
  [key: string]: unknown;
}

interface ExcalidrawAppState {
  viewBackgroundColor?: string;
  [key: string]: unknown;
}

interface ExcalidrawPreviewProps {
  data: string; // JSON string of excalidraw file content
}

// Cache for the export function
let exportToSvgFunc:
  | ((opts: {
      elements: readonly ExcalidrawElement[];
      appState?: ExcalidrawAppState;
    }) => Promise<SVGSVGElement>)
  | null = null;

const ExcalidrawPreview = memo(function ExcalidrawPreview({
  data,
}: ExcalidrawPreviewProps) {
  const { t } = useTranslation();
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Parse excalidraw data
  const parseData = useCallback((rawData: string) => {
    if (!rawData) return null;

    try {
      const parsed = JSON.parse(rawData);
      const elements = parsed.elements || parsed;
      const appState = parsed.appState || {};

      if (!Array.isArray(elements)) {
        return null;
      }

      return {
        elements: elements as ExcalidrawElement[],
        appState: {
          ...appState,
          viewBackgroundColor: appState.viewBackgroundColor || "#ffffff",
        },
      };
    } catch (err) {
      console.error("Failed to parse Excalidraw data:", err);
      return null;
    }
  }, []);

  // Load export function and render SVG
  useEffect(() => {
    if (!data) {
      setIsLoading(false);
      return;
    }

    const parsed = parseData(data);
    if (!parsed) {
      setError(t("documents.invalidExcalidrawFormat"));
      setIsLoading(false);
      return;
    }

    const renderSvg = async () => {
      try {
        // Load export function once
        if (!exportToSvgFunc) {
          const mod = await import("@excalidraw/excalidraw");
          exportToSvgFunc = mod.exportToSvg;
        }

        // Use local reference to satisfy TypeScript
        const exportFn = exportToSvgFunc;
        if (!exportFn) {
          throw new Error(t("documents.excalidrawExportFailed"));
        }

        const svg = await exportFn({
          elements: parsed.elements,
          appState: { ...parsed.appState, exportWithDarkMode: false },
        });

        // Serialize SVG to string
        const svgString = new XMLSerializer().serializeToString(svg);
        setSvgContent(svgString);
        setError(null);
      } catch (err) {
        console.error("Failed to render Excalidraw:", err);
        setError(t("documents.excalidrawRenderFailed"));
      } finally {
        setIsLoading(false);
      }
    };

    renderSvg();
  }, [data, parseData, t]);

  // Render SVG as blob URL for img tag
  const svgBlobUrl = useMemo(() => {
    if (!svgContent) return null;
    const blob = new Blob([svgContent], { type: "image/svg+xml" });
    return URL.createObjectURL(blob);
  }, [svgContent]);

  // Cleanup blob URL
  useEffect(() => {
    if (!svgBlobUrl) return;
    return () => URL.revokeObjectURL(svgBlobUrl);
  }, [svgBlobUrl]);

  // Error state
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
        <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-red-100 dark:bg-red-900/30">
          <AlertCircle size={28} className="text-red-500" />
        </div>
        <div className="text-center">
          <p className="text-sm text-red-600 dark:text-red-400 font-medium mb-2">
            {error}
          </p>
          <p className="text-xs text-stone-400 dark:text-stone-500">
            The file may be corrupted or in an unsupported format.
          </p>
        </div>
      </div>
    );
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-4 sm:p-8 bg-stone-50 dark:bg-stone-800/50 h-full overflow-auto">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <>
      {/* Render SVG as clickable image — matches image card pattern */}
      <div className="flex items-center justify-center p-4 sm:p-8 bg-stone-50 dark:bg-stone-800/50 h-full overflow-auto">
        {svgBlobUrl ? (
          <ImageWithSkeleton
            src={svgBlobUrl}
            alt={t("documents.excalidrawDiagram", "Excalidraw diagram")}
            skipUrlResolve
            inline
            className="rounded-lg shadow-lg max-w-full max-h-full"
            style={{ objectFit: "contain" }}
            onClick={() => setIsFullscreen(true)}
          />
        ) : (
          <p className="text-stone-400 dark:text-stone-500">
            {t("documents.noContent", "无内容")}
          </p>
        )}
      </div>

      {/* Fullscreen viewer */}
      {isFullscreen && svgContent && (
        <ExcalidrawFullscreenViewer
          svgContent={svgContent}
          onClose={() => setIsFullscreen(false)}
        />
      )}
    </>
  );
});

// Fullscreen viewer for excalidraw diagrams (matches ImageViewer pattern)
export function ExcalidrawFullscreenViewer({
  svgContent,
  onClose,
}: {
  svgContent: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [scale, setScale] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [imgLoading, setImgLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  const MIN_SCALE = 0.1;
  const MAX_SCALE = 20;
  const SCALE_STEP = 0.25;

  // Ref to read current position/scale inside native event listeners
  const gestureStateRef = useRef({ position: { x: 0, y: 0 }, scale: 1 });
  gestureStateRef.current = { position, scale };

  // Render SVG as <img> via blob URL for GPU-accelerated transforms
  const svgBlobUrl = useMemo(() => {
    const blob = new Blob([svgContent], { type: "image/svg+xml" });
    return URL.createObjectURL(blob);
  }, [svgContent]);

  useEffect(() => {
    return () => URL.revokeObjectURL(svgBlobUrl);
  }, [svgBlobUrl]);

  // Body scroll lock
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  // Escape to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Native non-passive wheel handler — matches ImageViewer
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleNativeWheel = (event: WheelEvent) => {
      event.preventDefault();
      const delta = event.deltaY > 0 ? -SCALE_STEP : SCALE_STEP;
      setScale((prev) =>
        Math.min(MAX_SCALE, Math.max(MIN_SCALE, prev + delta)),
      );
    };

    container.addEventListener("wheel", handleNativeWheel, { passive: false });
    return () => {
      container.removeEventListener("wheel", handleNativeWheel);
    };
  }, []);

  // Mouse drag to pan
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      setIsDragging(true);
      setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
    },
    [position],
  );

  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      setPosition({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
    };
    const handleMouseUp = () => setIsDragging(false);
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging, dragStart]);

  // Native non-passive touch listeners (pinch zoom + pan)
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let ts: { x: number; y: number } | null = null;
    let pinchDist: number | null = null;
    let pinchScale = 1;

    const onStart = (e: TouchEvent) => {
      if (e.touches.length === 1) {
        const touch = e.touches[0];
        const pos = gestureStateRef.current.position;
        ts = { x: touch.clientX - pos.x, y: touch.clientY - pos.y };
        setIsDragging(true);
      } else if (e.touches.length === 2) {
        setIsDragging(false);
        ts = null;
        pinchDist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY,
        );
        pinchScale = gestureStateRef.current.scale;
      }
    };

    const onMove = (e: TouchEvent) => {
      e.preventDefault();
      if (e.touches.length === 1 && ts) {
        const touch = e.touches[0];
        setPosition({
          x: touch.clientX - ts.x,
          y: touch.clientY - ts.y,
        });
      } else if (e.touches.length === 2 && pinchDist !== null) {
        const dist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY,
        );
        const sf = dist / pinchDist;
        setScale(() =>
          Math.min(MAX_SCALE, Math.max(MIN_SCALE, pinchScale * sf)),
        );
      }
    };

    const onEnd = () => {
      setIsDragging(false);
      ts = null;
      pinchDist = null;
    };

    container.addEventListener("touchstart", onStart, { passive: true });
    container.addEventListener("touchmove", onMove, { passive: false });
    container.addEventListener("touchend", onEnd, { passive: true });
    return () => {
      container.removeEventListener("touchstart", onStart);
      container.removeEventListener("touchmove", onMove);
      container.removeEventListener("touchend", onEnd);
    };
  }, []);

  // Download handlers for fullscreen top bar
  const handleDownloadSVG = () => {
    const blob = new Blob([svgContent], { type: "image/svg+xml" });
    downloadBlob(blob, "excalidraw-diagram.svg");
  };

  const handleDownloadPNG = async () => {
    try {
      const img = new Image();
      const svgBlob = new Blob([svgContent], { type: "image/svg+xml" });
      const url = URL.createObjectURL(svgBlob);

      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = reject;
        img.src = url;
      });

      const canvas = document.createElement("canvas");
      const renderScale = 2;
      canvas.width = img.width * renderScale;
      canvas.height = img.height * renderScale;
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.scale(renderScale, renderScale);
        ctx.drawImage(img, 0, 0);
      }

      canvas.toBlob((blob) => {
        if (blob) {
          downloadBlob(blob, "excalidraw-diagram.png");
        }
      }, "image/png");

      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to export PNG:", err);
    }
  };

  // Download dropdown state
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!showDownloadMenu) return;
    const handleClickOutside = () => setShowDownloadMenu(false);
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, [showDownloadMenu]);

  const handleBackgroundClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  return createPortal(
    <div
      data-yields-sidebar
      className="fixed inset-0 z-[300] flex flex-col bg-black/90"
      onClick={handleBackgroundClick}
    >
      {/* Top bar — matches ImageViewer pattern */}
      <ViewerTopBar>
        <ViewerTopBarButton
          onClick={onClose}
          aria-label={t("common.close")}
          icon={<X size={20} className="text-white/70" />}
          iconOnly
        />

        <div className="flex items-center gap-1 relative">
          {/* Download dropdown — matches ImageViewer download button style */}
          <ViewerTopBarButton
            onClick={(e) => {
              e.stopPropagation();
              setShowDownloadMenu(!showDownloadMenu);
            }}
            aria-label={t("documents.download")}
            icon={<Download size={18} className="text-white/70" />}
          >
            <span className="hidden sm:inline">{t("documents.download")}</span>
          </ViewerTopBarButton>
          {showDownloadMenu && (
            <div className="absolute right-0 top-full mt-1 z-50 min-w-[100px] rounded-lg border border-white/10 bg-black/80 shadow-lg overflow-hidden">
              <ViewerDropdownMenuItem
                variant="dark"
                onClick={(e) => {
                  e.stopPropagation();
                  handleDownloadSVG();
                  setShowDownloadMenu(false);
                }}
              >
                SVG
              </ViewerDropdownMenuItem>
              <ViewerDropdownMenuItem
                variant="dark"
                onClick={(e) => {
                  e.stopPropagation();
                  handleDownloadPNG();
                  setShowDownloadMenu(false);
                }}
              >
                PNG
              </ViewerDropdownMenuItem>
            </div>
          )}
        </div>
      </ViewerTopBar>

      {/* Main area */}
      <div ref={containerRef} className="flex-1 overflow-hidden relative">
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{
            cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "default",
          }}
          onMouseDown={handleMouseDown}
        >
          {!imgLoading && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="skeleton-line w-48 h-32 rounded-lg" />
            </div>
          )}
          <img
            src={svgBlobUrl}
            alt={t("documents.excalidrawDiagram", "Excalidraw diagram")}
            className="max-w-[90vw] max-h-[85dvh] object-contain select-none"
            style={{
              transform: `translate(${position.x}px, ${position.y}px) scale(${scale}) rotate(${rotation}deg)`,
              transition: isDragging ? "none" : "transform 0.1s ease-out",
              touchAction: "none",
              opacity: imgLoading ? 0 : 1,
            }}
            onLoad={() => setImgLoading(false)}
            draggable={false}
          />
        </div>

        {/* Floating bottom controls — shared ViewerToolbar */}
        <ViewerToolbar
          scale={scale}
          minScale={MIN_SCALE}
          maxScale={MAX_SCALE}
          onZoomIn={() =>
            setScale((prev) => Math.min(MAX_SCALE, prev + SCALE_STEP))
          }
          onZoomOut={() =>
            setScale((prev) => Math.max(MIN_SCALE, prev - SCALE_STEP))
          }
          onRotateLeft={() => setRotation((prev) => prev - 90)}
          onRotateRight={() => setRotation((prev) => prev + 90)}
          onReset={() => {
            setScale(1);
            setRotation(0);
            setPosition({ x: 0, y: 0 });
          }}
        />
      </div>
    </div>,
    document.body,
  );
}

export default ExcalidrawPreview;
