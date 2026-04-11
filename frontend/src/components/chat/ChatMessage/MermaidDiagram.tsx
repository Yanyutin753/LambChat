import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, Download } from "lucide-react";
import { useTranslation } from "react-i18next";

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

        // Clear previous content
        setSvg("");
        setError(null);

        // Validate mermaid syntax before rendering
        await mermaid.default.parse(chart);

        // Render the diagram
        const { svg } = await mermaid.default.render(idRef.current, chart);

        // Fix SVG: remove width="100%" which causes display issues
        // Keep the original width/height values from mermaid to preserve text rendering
        const processedSvg = svg.replace(/\swidth="100%"/g, "");

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
        // Don't set svg on error
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
    if (!svg || !ref.current) return;

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
    // When mermaid fails, show code block instead of error box to not affect page rendering
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
  );
}
