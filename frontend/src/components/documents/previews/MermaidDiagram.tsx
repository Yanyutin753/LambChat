import { memo, useEffect, useRef, useState, useCallback } from "react";
import { Copy, Check, Download, ChevronDown } from "lucide-react";
import { ViewerDropdownMenuItem } from "../../common";
import { downloadBlob } from "../../common/viewerDownload";
import { copyToClipboard } from "../../../utils/clipboard";
import { themeExportBackground } from "../../../utils/themeDom";
import { useAppThemeMode } from "../../../hooks/useAppThemeMode";

interface MermaidDiagramProps {
  code: string;
  t: (key: string, options?: Record<string, unknown>) => string;
}

// Mermaid diagram component with actions
const MermaidDiagram = memo(function MermaidDiagram({
  code,
  t,
}: MermaidDiagramProps) {
  const themeMode = useAppThemeMode();
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [scale, setScale] = useState(1);
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleWheel = useCallback((event: React.WheelEvent) => {
    if (!event.ctrlKey && !event.metaKey) return;

    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.1 : 0.1;
    setScale((prev) => Math.min(Math.max(prev + delta, 0.5), 3));
  }, []);

  // Handle touch zoom
  const [touchStart, setTouchStart] = useState<{
    x: number;
    y: number;
    distance: number;
  } | null>(null);

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
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [translate, setTranslate] = useState({ x: 0, y: 0 });

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

  useEffect(() => {
    const renderDiagram = async () => {
      try {
        const mermaid = await import("mermaid");
        // Initialize mermaid — follow the active theme; sepia keeps the light
        // palette but repaints the canvas onto the beige card background
        const isSepia = themeMode === "sepia";
        mermaid.default.initialize({
          startOnLoad: false,
          theme: themeMode === "dark" ? "dark" : "default",
          ...(isSepia
            ? { themeVariables: { background: "#faf6ea" } }
            : {}),
          securityLevel: "strict",
          flowchart: {
            useMaxWidth: true,
            htmlLabels: true,
          },
        });

        const { svg } = await mermaid.default.render(
          `mermaid-${Date.now()}`,
          code,
        );
        setSvg(svg);
        setError(null);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : t("documents.mermaidRenderFailed"),
        );
      }
    };
    renderDiagram();
  }, [code, t, themeMode]);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!showDownloadMenu) return;

    const handleClickOutside = () => setShowDownloadMenu(false);
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, [showDownloadMenu]);

  const handleCopyCode = async () => {
    await copyToClipboard(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadSVG = () => {
    if (!svg) return;

    const blob = new Blob([svg], { type: "image/svg+xml" });
    downloadBlob(blob, "diagram.svg");
  };

  // Helper function to extract dimensions from SVG
  const getSvgDimensions = (
    svgString: string,
  ): { width: number; height: number } => {
    const parser = new DOMParser();
    const doc = parser.parseFromString(svgString, "image/svg+xml");
    const svgEl = doc.querySelector("svg");
    if (!svgEl) return { width: 800, height: 600 };

    // Try to get width and height attributes
    let width = parseFloat(svgEl.getAttribute("width") || "0");
    let height = parseFloat(svgEl.getAttribute("height") || "0");

    // If not present, try viewBox
    if (!width || !height) {
      const viewBox = svgEl.getAttribute("viewBox");
      if (viewBox) {
        const parts = viewBox.split(/\s+/);
        if (parts.length === 4) {
          width = parseFloat(parts[2]);
          height = parseFloat(parts[3]);
        }
      }
    }

    // Fallback
    if (!width || !height) {
      width = 800;
      height = 600;
    }

    return { width, height };
  };

  const handleDownloadPNG = () => {
    if (!svg || !containerRef.current) return;

    const { width, height } = getSvgDimensions(svg);
    const scale = 2; // Higher resolution

    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Set canvas size with higher resolution
    canvas.width = width * scale;
    canvas.height = height * scale;

    const img = new Image();
    // Use base64 data URL to avoid tainted canvas
    const svgBase64 = btoa(unescape(encodeURIComponent(svg)));

    img.onload = () => {
      ctx.scale(scale, scale);
      ctx.fillStyle = themeExportBackground(themeMode);
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(img, 0, 0, width, height);

      canvas.toBlob((blob) => {
        if (!blob) return;
        downloadBlob(blob, "diagram.png");
      }, "image/png");
    };

    img.onerror = () => {
      console.error("Failed to load SVG for PNG export");
    };

    img.src = `data:image/svg+xml;base64,${svgBase64}`;
  };

  if (error) {
    return (
      <div className="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
        <p className="text-sm text-red-600 dark:text-red-400 font-medium mb-2">
          Mermaid Error
        </p>
        <pre className="mt-2 text-xs text-red-500 dark:text-red-300 overflow-auto">
          {error}
        </pre>
      </div>
    );
  }

  return (
    <div className="my-4">
      {/* Action buttons */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <button
          onClick={handleCopyCode}
          className="flex shrink-0 items-center gap-1 whitespace-nowrap px-3 py-1.5 rounded-lg bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 text-xs font-medium text-stone-600 dark:text-stone-300 transition-colors"
        >
          {copied ? (
            <>
              <Check size={14} className="text-green-500" />
              <span className="text-green-500">{t("documents.copied")}</span>
            </>
          ) : (
            <>
              <Copy size={14} />
              <span>{t("documents.copyCode")}</span>
            </>
          )}
        </button>
        {/* Download dropdown */}
        <div className="relative">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowDownloadMenu(!showDownloadMenu);
            }}
            className="flex shrink-0 items-center gap-1 whitespace-nowrap px-3 py-1.5 rounded-lg bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 text-xs font-medium text-stone-600 dark:text-stone-300 transition-colors"
          >
            <Download size={14} />
            <span>{t("documents.download")}</span>
            <ChevronDown size={12} />
          </button>
          {showDownloadMenu && (
            <div className="absolute left-0 top-full mt-1 z-50 min-w-[100px] rounded-lg border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800 shadow-lg overflow-hidden">
              <ViewerDropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation();
                  handleDownloadSVG();
                  setShowDownloadMenu(false);
                }}
              >
                SVG
              </ViewerDropdownMenuItem>
              <ViewerDropdownMenuItem
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
      </div>

      {/* Diagram container - centered with zoom and drag */}
      <div
        className={`mermaid-diagram flex items-center justify-center p-4 bg-white dark:bg-stone-800 rounded-lg overflow-hidden min-h-[200px] cursor-${
          isDragging ? "grabbing" : "grab"
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
        <div
          ref={containerRef}
          style={{
            transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
            transformOrigin: "center center",
            transition: isDragging ? "none" : "transform 0.2s ease-out",
          }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </div>
  );
});

export default MermaidDiagram;
