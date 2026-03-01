import { clsx } from "clsx";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import {
  oneLight,
  oneDark,
} from "react-syntax-highlighter/dist/esm/styles/prism";
import { useCallback, useEffect, useRef, useState, memo } from "react";
import toast from "react-hot-toast";
import mermaid from "mermaid";
import { LoadingSpinner, CollapsiblePill, AttachmentCard } from "../common";
import type { CollapsibleStatus } from "../common";
import {
  Bot,
  Wrench,
  CheckCircle,
  XCircle,
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  Brain,
  Users,
  Download,
  FileText,
  ExternalLink,
  FileCode,
  Image as ImageIcon,
  Box,
  Info,
} from "lucide-react";
import type {
  Message,
  MessagePart,
  ToolCall,
  ToolResult,
  TokenUsagePart,
  MessageAttachment,
} from "../../types";
import { useTranslation } from "react-i18next";
import DocumentPreview from "../documents/DocumentPreview";
import { ImageViewer } from "../common/ImageViewer";
import { getFullUrl } from "../../services/api";

// Initialize mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: "default",
  securityLevel: "loose",
});

// 骨架屏样式的加载动画组件 - 精致细线条
function ThinkingIndicator() {
  return (
    <div className="space-y-2.5 py-1">
      {/* 第一行 - 长条 */}
      <div className="skeleton-line w-full h-2 rounded-sm" />

      {/* 第二行 - 三个中条 */}
      <div className="flex gap-4">
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
      </div>

      {/* 第三行 - 三个中条 */}
      <div className="flex gap-4">
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
      </div>

      {/* 第四行 */}
      <div className="flex gap-4">
        <div className="skeleton-line flex-1 h-2 rounded-sm" />
        <div className="skeleton-line w-2/5 h-2 rounded-sm" />
      </div>
    </div>
  );
}

interface ChatMessageProps {
  message: Message;
  onStop?: () => void;
}

// Mermaid diagram component with actions
function MermaidDiagram({
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
        // Clear previous content
        setSvg("");
        setError(null);

        // Validate mermaid syntax before rendering
        await mermaid.parse(chart);

        // Render the diagram
        const { svg } = await mermaid.render(idRef.current, chart);

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
        <pre className="p-3 bg-gray-50 dark:bg-stone-800 overflow-x-auto text-xs text-stone-700 dark:text-stone-300 font-mono">
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
        <pre className="p-3 bg-gray-50 dark:bg-stone-800 overflow-x-auto text-xs text-stone-700 dark:text-stone-300 font-mono">
          {chart}
        </pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="mermaid-diagram overflow-x-auto rounded-lg bg-gray-50 p-4 dark:bg-stone-800">
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
              title="Download"
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
        className={`mermaid-diagram overflow-hidden p-4 bg-gray-50 dark:bg-stone-800 flex items-center justify-center min-h-[200px] cursor-${
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

// Token 使用统计按钮组件 - 类 ChatGPT 风格
function TokenDetailsButton({
  tokenUsage,
  duration,
}: {
  tokenUsage?: TokenUsagePart;
  duration?: number;
}) {
  const { t } = useTranslation();
  const [showDetails, setShowDetails] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // 点击外部关闭详情
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setShowDetails(false);
      }
    };
    if (showDetails) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showDetails]);

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        onClick={() => setShowDetails(!showDetails)}
        className={clsx(
          "p-1.5 rounded-md transition-all",
          "opacity-0 group-hover:opacity-100",
          "hover:bg-gray-200 dark:hover:bg-stone-700",
          "text-gray-400 dark:text-stone-500 hover:text-gray-600 dark:hover:text-stone-300",
        )}
        title="Token usage"
      >
        <Info size={14} />
      </button>
      {/* ChatGPT 风格的详情弹窗 */}
      {showDetails && (
        <div
          className={clsx(
            "absolute bottom-full mb-2 left-0 z-50",
            "min-w-[150px] w-auto p-3 rounded-lg shadow-lg",
            "bg-white dark:bg-stone-800",
            "border border-gray-200 dark:border-stone-700",
            "whitespace-nowrap",
          )}
        >
          <div className="text-xs space-y-1.5">
            {tokenUsage && (
              <>
                <div className="flex justify-between gap-4">
                  <span className="text-gray-500 dark:text-stone-400">
                    {t("chat.message.tokenInput")}
                  </span>
                  <span className="text-gray-700 dark:text-stone-200 font-medium">
                    {tokenUsage.input_tokens?.toLocaleString()} tokens
                  </span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="text-gray-500 dark:text-stone-400">
                    {t("chat.message.tokenOutput")}
                  </span>
                  <span className="text-gray-700 dark:text-stone-200 font-medium">
                    {tokenUsage.output_tokens?.toLocaleString()} tokens
                  </span>
                </div>
                <div className="flex justify-between gap-4 border-t border-gray-100 dark:border-stone-700 pt-1.5 mt-1.5">
                  <span className="text-gray-500 dark:text-stone-400">
                    {t("chat.message.tokenTotal")}
                  </span>
                  <span className="text-gray-700 dark:text-stone-200 font-medium">
                    {tokenUsage.total_tokens?.toLocaleString()} tokens
                  </span>
                </div>
              </>
            )}
            {duration && (
              <div className="flex justify-between gap-4 border-t border-gray-100 dark:border-stone-700 pt-1.5 mt-1.5">
                <span className="text-gray-500 dark:text-stone-400">
                  {t("chat.message.duration")}
                </span>
                <span className="text-gray-700 dark:text-stone-200 font-medium">
                  {(duration / 1000).toFixed(2)}s
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Code block component with copy button and enhanced styling
function CodeBlock({
  className,
  children,
  inline,
  isStreaming,
}: {
  className?: string;
  children?: React.ReactNode;
  inline?: boolean;
  isStreaming?: boolean;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [isDark, setIsDark] = useState(false);
  const match = /language-(\w+)/.exec(className || "");
  const language = match ? match[1] : "";
  const codeString = String(children).replace(/\n$/, "");

  // Detect dark mode
  useEffect(() => {
    const checkDark = () => {
      setIsDark(document.documentElement.classList.contains("dark"));
    };
    checkDark();
    const observer = new MutationObserver(checkDark);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(codeString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Handle mermaid diagrams
  if (language === "mermaid") {
    return <MermaidDiagram chart={codeString} isStreaming={isStreaming} />;
  }

  if (inline) {
    return (
      <code className="rounded bg-stone-200 dark:bg-stone-700 px-1.5 py-0.5 text-sm text-stone-800 dark:text-stone-200 font-mono">
        {children}
      </code>
    );
  }

  return (
    <div className="group relative my-2 sm:my-3 max-w-full overflow-hidden rounded-xl border border-stone-200 dark:border-stone-700">
      {/* Header bar - ChatGPT style */}
      <div className="flex items-center justify-between px-3 sm:px-4 py-2 bg-stone-200/70 dark:bg-stone-800/50">
        <div className="flex items-center gap-2 min-w-0">
          {/* Language label */}
          <span className="text-xs font-medium text-stone-500 dark:text-stone-400 truncate">
            {language || "code"}
          </span>
        </div>
        {/* Copy button */}
        <button
          onClick={handleCopy}
          className={clsx(
            "flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-all touch-manipulation",
            "min-h-[32px] min-w-[32px]",
            copied
              ? "text-green-600 dark:text-green-400"
              : "text-stone-500 hover:text-stone-700 hover:bg-stone-300/50 dark:text-stone-400 dark:hover:text-stone-200 dark:hover:bg-stone-700/50",
          )}
          title={copied ? t("chat.message.copied") : t("chat.message.copyCode")}
        >
          {copied ? (
            <>
              <Check size={14} />
              <span className="hidden xs:inline">
                {t("chat.message.copied")}
              </span>
            </>
          ) : (
            <>
              <Copy size={14} />
              <span className="hidden xs:inline">{t("chat.message.copy")}</span>
            </>
          )}
        </button>
      </div>

      {/* Code content with syntax highlighting and line numbers */}
      <SyntaxHighlighter
        language={language || "text"}
        style={isDark ? oneDark : oneLight}
        showLineNumbers={true}
        wrapLines={true}
        customStyle={{
          margin: 0,
          padding: "0.75rem",
          fontSize: "0.75rem",
          lineHeight: "1.7",
          background: "transparent",
        }}
        lineNumberStyle={{
          minWidth: "2.5em",
          paddingRight: "1em",
          marginRight: "1em",
          textAlign: "right",
          color: isDark ? "#71717a" : "#a1a1aa",
          borderRight: isDark ? "1px solid #44403c" : "1px solid #e7e5e4",
        }}
        codeTagProps={{
          style: {
            fontFamily:
              "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
          },
        }}
      >
        {codeString}
      </SyntaxHighlighter>
    </div>
  );
}

// Collapsible Tool Call Item (紧凑设计)
function ToolCallItem({
  name,
  args,
  result,
  success,
  isPending,
}: {
  name: string;
  args: Record<string, unknown>;
  result?: string;
  success?: boolean;
  isPending?: boolean;
}) {
  const { t } = useTranslation();
  const hasResult = result !== undefined;
  const hasArgs = Object.keys(args).length > 0;

  // Map props to CollapsibleStatus
  let status: CollapsibleStatus = "idle";
  if (isPending) {
    status = "loading";
  } else if (success) {
    status = "success";
  } else if (hasResult) {
    status = "error";
  }

  const canExpand = hasArgs || hasResult;

  return (
    <CollapsiblePill
      status={status}
      icon={<Wrench size={12} className="shrink-0 opacity-50" />}
      label={name}
      variant="tool"
      expandable={canExpand}
    >
      {canExpand && (
        <div className="mt-2 ml-4 pl-3 border-l-2 border-stone-200/60 dark:border-stone-700/50 space-y-2">
          {/* Arguments */}
          {hasArgs && (
            <div className="p-2 rounded-md bg-stone-50/80 dark:bg-stone-800/50">
              <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-1 font-medium">
                {t("chat.message.args")}
              </div>
              <pre className="text-xs text-stone-600 dark:text-stone-300 overflow-x-auto">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          )}

          {/* Result */}
          {hasResult && (
            <div className="p-2 rounded-md bg-stone-50/80 dark:bg-stone-800/50">
              <div className="text-xs uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-1 font-medium">
                {t("chat.message.result")}
              </div>
              <pre className="text-xs text-stone-600 dark:text-stone-300 max-h-32 overflow-y-auto whitespace-pre-wrap break-words">
                {result}
              </pre>
            </div>
          )}

          {/* Pending state */}
          {isPending && (
            <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400">
              <LoadingSpinner size="xs" />
              <span>{t("chat.message.running")}</span>
            </div>
          )}
        </div>
      )}
    </CollapsiblePill>
  );
}

// File Reveal Item - 用于展示 reveal_file 工具的结果
interface FileInfo {
  path: string;
  description?: string;
  s3_url?: string;
  s3_key?: string;
  size?: number;
  error?: string;
}

interface FileRevealResult {
  type: "file_reveal";
  file: FileInfo;
}

// 获取文件扩展名
function getFileExtension(filePath: string): string {
  const parts = filePath.split(".");
  return parts.length > 1 ? parts.pop()?.toLowerCase() || "" : "";
}

// 根据文件类型获取图标和颜色
function getFileIconInfo(filePath: string): {
  icon: React.ElementType;
  color: string;
  bg: string;
} {
  const ext = getFileExtension(filePath);

  // 图片
  if (["jpg", "jpeg", "png", "gif", "svg", "webp", "ico"].includes(ext)) {
    return {
      icon: ImageIcon,
      color: "text-green-500",
      bg: "bg-green-100 dark:bg-green-900/30",
    };
  }
  // 代码文件
  if (
    [
      "js",
      "ts",
      "jsx",
      "tsx",
      "py",
      "java",
      "cpp",
      "c",
      "h",
      "go",
      "rs",
      "rb",
      "php",
      "vue",
      "html",
      "css",
      "json",
      "xml",
      "yaml",
      "yml",
      "sh",
      "bash",
    ].includes(ext)
  ) {
    return {
      icon: FileCode,
      color: "text-blue-500",
      bg: "bg-blue-100 dark:bg-blue-900/30",
    };
  }
  // Markdown
  if (["md", "markdown"].includes(ext)) {
    return {
      icon: FileText,
      color: "text-purple-500",
      bg: "bg-purple-100 dark:bg-purple-900/30",
    };
  }
  // PDF
  if (ext === "pdf") {
    return {
      icon: FileText,
      color: "text-red-500",
      bg: "bg-red-100 dark:bg-red-900/30",
    };
  }
  // 默认文件
  return {
    icon: FileText,
    color: "text-stone-500",
    bg: "bg-stone-100 dark:bg-stone-800",
  };
}

function FileRevealItem({
  args,
  result,
  success,
  isPending,
}: {
  args: Record<string, unknown>;
  result?: string;
  success?: boolean;
  isPending?: boolean;
}) {
  const { t } = useTranslation();
  const [showPreview, setShowPreview] = useState(false);

  // 解析结果获取路径和 S3 信息
  let filePath = "";
  let description = "";
  let s3Key = "";
  let fileSize: number | undefined = undefined;
  let error = "";

  if (result) {
    try {
      // 尝试提取 content 字段中的 JSON（如果格式是 content='...' name='...'）
      let jsonStr = result;
      const contentMatch = result.match(/content='(.+?)'(\s|$)/);
      if (contentMatch) {
        // 处理转义的单引号和可能的嵌套引号
        jsonStr = contentMatch[1].replace(/\\'/g, "'");
      }

      const parsed: FileRevealResult = JSON.parse(jsonStr);
      if (parsed.type === "file_reveal" && parsed.file) {
        filePath = parsed.file.path;
        description = parsed.file.description || "";
        s3Key = parsed.file.s3_key || "";
        fileSize = parsed.file.size;
        error = parsed.file.error || "";
      }
    } catch {
      // 解析失败，使用 args 中的值
      filePath = (args.path as string) || "";
      description = (args.description as string) || "";
    }
  } else {
    filePath = (args.path as string) || "";
    description = (args.description as string) || "";
  }

  const fileName = filePath.split("/").pop() || filePath;
  const { icon: FileIcon, color, bg } = getFileIconInfo(filePath);

  // Pending 状态
  if (isPending) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-900">
        <div className={`p-2.5 rounded-lg ${bg}`}>
          <LoadingSpinner size="sm" className={color} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-stone-700 dark:text-stone-300 truncate">
            {fileName}
          </div>
          {description && (
            <div className="text-xs text-stone-500 dark:text-stone-400 truncate mt-0.5">
              {description}
            </div>
          )}
        </div>
        <div className="text-xs text-amber-600 dark:text-amber-400">
          {t("chat.message.running")}
        </div>
      </div>
    );
  }

  // 错误状态
  if (error) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20">
        <div className={`p-2.5 rounded-lg bg-red-100 dark:bg-red-900/30`}>
          <FileIcon size={20} className="text-red-500" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-red-700 dark:text-red-300 truncate">
            {fileName}
          </div>
          <div className="text-xs text-red-500 dark:text-red-400 truncate mt-0.5">
            {error}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="my-2 sm:my-3">
      {showPreview && filePath && (
        <DocumentPreview
          path={filePath}
          s3Key={s3Key || undefined}
          fileSize={fileSize}
          onClose={() => setShowPreview(false)}
        />
      )}

      {/* 文件卡片 - 类似 ChatGPT 风格 */}
      <button
        onClick={() => filePath && setShowPreview(true)}
        className={clsx(
          "w-full flex items-center gap-3 p-4 rounded-xl border transition-all cursor-pointer text-left",
          success
            ? "border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-900 hover:shadow-lg hover:border-stone-300 dark:hover:border-stone-600 hover:scale-[1.005] transition-transform"
            : "border-stone-200 dark:border-stone-700 bg-stone-50 dark:bg-stone-800 opacity-70",
        )}
        disabled={!filePath || !success}
      >
        {/* 文件图标 */}
        <div className={`p-2.5 rounded-lg shrink-0 ${bg}`}>
          <FileIcon size={20} className={color} />
        </div>

        {/* 文件信息 */}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-stone-800 dark:text-stone-200 truncate">
            {fileName}
          </div>
          {description && (
            <div className="text-xs text-stone-500 dark:text-stone-400 truncate mt-1">
              {description}
            </div>
          )}
        </div>

        {/* 打开图标 */}
        {success && filePath && (
          <div className="shrink-0 p-2 rounded-lg bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400">
            <ExternalLink size={16} />
          </div>
        )}
      </button>
    </div>
  );
}

// Thinking Block - 思考过程展示 (ChatGPT风格)
function ThinkingBlock({
  content,
  isStreaming,
  isPending,
  success,
  hasResult,
}: {
  content: string;
  isStreaming?: boolean;
  isPending?: boolean;
  success?: boolean;
  hasResult?: boolean;
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="my-1">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={clsx(
          "inline-flex items-center gap-1.5 px-2.5 py-2 rounded-full text-xs font-medium",
          "transition-all bg-stone-200 dark:bg-stone-700",
          "text-stone-600 dark:text-stone-300",
          "hover:bg-stone-300 dark:hover:bg-stone-600 cursor-pointer",
        )}
      >
        {/* 状态指示器 */}
        {isPending ? (
          <LoadingSpinner size="sm" className="shrink-0" />
        ) : success ? (
          <CheckCircle size={12} className="shrink-0" />
        ) : hasResult ? (
          <XCircle size={12} className="shrink-0" />
        ) : null}

        {/* 思考图标 */}
        <Brain
          size={12}
          className="shrink-0 text-stone-500 dark:text-stone-400"
        />

        <span className="font-mono">
          {isStreaming || isPending
            ? t("chat.message.thinking")
            : t("chat.message.thought")}
        </span>
        {isStreaming && (
          <span className="flex items-center gap-[2px] ml-1">
            <span className="w-0.5 h-1 bg-stone-500 dark:bg-stone-400 rounded-full animate-[wave_0.6s_ease-in-out_infinite]" />
            <span className="w-0.5 h-1.5 bg-stone-500 dark:bg-stone-400 rounded-full animate-[wave_0.6s_ease-in-out_infinite_0.1s]" />
            <span className="w-0.5 h-1 bg-stone-500 dark:bg-stone-400 rounded-full animate-[wave_0.6s_ease-in-out_infinite_0.2s]" />
          </span>
        )}
        <ChevronRight
          size={12}
          className={clsx(
            "shrink-0 transition-transform duration-200 text-stone-500 dark:text-stone-400",
            isExpanded && "rotate-90",
          )}
        />
      </button>

      <div
        className={clsx(
          "grid transition-all duration-200 ease-out",
          isExpanded
            ? "grid-rows-[1fr] opacity-100 mt-1"
            : "grid-rows-[0fr] opacity-0",
        )}
      >
        <div className="overflow-hidden">
          <div className="ml-4 pl-3 border-l-2 border-stone-300 dark:border-stone-600">
            <pre className="text-xs text-stone-600 dark:text-stone-300 whitespace-pre-wrap font-mono leading-relaxed pl-1 pt-2">
              {content}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}

// Subagent Block - 子代理调用展示 (ChatGPT风格简约设计)
function SubagentBlock({
  agent_name,
  input,
  result,
  success,
  isPending,
  parts,
}: {
  agent_id: string;
  agent_name: string;
  input: string;
  result?: string;
  success?: boolean;
  isPending?: boolean;
  parts?: MessagePart[];
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);
  const hasContent = (parts && parts.length > 0) || result;

  // 完成后自动收起
  useEffect(() => {
    if (isPending === false) {
      setIsExpanded(false);
    }
  }, [isPending]);

  return (
    <div
      className={clsx(
        "my-3 rounded-xl overflow-hidden transition-all duration-200",
        "border border-stone-200 dark:border-stone-700",
        "bg-white dark:bg-stone-900",
      )}
    >
      {/* Header - 简约设计 */}
      <button
        onClick={() => hasContent && setIsExpanded(!isExpanded)}
        className={clsx(
          "w-full px-4 py-3 flex items-center gap-3 transition-colors",
          "hover:bg-stone-50 dark:hover:bg-stone-800/50",
          hasContent && "cursor-pointer",
        )}
      >
        {/* 状态图标 - 小巧精致 */}
        <div
          className={clsx(
            "flex h-7 w-7 items-center justify-center rounded-lg",
            isPending
              ? "bg-blue-100 dark:bg-blue-900/40"
              : success
                ? "bg-emerald-100 dark:bg-emerald-900/40"
                : "bg-stone-100 dark:bg-stone-800",
          )}
        >
          {isPending ? (
            <LoadingSpinner
              size="sm"
              className="text-blue-600 dark:text-blue-400"
            />
          ) : success ? (
            <CheckCircle
              size={14}
              className="text-stone-600 dark:text-stone-300"
            />
          ) : (
            <Users size={14} className="text-stone-500 dark:text-stone-400" />
          )}
        </div>

        <div className="flex-1 min-w-0 text-left">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-stone-800 dark:text-stone-200 truncate">
              {agent_name}
            </span>
            {isPending && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400 font-medium">
                {t("chat.message.running")}
              </span>
            )}
          </div>
          {input && !isExpanded && (
            <p className="text-xs text-stone-500 dark:text-stone-400 truncate mt-0.5 max-w-md">
              {input}
            </p>
          )}
        </div>

        {/* 展开按钮 */}
        {hasContent && (
          <div className="text-stone-400 dark:text-stone-500">
            {isExpanded ? (
              <ChevronDown size={18} />
            ) : (
              <ChevronRight size={18} />
            )}
          </div>
        )}
      </button>

      {/* 展开内容 */}
      {isExpanded && (
        <div className="px-4 pb-4 space-y-3">
          {/* 分隔线 */}
          <div className="border-t border-stone-100 dark:border-stone-800" />

          {/* 任务描述 */}
          {input && (
            <div className="text-sm text-stone-600 dark:text-stone-300 leading-relaxed">
              <MarkdownContent content={input} />
            </div>
          )}

          {/* 子代理内部内容 */}
          {parts && parts.length > 0 && (
            <div className="space-y-2 pl-3 border-l-2 border-stone-200 dark:border-stone-700">
              {parts.map((part, index) => (
                <SubagentContentRenderer
                  key={index}
                  part={part}
                  isStreaming={isPending}
                  isLast={index === parts.length - 1}
                />
              ))}
            </div>
          )}

          {/* 结果 */}
          {result && !isPending && (
            <div className="p-3 rounded-lg bg-stone-50 dark:bg-stone-800/50 border border-stone-100 dark:border-stone-700">
              <div className="text-xs text-stone-500 dark:text-stone-400 mb-1.5 font-medium">
                {t("chat.message.result")}
              </div>
              <div className="text-xs text-stone-700 dark:text-stone-300 max-h-48 overflow-y-auto leading-relaxed">
                <MarkdownContent content={result} />
              </div>
            </div>
          )}

          {/* 等待状态 */}
          {isPending && !parts?.length && (
            <div className="flex items-center gap-2 py-2 text-stone-500 dark:text-stone-400">
              <LoadingSpinner size="sm" />
              <span className="text-sm">{t("chat.message.executing")}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// 子代理内部工具调用组件（单独提取以遵守 hooks 规则）
function SubagentToolItem({
  part,
}: {
  part: Extract<MessagePart, { type: "tool" }>;
}) {
  const { t } = useTranslation();

  // Determine status based on part state
  let status: CollapsibleStatus = "idle";
  if (part.isPending) {
    status = "loading";
  } else if (part.success) {
    status = "success";
  } else if (part.result) {
    status = "error";
  }

  const hasArgs = part.args && Object.keys(part.args).length > 0;
  const hasResult = !!part.result;
  const canExpand = hasArgs || hasResult;

  return (
    <div className="rounded-lg bg-stone-100/80 dark:bg-stone-700/50 overflow-hidden">
      <CollapsiblePill
        status={status}
        icon={<Wrench size={12} className="shrink-0 opacity-50" />}
        label={part.name}
        variant="tool"
        expandable={canExpand}
      >
        {canExpand && (
          <div className="px-3 pb-2 space-y-2 border-t border-stone-200/50 dark:border-stone-600/50">
            {hasArgs && (
              <div>
                <div className="text-xs text-stone-400 dark:text-stone-500 mb-1">
                  {t("chat.message.parameters")}
                </div>
                <pre className="text-xs text-stone-600 dark:text-stone-300 bg-stone-50 dark:bg-stone-800 rounded p-1.5 overflow-auto">
                  {JSON.stringify(part.args, null, 2)}
                </pre>
              </div>
            )}
            {hasResult && (
              <div>
                <div className="text-xs text-stone-400 dark:text-stone-500 mb-1">
                  {t("chat.message.result")}
                </div>
                <pre className="text-xs text-stone-600 dark:text-stone-300 bg-stone-50 dark:bg-stone-800 rounded p-1.5 max-h-24 overflow-auto">
                  {truncateText(part.result || "", 500)}
                </pre>
              </div>
            )}
          </div>
        )}
      </CollapsiblePill>
    </div>
  );
}

// Sandbox 状态块组件
function SandboxItem({
  status,
  sandboxId,
  error,
}: {
  status: "starting" | "ready" | "error";
  sandboxId?: string;
  error?: string;
}) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);

  const hasDetails =
    (status === "ready" && sandboxId) || (status === "error" && error);

  const pillStatus: CollapsibleStatus =
    status === "starting"
      ? "loading"
      : status === "ready"
        ? "success"
        : "error";

  return (
    <CollapsiblePill
      status={pillStatus}
      icon={<Box size={10} className="shrink-0 opacity-50" />}
      label={t("chat.sandbox.name")}
      expandable={!!hasDetails}
      onExpandChange={setIsExpanded}
    >
      {isExpanded && hasDetails && (
        <div className="mt-1 ml-4 pl-3 border-l-2 border-stone-300 dark:border-stone-600">
          {status === "ready" && sandboxId && (
            <div className="text-xs text-stone-600 dark:text-stone-300 pl-1 py-1 font-mono">
              ID: {sandboxId}
            </div>
          )}
          {status === "error" && error && (
            <div className="text-xs text-red-600 dark:text-red-400 pl-1 py-1">
              {error}
            </div>
          )}
        </div>
      )}
    </CollapsiblePill>
  );
}

// 子代理内部内容渲染器（独立于主代理的渲染逻辑）
function SubagentContentRenderer({
  part,
  isStreaming,
  isLast,
}: {
  part: MessagePart;
  isStreaming?: boolean;
  isLast: boolean;
}) {
  // 文本 - 使用 markdown 渲染
  if (part.type === "text") {
    return (
      <div className="text-sm text-stone-600 dark:text-stone-300 leading-relaxed">
        <MarkdownContent
          content={part.content || ""}
          isStreaming={isStreaming && isLast}
        />
      </div>
    );
  }

  // 工具调用 - 使用独立组件
  if (part.type === "tool") {
    return <SubagentToolItem part={part} />;
  }

  // Thinking - 使用 ThinkingBlock 组件
  if (part.type === "thinking") {
    return (
      <ThinkingBlock
        content={part.content || ""}
        isStreaming={isStreaming && isLast && part.isStreaming}
      />
    );
  }

  // 嵌套子代理（递归）
  if (part.type === "subagent") {
    return (
      <SubagentBlock
        agent_id={part.agent_id}
        agent_name={part.agent_name}
        input={part.input}
        result={part.result}
        success={part.success}
        isPending={part.isPending}
        parts={part.parts}
      />
    );
  }

  // Sandbox 状态块
  if (part.type === "sandbox") {
    return (
      <SandboxItem
        status={part.status}
        sandboxId={part.sandbox_id}
        error={part.error}
      />
    );
  }

  return null;
}

// 格式化文件大小
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// 根据文件类型获取图标和颜色信息
function getAttachmentIconInfo(mimeType: string): {
  icon: React.ElementType;
  bgColor: string;
  iconColor: string;
  label: string;
} {
  // 图片
  if (mimeType.startsWith("image/")) {
    return {
      icon: ImageIcon,
      bgColor: "bg-emerald-500",
      iconColor: "text-white",
      label: "image",
    };
  }
  // PDF
  if (mimeType === "application/pdf") {
    return {
      icon: FileText,
      bgColor: "bg-red-400",
      iconColor: "text-white",
      label: "PDF",
    };
  }
  // 代码文件
  if (
    mimeType.startsWith("text/") ||
    mimeType.includes("javascript") ||
    mimeType.includes("json") ||
    mimeType.includes("xml")
  ) {
    return {
      icon: FileCode,
      bgColor: "bg-blue-500",
      iconColor: "text-white",
      label: "text",
    };
  }
  // 默认文件
  return {
    icon: FileText,
    bgColor: "bg-gray-400",
    iconColor: "text-white",
    label: "file",
  };
}

// 用户消息气泡组件（带复制功能，支持 markdown 渲染）- ChatGPT 风格
function UserMessageBubble({
  content,
  attachments,
}: {
  content?: string;
  attachments?: MessageAttachment[];
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [previewAttachment, setPreviewAttachment] =
    useState<MessageAttachment | null>(null);
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);

  // Debug log for attachments
  useEffect(() => {
    console.log("[UserMessageBubble] Rendering with attachments:", attachments);
  }, [attachments]);

  const handleCopy = async () => {
    if (!content) return;
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // 渲染附件预览 - 统一使用文件卡片样式
  const renderAttachments = () => {
    if (!attachments || attachments.length === 0) return null;

    return (
      <div className="flex flex-row justify-end flex-wrap gap-2 sm:gap-3 mb-2">
        {attachments.map((attachment) => {
          const isImage =
            attachment.mimeType?.startsWith("image/") && attachment.url;

          return (
            <AttachmentCard
              key={attachment.id}
              attachment={attachment}
              variant="preview"
              size="default"
              onClick={() => {
                if (isImage && attachment.url) {
                  setImageViewerSrc(getFullUrl(attachment.url) ?? null);
                } else {
                  setPreviewAttachment(attachment);
                }
              }}
            />
          );
        })}
      </div>
    );
  };

  const hasAttachments = attachments && attachments.length > 0;
  const hasContent = content && content.trim().length > 0;

  return (
    <div className="w-full px-2 py-1.5 sm:px-4 group">
      <div className="mx-auto flex max-w-3xl xl:max-w-5xl justify-end px-2">
        <div className="flex flex-col items-end max-w-[90%]">
          {/* 附件预览 - 在消息气泡外部 */}
          {hasAttachments && renderAttachments()}

          {/* 消息气泡 */}
          {hasContent && (
            <div className="rounded-3xl max-w-full px-5 py-3 bg-gray-50 dark:bg-stone-800 shadow-sm">
              <div className="leading-relaxed text-[15px] sm:text-base text-stone-700 dark:text-stone-300">
                <MarkdownContent content={content!} />
              </div>
            </div>
          )}

          {/* 操作按钮 - 悬停时显示 */}
          <div className="flex justify-end mt-1 gap-1">
            <button
              onClick={handleCopy}
              className={clsx(
                "p-1.5 rounded-lg transition-all duration-200",
                "opacity-0 group-hover:opacity-100",
                "hover:bg-black/5 dark:hover:bg-white/5",
                copied
                  ? "text-emerald-500 dark:text-emerald-400"
                  : "text-gray-400 dark:text-stone-500 hover:text-gray-600 dark:hover:text-stone-300",
              )}
              title={copied ? t("chat.message.copied") : t("chat.message.copy")}
            >
              {copied ? <Check size={16} /> : <Copy size={16} />}
            </button>
          </div>
        </div>
      </div>

      {/* 文件预览弹窗 */}
      {previewAttachment && (
        <DocumentPreview
          path={previewAttachment.name}
          s3Key={previewAttachment.key}
          fileSize={previewAttachment.size}
          onClose={() => setPreviewAttachment(null)}
          imageUrl={
            previewAttachment.type === "image"
              ? getFullUrl(previewAttachment.url)
              : undefined
          }
        />
      )}

      {/* Image viewer for direct image preview */}
      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          isOpen={!!imageViewerSrc}
          onClose={() => setImageViewerSrc(null)}
        />
      )}
    </div>
  );
}

export function ChatMessage({ message }: ChatMessageProps) {
  const { t } = useTranslation();
  const isUser = message.role === "user";
  const isStreaming = message.isStreaming && !message.content;

  // 如果有 parts，按顺序渲染；否则回退到旧的渲染方式
  const hasParts = message.parts && message.parts.length > 0;

  // 用户消息：气泡样式，右对齐
  if (isUser) {
    console.log("[ChatMessage] Rendering user message with attachments:", {
      messageId: message.id,
      attachments: message.attachments,
    });
    return (
      <UserMessageBubble
        content={message.content}
        attachments={message.attachments}
      />
    );
  }

  // 获取助手消息的纯文本内容用于复制
  const getAssistantTextContent = (): string => {
    if (hasParts && message.parts) {
      // 从 parts 中提取所有文本内容
      return message.parts
        .filter(
          (part): part is Extract<MessagePart, { type: "text" }> =>
            part.type === "text",
        )
        .map((part) => part.content)
        .join("\n");
    }
    return message.content || "";
  };

  // 助手消息：左侧布局
  return (
    <div className="group w-full">
      <div className="mx-auto flex flex-col max-w-3xl xl:max-w-5xl px-5 sm:px-7 sm:mb-4">
        {/* Content */}
        <div className="flex-1 overflow-hidden min-w-0">
          {/* Header: Avatar + Role label + Stop button */}
          <div className="mb-3 flex items-center gap-2">
            <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-amber-500 to-rose-500 text-white shadow-sm">
              <Bot size={16} />
            </div>
            <span className="text-sm sm:text-base font-semibold text-stone-900 dark:text-stone-100">
              {t("chat.message.assistant")}
            </span>
          </div>

          {/* Streaming/Thinking indicator */}
          {isStreaming && !hasParts && <ThinkingIndicator />}

          {hasParts ? (
            <div className="space-y-3 px-2">
              {message.parts!.map((part: MessagePart, index: number) => (
                <MessagePartRenderer
                  key={index}
                  part={part}
                  isStreaming={message.isStreaming}
                  isLast={index === message.parts!.length - 1}
                />
              ))}
            </div>
          ) : (
            <>
              {message.content && (
                <MarkdownContent
                  content={message.content}
                  isStreaming={message.isStreaming}
                />
              )}
              {message.toolCalls && message.toolCalls.length > 0 && (
                <div className="mt-4 space-y-2">
                  <div className="text-xs font-medium text-stone-400 uppercase tracking-wide mb-2 dark:text-stone-500">
                    {t("chat.message.toolCalls")} ({message.toolCalls.length})
                  </div>
                  {message.toolCalls.map((call: ToolCall, index: number) => {
                    const result = message.toolResults?.find(
                      (r: ToolResult) => r.name === call.name,
                    );
                    return (
                      <ToolCallItem
                        key={index}
                        name={call.name}
                        args={call.args || {}}
                        result={result?.result}
                        success={result?.success}
                        isPending={!result && message.isStreaming}
                      />
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>
        {/* 复制按钮和 Token 按钮 - 底部同一水平线，悬停消息时显示（仅消息完成后） */}
        {!message.isStreaming && (
          <div className="mt-2 flex items-center gap-1">
            <button
              onClick={() => {
                const textContent = getAssistantTextContent();
                if (textContent) {
                  navigator.clipboard.writeText(textContent);
                  toast.success(t("chat.message.copied"));
                }
              }}
              className={clsx(
                "p-1.5 rounded-md transition-all",
                "opacity-0 group-hover:opacity-100",
                "hover:bg-gray-200 dark:hover:bg-stone-700",
                "text-gray-400 dark:text-stone-500 hover:text-gray-600 dark:hover:text-stone-300",
              )}
              title={t("chat.message.copy")}
            >
              <Copy size={14} />
            </button>
            {/* Token 使用统计按钮 */}
            {(message.tokenUsage || message.duration) && (
              <TokenDetailsButton
                tokenUsage={message.tokenUsage}
                duration={message.duration}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// 渲染单个消息部分
function MessagePartRenderer({
  part,
  isStreaming,
  isLast,
}: {
  part: MessagePart;
  isStreaming?: boolean;
  isLast: boolean;
}) {
  if (part.type === "text") {
    // 子代理内部的文本使用简单渲染，主代理使用 Markdown
    if (part.depth && part.depth > 0) {
      return (
        <span className="text-xs text-stone-600 dark:text-stone-300 leading-relaxed">
          {part.content}
          {isStreaming && isLast && (
            <span className="inline-block h-3 w-0.5 animate-pulse bg-blue-400 ml-0.5 rounded-sm" />
          )}
        </span>
      );
    }
    return (
      <MarkdownContent
        content={part.content}
        isStreaming={isStreaming && isLast}
      />
    );
  }

  if (part.type === "tool") {
    // 检测 reveal_file 工具，使用专门的组件
    if (part.name === "reveal_file") {
      return (
        <FileRevealItem
          args={part.args}
          result={part.result}
          success={part.success}
          isPending={part.isPending}
        />
      );
    }
    return (
      <ToolCallItem
        name={part.name}
        args={part.args}
        result={part.result}
        success={part.success}
        isPending={part.isPending}
      />
    );
  }

  if (part.type === "thinking") {
    return (
      <ThinkingBlock
        content={part.content}
        isStreaming={isStreaming && isLast && part.isStreaming}
      />
    );
  }

  if (part.type === "subagent") {
    return (
      <SubagentBlock
        agent_id={part.agent_id}
        agent_name={part.agent_name}
        input={part.input}
        result={part.result}
        success={part.success}
        isPending={part.isPending}
        parts={part.parts}
      />
    );
  }

  // Sandbox 状态块
  if (part.type === "sandbox") {
    return (
      <SandboxItem
        status={part.status}
        sandboxId={part.sandbox_id}
        error={part.error}
      />
    );
  }

  return null;
}

// Markdown 内容渲染组件 - 美化版本
const MarkdownContent = memo(function MarkdownContent({
  content,
  isStreaming,
}: {
  content: string;
  isStreaming?: boolean;
}) {
  return (
    <span className="markdown-preview block my-1">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // Headings
          h1: ({ children }) => (
            <h1 className="text-2xl font-bold text-stone-900 dark:text-stone-100 mt-4 mb-3 first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-xl font-bold text-stone-900 dark:text-stone-100 mt-3 mb-2">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100 mt-2 mb-1.5">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-base font-semibold text-stone-800 dark:text-stone-200 mt-2 mb-1">
              {children}
            </h4>
          ),
          // Paragraphs
          p: ({ children }) => (
            <p className="text-stone-700 dark:text-stone-300 leading-relaxed mb-2 last:mb-0">
              {children}
            </p>
          ),
          // Lists with better styling
          ul: ({ children }) => (
            <ul className="list-none space-y-1.5 mb-3 pl-5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal space-y-1.5 mb-3 pl-5 marker:text-stone-500 dark:marker-stone-400 marker:font-semibold">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="text-stone-700 dark:text-stone-300 leading-relaxed relative">
              <span className="absolute -left-3 top-2" />
              {children}
            </li>
          ),
          // Blockquotes with elegant styling
          blockquote: ({ children }) => (
            <blockquote className="my-3 pl-3 pr-3 py-2 border-l-4 border-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded-r-lg">
              <div className="text-stone-600 dark:text-stone-300 italic text-sm">
                {children}
              </div>
            </blockquote>
          ),
          // Links with hover effects
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 no-underline transition-colors"
            >
              {children}
            </a>
          ),
          // Horizontal rule
          hr: () => (
            <hr className="my-4 border-0 h-px bg-gradient-to-r from-transparent via-stone-300 dark:via-stone-600 to-transparent" />
          ),
          // Strong and emphasis
          strong: ({ children }) => (
            <strong className="font-bold text-stone-900 dark:text-stone-100">
              {children}
            </strong>
          ),
          em: ({ children }) => (
            <em className="italic text-stone-600 dark:text-stone-400">
              {children}
            </em>
          ),
          // Code blocks
          code: ({ className, children }) => {
            const hasLanguage = className && /language-/.test(className);
            const codeContent = String(children).replace(/\n$/, "");
            const isMultiline = codeContent.includes("\n");
            const isInline = !hasLanguage && !isMultiline;

            return (
              <CodeBlock
                className={className}
                inline={isInline}
                isStreaming={isStreaming}
              >
                {children}
              </CodeBlock>
            );
          },
          pre: ({ children }) => <>{children}</>,
          // Tables with beautiful styling
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto rounded-lg shadow ring-1 ring-stone-200 dark:ring-stone-700">
              <table className="min-w-full divide-y divide-stone-200 dark:divide-stone-700">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-stone-50 dark:bg-stone-800">{children}</thead>
          ),
          tbody: ({ children }) => (
            <tbody className="divide-y divide-stone-200 dark:divide-stone-700 bg-white dark:bg-stone-900">
              {children}
            </tbody>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-stone-50 dark:hover:bg-stone-800/50 transition-colors">
              {children}
            </tr>
          ),
          th: ({ children }) => (
            <th className="px-3 py-2 text-left text-xs font-semibold text-stone-700 dark:text-stone-300 uppercase tracking-wider">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2 text-sm text-stone-600 dark:text-stone-400 whitespace-nowrap">
              {children}
            </td>
          ),
          // Images
          img: ({ src, alt }) => (
            <img
              src={src}
              alt={alt}
              className="max-w-full h-auto my-2 rounded-lg shadow"
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
      {isStreaming && (
        <span className="inline-block h-4 w-1.5 animate-pulse bg-amber-400 ml-0.5 rounded-sm align-middle" />
      )}
    </span>
  );
});

function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
}
