import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Copy, Download, Code, Eye, X, Maximize2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  prepareFullscreenMermaidSvg,
  stripResponsiveWidthAttribute,
} from "./mermaidSvgUtils";
import { ViewerToolbar } from "../../common/ViewerToolbar";

// Fix common AI-generated mermaid syntax issues:
// - subgraph 🎯 ["title"] → subgraph S1["🎯 title"]
// - subgraph emoji ["title"] → subgraph S<N>["emoji title"]
function normalizeMermaidChart(chart: string): string {
  let subgraphId = 0;
  return chart.replace(
    /^(\s*)(subgraph)\s+([^\s[]+)(\s+\[.*?\])?$/gm,
    (_match, indent, _keyword, id, titlePart) => {
      // If the ID is a valid identifier (starts with letter/_, no emoji), keep it
      if (/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(id)) {
        return `${indent}subgraph ${id}${titlePart || ""}`;
      }
      // Otherwise, replace with a generated ID and merge emoji into the title
      subgraphId++;
      const emoji = id;
      const title = titlePart
        ? titlePart.replace(/^\s*\["?/, "").replace(/"?\]\s*$/, "")
        : emoji;
      return `${indent}subgraph S${subgraphId}["${emoji} ${title}"]`;
    },
  );
}

// Mermaid diagram component with actions
export function MermaidDiagram({
  chart,
  isStreaming,
}: {
  chart: string;
  isStreaming?: boolean;
}) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [scale, setScale] = useState(1);
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showCode, setShowCode] = useState(false);
  const idRef = useRef<string>(
    `mermaid-${Math.random().toString(36).slice(2)}-${Date.now()}`,
  );

  // Only render diagram when not streaming
  const shouldRenderDiagram = !isStreaming && chart.trim().length > 0;

  // Handle wheel zoom - let browser handle scroll, just update scale
  const handleWheel = useCallback((e: React.WheelEvent) => {
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
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
      if (e.button !== 0) return; // Only left click
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
    // Don't render during streaming
    if (!shouldRenderDiagram) {
      setSvg("");
      setError(null);
      return;
    }

    const renderDiagram = async () => {
      if (!chart.trim()) return;

      try {
        const mermaid = await import("mermaid");

        // Initialize mermaid
        mermaid.default.initialize({
          startOnLoad: false,
          theme: "default",
          securityLevel: "strict",
        });

        // Normalize chart to fix common AI-generated syntax issues
        const normalizedChart = normalizeMermaidChart(chart);

        // Clear previous content
        setSvg("");
        setError(null);

        // Validate mermaid syntax before rendering
        await mermaid.default.parse(normalizedChart);

        // Render the diagram
        const { svg } = await mermaid.default.render(
          idRef.current,
          normalizedChart,
        );

        // Fix SVG: remove width="100%" which causes display issues
        const processedSvg = stripResponsiveWidthAttribute(svg);

        // Check if the SVG contains error indicators
        if (
          processedSvg.includes('class="error-icon"') ||
          processedSvg.includes("Syntax error in text")
        ) {
          throw new Error(t("chat.message.mermaidError"));
        }

        setSvg(processedSvg);
      } catch (err) {
        console.error("Mermaid render error:", err);
        const errorMessage =
          err instanceof Error ? err.message : "Failed to render diagram";
        setError(errorMessage);
        setSvg("");
      }
    };

    renderDiagram();
  }, [chart, t, shouldRenderDiagram]);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!showDownloadMenu) return;

    const handleClickOutside = () => setShowDownloadMenu(false);
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, [showDownloadMenu]);

  const handleCopyCode = async () => {
    await navigator.clipboard.writeText(chart);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadSVG = () => {
    if (!svg) return;

    const blob = new Blob([svg], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "diagram.svg";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getSvgDimensions = (
    svgString: string,
  ): { width: number; height: number } => {
    const parser = new DOMParser();
    const doc = parser.parseFromString(svgString, "image/svg+xml");
    const svgEl = doc.querySelector("svg");
    if (!svgEl) return { width: 800, height: 600 };

    let width = parseFloat(svgEl.getAttribute("width") || "0");
    let height = parseFloat(svgEl.getAttribute("height") || "0");

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

    if (!width || !height) {
      width = 800;
      height = 600;
    }

    return { width, height };
  };

  const handleDownloadPNG = () => {
    if (!svg || !ref.current) return;

    const { width, height } = getSvgDimensions(svg);
    const pngScale = 2;

    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = width * pngScale;
    canvas.height = height * pngScale;

    const img = new Image();
    const svgBase64 = btoa(unescape(encodeURIComponent(svg)));

    img.onload = () => {
      ctx.scale(pngScale, pngScale);
      ctx.fillStyle = document.documentElement.classList.contains("dark")
        ? "#1c1917"
        : "#ffffff";
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(img, 0, 0, width, height);

      canvas.toBlob((blob) => {
        if (!blob) return;
        const pngUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = pngUrl;
        a.download = "diagram.png";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(pngUrl);
      }, "image/png");
    };

    img.onerror = () => {
      console.error("Failed to load SVG for PNG export");
    };

    img.src = `data:image/svg+xml;base64,${svgBase64}`;
  };

  // During streaming, show code block instead
  if (isStreaming) {
    return (
      <div className="my-2 sm:my-3 max-w-full overflow-hidden rounded-xl border border-stone-200 dark:border-stone-700">
        <div className="flex items-center justify-between px-3 sm:px-4 py-2 bg-stone-200/70 dark:bg-stone-800/50">
          <span className="text-xs font-medium text-stone-500 dark:text-stone-400">
            mermaid
          </span>
          <button
            onClick={handleCopyCode}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all min-h-[32px] min-w-[32px] touch-manipulation"
          >
            {copied ? (
              <>
                <Check
                  size={14}
                  className="text-green-600 dark:text-green-400"
                />
                <span className="text-green-600 dark:text-green-400">
                  {t("chat.message.copied")}
                </span>
              </>
            ) : (
              <>
                <Copy
                  size={14}
                  className="text-stone-500 dark:text-stone-400"
                />
                <span className="text-stone-500 dark:text-stone-400">
                  {t("chat.message.copy")}
                </span>
              </>
            )}
          </button>
        </div>
        <pre className="p-3 bg-stone-50 dark:bg-stone-800 overflow-x-auto max-h-64 overflow-y-auto text-xs text-stone-700 dark:text-stone-300 font-mono">
          {chart}
        </pre>
      </div>
    );
  }

  if (error) {
    return (
      <div className="my-2 sm:my-3 max-w-full overflow-hidden rounded-xl border border-stone-200 dark:border-stone-700">
        <div className="flex items-center justify-between px-3 sm:px-4 py-2 bg-stone-200/70 dark:bg-stone-800/50">
          <span className="text-xs font-medium text-stone-500 dark:text-stone-400">
            mermaid
          </span>
          <button
            onClick={handleCopyCode}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all min-h-[32px] min-w-[32px] touch-manipulation"
          >
            {copied ? (
              <>
                <Check
                  size={14}
                  className="text-green-600 dark:text-green-400"
                />
                <span className="text-green-600 dark:text-green-400">
                  {t("chat.message.copied")}
                </span>
              </>
            ) : (
              <>
                <Copy size={14} />
                <span>{t("chat.message.copyCode")}</span>
              </>
            )}
          </button>
        </div>
        <pre className="p-3 bg-stone-50 dark:bg-stone-800 overflow-x-auto max-h-64 overflow-y-auto text-xs text-stone-700 dark:text-stone-300 font-mono">
          {chart}
        </pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="mermaid-diagram overflow-x-auto rounded-lg bg-stone-50 p-4 dark:bg-stone-800">
        <div className="text-sm text-stone-500 dark:text-stone-400">
          Loading diagram...
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="my-2 sm:my-3 max-w-full overflow-hidden rounded-xl border border-stone-200 dark:border-stone-700">
        {/* Header bar with action buttons */}
        <div className="flex items-center justify-between px-3 sm:px-4 py-2 bg-stone-200/70 dark:bg-stone-800/50">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-xs font-medium text-stone-500 dark:text-stone-400">
              mermaid
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={handleCopyCode}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all min-h-[32px] min-w-[32px] touch-manipulation"
              title={
                copied ? t("chat.message.copied") : t("chat.message.copyCode")
              }
            >
              {copied ? (
                <>
                  <Check
                    size={14}
                    className="text-green-600 dark:text-green-400"
                  />
                  <span className="hidden xs:inline text-green-600 dark:text-green-400">
                    {t("chat.message.copied")}
                  </span>
                </>
              ) : (
                <>
                  <Copy
                    size={14}
                    className="text-stone-500 dark:text-stone-400"
                  />
                  <span className="hidden xs:inline text-stone-500 dark:text-stone-400">
                    {t("chat.message.copy")}
                  </span>
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
                className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all hover:bg-stone-300/50 dark:hover:bg-stone-700/50 min-h-[32px] min-w-[32px] touch-manipulation"
                title={t("documents.download")}
              >
                <Download
                  size={14}
                  className="text-stone-500 dark:text-stone-400"
                />
              </button>
              {showDownloadMenu && (
                <div className="absolute right-0 top-full mt-1 z-50 min-w-[100px] rounded-lg border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800 shadow-lg overflow-hidden">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDownloadSVG();
                      setShowDownloadMenu(false);
                    }}
                    className="w-full px-3 py-2 text-left text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-700 flex items-center gap-2"
                  >
                    SVG
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDownloadPNG();
                      setShowDownloadMenu(false);
                    }}
                    className="w-full px-3 py-2 text-left text-xs text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-700 flex items-center gap-2"
                  >
                    PNG
                  </button>
                </div>
              )}
            </div>
            {/* Preview code button */}
            <button
              onClick={() => {
                setShowCode(true);
                setIsFullscreen(true);
              }}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all hover:bg-stone-300/50 dark:hover:bg-stone-700/50 min-h-[32px] min-w-[32px] touch-manipulation"
              title={t("mermaidViewer.showCode")}
            >
              <Code size={14} className="text-stone-500 dark:text-stone-400" />
              <span className="hidden xs:inline text-stone-500 dark:text-stone-400">
                {t("mermaidViewer.showCode")}
              </span>
            </button>
            {/* Fullscreen button */}
            <button
              onClick={() => setIsFullscreen(true)}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all hover:bg-stone-300/50 dark:hover:bg-stone-700/50 min-h-[32px] min-w-[32px] touch-manipulation"
              title={t("imageViewer.fullscreen", "Fullscreen")}
            >
              <Maximize2
                size={14}
                className="text-stone-500 dark:text-stone-400"
              />
            </button>
          </div>
        </div>

        {/* Diagram container - centered with zoom and drag */}
        <div
          className={`mermaid-diagram overflow-hidden p-4 bg-stone-50 dark:bg-stone-800 flex items-center justify-center min-h-[200px] max-h-[500px] cursor-${
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
            ref={ref}
            style={{
              transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
              transformOrigin: "center center",
              transition: isDragging ? "none" : "transform 0.2s ease-out",
            }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        </div>
      </div>

      {/* Fullscreen Mermaid Viewer */}
      {isFullscreen && (
        <MermaidViewer
          svg={svg}
          chart={chart}
          onClose={() => {
            setIsFullscreen(false);
            setShowCode(false);
          }}
          initialShowCode={showCode}
          onToggleCode={setShowCode}
        />
      )}
    </>
  );
}

// Fullscreen viewer for mermaid diagrams (similar to ImageViewer)
function MermaidViewer({
  svg,
  chart,
  onClose,
  initialShowCode,
  onToggleCode,
}: {
  svg: string;
  chart: string;
  onClose: () => void;
  initialShowCode: boolean;
  onToggleCode: (show: boolean) => void;
}) {
  const { t } = useTranslation();
  const [scale, setScale] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [showCode, setShowCode] = useState(initialShowCode);
  const [copied, setCopied] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const MIN_SCALE = 0.1;
  const MAX_SCALE = 20;
  const SCALE_STEP = 0.25;

  // Ref to read current position/scale inside native event listeners
  const gestureStateRef = useRef({ position: { x: 0, y: 0 }, scale: 1 });
  gestureStateRef.current = { position, scale };

  const fullscreenSvg = useMemo(() => prepareFullscreenMermaidSvg(svg), [svg]);

  // Render SVG as <img> via blob URL for GPU-accelerated transforms (same as ImageViewer)
  const svgBlobUrl = useMemo(() => {
    const blob = new Blob([fullscreenSvg], { type: "image/svg+xml" });
    return URL.createObjectURL(blob);
  }, [fullscreenSvg]);

  useEffect(() => {
    return () => URL.revokeObjectURL(svgBlobUrl);
  }, [svgBlobUrl]);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -SCALE_STEP : SCALE_STEP;
    setScale((prev) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, prev + delta)));
  }, []);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      setIsDragging(true);
      setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
    },
    [position],
  );

  // Native non-passive touch listeners (React onTouchMove is passive, preventDefault is ignored)
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

  const handleCopyCode = async () => {
    await navigator.clipboard.writeText(chart);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const toggleCode = () => {
    const next = !showCode;
    setShowCode(next);
    onToggleCode(next);
  };

  const btnCls =
    "flex items-center justify-center w-10 h-10 rounded-lg hover:bg-white/10 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed";

  return createPortal(
    <div
      data-yields-sidebar
      className="fixed inset-0 z-[300] flex flex-col bg-black/90"
    >
      {/* Top bar - close + code actions */}
      <div className="flex items-center justify-between px-3 sm:px-6 py-3 bg-black">
        <button
          type="button"
          onClick={onClose}
          className={btnCls}
          aria-label={t("common.close")}
        >
          <X size={20} className="text-white/70" />
        </button>

        <div className="flex items-center gap-1">
          {/* Toggle code view */}
          <button
            type="button"
            onClick={toggleCode}
            className={`flex items-center gap-1.5 rounded-lg px-3 h-10 text-sm font-medium transition-colors cursor-pointer ${
              showCode
                ? "bg-white/20 text-white/70"
                : "hover:bg-white/10 text-white/70"
            }`}
            aria-label={
              showCode
                ? t("mermaidViewer.hideCode", "Hide code")
                : t("mermaidViewer.showCode", "Show code")
            }
          >
            {showCode ? (
              <Eye size={18} className="text-white/70" />
            ) : (
              <Code size={18} className="text-white/70" />
            )}
            <span className="hidden sm:inline">
              {showCode
                ? t("mermaidViewer.hideCode", "Hide code")
                : t("mermaidViewer.showCode", "Show code")}
            </span>
          </button>

          {/* Copy code */}
          <button
            type="button"
            onClick={handleCopyCode}
            className="flex items-center gap-1 rounded-lg px-3 h-10 text-sm font-medium transition-colors cursor-pointer hover:bg-white/10"
            aria-label={t("chat.message.copyCode")}
          >
            {copied ? (
              <>
                <Check size={18} className="text-green-400" />
                <span className="text-green-400 hidden sm:inline">
                  {t("chat.message.copied")}
                </span>
              </>
            ) : (
              <>
                <Copy size={18} className="text-white/70" />
                <span className="text-white/70 hidden sm:inline">
                  {t("chat.message.copy")}
                </span>
              </>
            )}
          </button>

          {/* Download SVG */}
          <button
            type="button"
            onClick={() => {
              const blob = new Blob([fullscreenSvg], { type: "image/svg+xml" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = "mermaid.svg";
              a.click();
              URL.revokeObjectURL(url);
            }}
            className="flex items-center gap-1.5 rounded-lg px-3 h-10 text-sm font-medium transition-colors cursor-pointer hover:bg-white/10 text-white/70"
            aria-label={t("imageViewer.download")}
          >
            <Download size={18} className="text-white/70" />
            <span className="hidden sm:inline">
              {t("imageViewer.download")}
            </span>
          </button>
        </div>
      </div>

      {/* Main area */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* SVG diagram */}
        <div
          ref={containerRef}
          className={`flex-1 overflow-hidden relative ${
            showCode ? "hidden sm:flex" : "flex"
          }`}
          style={{ touchAction: "none" }}
          onWheel={handleWheel}
        >
          <div
            className="absolute inset-0 flex items-center justify-center"
            style={{
              cursor:
                scale > 1 ? (isDragging ? "grabbing" : "grab") : "default",
            }}
            onMouseDown={handleMouseDown}
          >
            <img
              src={svgBlobUrl}
              alt="mermaid diagram"
              className="max-w-[90vw] max-h-[85vh] object-contain select-none"
              style={{
                transform: `translate(${position.x}px, ${position.y}px) scale(${scale}) rotate(${rotation}deg)`,
                transition: isDragging ? "none" : "transform 0.1s ease-out",
                touchAction: "none",
              }}
              draggable={false}
            />
          </div>

          {/* Floating bottom controls */}
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

        {/* Code panel */}
        {showCode && (
          <div className="w-full sm:w-[480px] border-l border-white/10 bg-stone-900 flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 border-b border-white/10">
              <span className="text-xs font-medium text-white/50">mermaid</span>
            </div>
            <pre className="flex-1 overflow-auto p-4 text-sm text-stone-300 font-mono whitespace-pre-wrap break-words">
              {chart}
            </pre>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
