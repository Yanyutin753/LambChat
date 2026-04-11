import { memo, useEffect, useState, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import {
  AlertCircle,
  Download,
  ZoomIn,
  ZoomOut,
  Maximize2,
} from "lucide-react";

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
  const [scale, setScale] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);

  // Touch zoom state
  const [touchStart, setTouchStart] = useState<{
    x: number;
    y: number;
    distance: number;
  } | null>(null);

  // Drag to pan state
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [translate, setTranslate] = useState({ x: 0, y: 0 });

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
      setError("Invalid Excalidraw file format");
      setIsLoading(false);
      return;
    }

    const renderSvg = async () => {
      try {
        // Load exportToSvg function once
        if (!exportToSvgFunc) {
          const mod = await import("@excalidraw/excalidraw");
          exportToSvgFunc = mod.exportToSvg;
        }

        // Use local reference to satisfy TypeScript
        const exportFn = exportToSvgFunc;
        if (!exportFn) {
          throw new Error("Failed to load export function");
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
        setError("Failed to render Excalidraw diagram");
      } finally {
        setIsLoading(false);
      }
    };

    renderSvg();
  }, [data, parseData]);

  // Wheel zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    setScale((prev) => Math.min(Math.max(prev + delta, 0.1), 5));
  }, []);

  // Touch zoom handlers
  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        setTouchStart({
          x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
          y: (e.touches[0].clientY + e.touches[1].clientY) / 2,
          distance: Math.sqrt(dx * dx + dy * dy),
        });
      } else if (e.touches.length === 1) {
        // Single touch for panning
        setIsDragging(true);
        setDragStart({
          x: e.touches[0].clientX - translate.x,
          y: e.touches[0].clientY - translate.y,
        });
      }
    },
    [translate],
  );

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (e.touches.length === 2 && touchStart) {
        e.preventDefault();
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const delta = (distance - touchStart.distance) / 200;
        setScale((prev) => Math.min(Math.max(prev + delta, 0.1), 5));
        setTouchStart({ ...touchStart, distance });
      } else if (e.touches.length === 1 && isDragging) {
        e.preventDefault();
        setTranslate({
          x: e.touches[0].clientX - dragStart.x,
          y: e.touches[0].clientY - dragStart.y,
        });
      }
    },
    [touchStart, isDragging, dragStart],
  );

  const handleTouchEnd = useCallback(() => {
    setTouchStart(null);
    setIsDragging(false);
  }, []);

  // Mouse drag handlers
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

  // Zoom controls
  const handleZoomIn = useCallback(() => {
    setScale((s) => Math.min(s * 1.25, 5));
  }, []);

  const handleZoomOut = useCallback(() => {
    setScale((s) => Math.max(s / 1.25, 0.1));
  }, []);

  const handleFitToScreen = useCallback(() => {
    if (containerRef.current) {
      const container = containerRef.current;
      const svgElement = container.querySelector("svg");
      if (svgElement) {
        const containerWidth = container.clientWidth;
        const containerHeight = container.clientHeight;
        const svgWidth = svgElement.getBoundingClientRect().width;
        const svgHeight = svgElement.getBoundingClientRect().height;

        const scaleX = containerWidth / svgWidth;
        const scaleY = containerHeight / svgHeight;
        const fitScale = Math.min(scaleX, scaleY, 1);

        setScale(fitScale);
        setTranslate({ x: 0, y: 0 });
      }
    }
  }, []);

  // Download handlers
  const handleDownloadSVG = useCallback(() => {
    if (!svgContent) return;

    const blob = new Blob([svgContent], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "excalidraw-diagram.svg";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [svgContent]);

  const handleDownloadPNG = useCallback(async () => {
    if (!svgContent) return;

    try {
      // Create image from SVG
      const img = new Image();
      const svgBlob = new Blob([svgContent], { type: "image/svg+xml" });
      const url = URL.createObjectURL(svgBlob);

      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = reject;
        img.src = url;
      });

      // Draw to canvas
      const canvas = document.createElement("canvas");
      const renderScale = 2; // Higher resolution
      canvas.width = img.width * renderScale;
      canvas.height = img.height * renderScale;
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.scale(renderScale, renderScale);
        ctx.drawImage(img, 0, 0);
      }

      // Download
      canvas.toBlob((blob) => {
        if (blob) {
          const pngUrl = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = pngUrl;
          a.download = "excalidraw-diagram.png";
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(pngUrl);
        }
      }, "image/png");

      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to export PNG:", err);
    }
  }, [svgContent]);

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
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <LoadingSpinner size="lg" />
        <p className="text-sm text-stone-500 dark:text-stone-400">
          Loading diagram...
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-stone-200 dark:border-stone-700 bg-stone-50 dark:bg-stone-800/50 shrink-0">
        {/* Zoom controls */}
        <button
          onClick={handleZoomOut}
          className="flex items-center justify-center w-8 h-8 rounded-lg bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 text-stone-600 dark:text-stone-300 transition-colors"
          title={t("documents.zoomOut")}
        >
          <ZoomOut size={16} />
        </button>

        <span className="text-xs text-stone-500 dark:text-stone-400 min-w-[50px] text-center">
          {Math.round(scale * 100)}%
        </span>

        <button
          onClick={handleZoomIn}
          className="flex items-center justify-center w-8 h-8 rounded-lg bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 text-stone-600 dark:text-stone-300 transition-colors"
          title={t("documents.zoomIn")}
        >
          <ZoomIn size={16} />
        </button>

        <button
          onClick={handleFitToScreen}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 text-xs font-medium text-stone-600 dark:text-stone-300 transition-colors"
          title={t("documents.fitToScreen")}
        >
          <Maximize2 size={14} />
          <span className="hidden sm:inline">Fit</span>
        </button>

        <div className="h-4 w-px bg-stone-200 dark:bg-stone-700" />

        {/* Download buttons */}
        <button
          onClick={handleDownloadSVG}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 text-xs font-medium text-stone-600 dark:text-stone-300 transition-colors"
          title={`${t("documents.download")} SVG`}
        >
          <Download size={14} />
          <span className="hidden sm:inline">SVG</span>
        </button>

        <button
          onClick={handleDownloadPNG}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 text-xs font-medium text-stone-600 dark:text-stone-300 transition-colors"
          title={`${t("documents.download")} PNG`}
        >
          <Download size={14} />
          <span className="hidden sm:inline">PNG</span>
        </button>
      </div>

      {/* SVG Container with touch and drag support */}
      <div
        ref={containerRef}
        className={`flex-1 overflow-hidden bg-white dark:bg-stone-900 flex items-center justify-center ${
          isDragging ? "cursor-grabbing" : "cursor-grab"
        }`}
        onWheel={handleWheel}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
      >
        {svgContent ? (
          <div
            style={{
              transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
              transformOrigin: "center center",
              transition: isDragging ? "none" : "transform 0.2s ease-out",
            }}
            dangerouslySetInnerHTML={{ __html: svgContent }}
          />
        ) : (
          <p className="text-stone-400 dark:text-stone-500">No content</p>
        )}
      </div>
    </div>
  );
});

export default ExcalidrawPreview;
