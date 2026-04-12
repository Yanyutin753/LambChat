import {
  useState,
  useEffect,
  useMemo,
  useRef,
  useCallback,
  lazy,
  Suspense,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { FileIcon } from "../common/FileIcon";
import { ImageViewer } from "../common/ImageViewer";
import {
  X,
  AlertCircle,
  Copy,
  Check,
  Download,
  Maximize2,
  Minimize2,
  Eye,
  Code2,
  PanelRight,
  Maximize,
} from "lucide-react";
import { uploadApi } from "../../services/api";

// Import utilities
import {
  getFileExtension,
  isBinaryFile,
  isImageFile,
  isPdfFile,
  isWordFile,
  isLegacyDocFile,
  isExcelFile,
  isPptFile,
  isPptxFile,
  isHtmlFile,
  isCodeFile,
  isMarkdownFile,
  isPreviewableFile,
  isExcalidrawFile,
  isVideoFile,
  getFileTypeInfo,
  detectLanguage,
} from "./utils";

// Import preview components
import CodeRenderer from "./previews/CodeRenderer";
import PlainTextViewer from "./previews/PlainTextViewer";
import MarkdownRenderer from "./previews/MarkdownRenderer";
import PptPreview from "./previews/PptPreview";
import HtmlPreview from "./previews/HtmlPreview";

// Lazy load heavy preview components
const PdfPreview = lazy(() => import("./previews/PdfPreview"));
const WordPreview = lazy(() => import("./previews/WordPreview"));
const ExcelPreview = lazy(() => import("./previews/ExcelPreview"));
const ExcalidrawPreview = lazy(() => import("./previews/ExcalidrawPreview"));

// Re-export utilities for external use
/* eslint-disable react-refresh/only-export-components */
export {
  getFileExtension,
  isBinaryFile,
  isImageFile,
  isPdfFile,
  isWordFile,
  isExcelFile,
  isPptFile,
  isHtmlFile,
  isPreviewableFile,
  isCodeFile,
  isMarkdownFile,
  getFileTypeInfo,
  detectLanguage,
} from "./utils";
/* eslint-enable react-refresh/only-export-components */

// Export components for external use
export { default as CodeRenderer } from "./previews/CodeRenderer";
export { default as MarkdownRenderer } from "./previews/MarkdownRenderer";
export { default as HtmlPreview } from "./previews/HtmlPreview";

interface DocumentPreviewProps {
  path: string;
  content?: string; // File content passed from parent (from agent events)
  s3Key?: string; // S3 object key for fetching content via signed URL
  signedUrl?: string; // Pre-signed URL (if available, skips getSignedUrl call)
  fileSize?: number; // File size in bytes
  imageUrl?: string; // Direct image URL for previewing image attachments
  onClose: () => void;
}

export default function DocumentPreview({
  path,
  content,
  s3Key,
  signedUrl,
  fileSize,
  imageUrl: externalImageUrl,
  onClose,
}: DocumentPreviewProps) {
  const { t } = useTranslation();
  const [data, setData] = useState<{ content: string; path: string } | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pptUrl, setPptUrl] = useState<string | null>(null);
  const [pptxBuffer, setPptxBuffer] = useState<ArrayBuffer | null>(null);
  const [htmlUrl, setHtmlUrl] = useState<string | null>(null);
  const [htmlContent, setHtmlContent] = useState<string>("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [docUrl, setDocUrl] = useState<string | null>(null);
  const [arrayBuffer, setArrayBuffer] = useState<ArrayBuffer | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showImageViewer, setShowImageViewer] = useState(false);
  const [excalidrawData, setExcalidrawData] = useState<string>("");
  const [viewSource, setViewSource] = useState(false);
  const [viewMode, setViewMode] = useState<"center" | "sidebar">("sidebar");
  const [resolvedUrl, setResolvedUrl] = useState<string | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    return parseInt(localStorage.getItem("sidebar-preview-width") || "45", 10);
  });

  // Persist sidebar width to CSS variable + localStorage
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--sidebar-preview-width", `${sidebarWidth}%`);
    localStorage.setItem("sidebar-preview-width", String(sidebarWidth));
  }, [sidebarWidth]);

  // When sidebar mode is active, signal the main layout to compress
  useEffect(() => {
    const root = document.documentElement;
    if (viewMode === "sidebar") {
      root.setAttribute("data-sidebar-preview", "open");
    } else {
      root.removeAttribute("data-sidebar-preview");
    }
    return () => root.removeAttribute("data-sidebar-preview");
  }, [viewMode]);

  // Drag resize handler — native DOM capture layer to block iframe events
  const panelRef = useRef<HTMLDivElement>(null);
  const indicatorRef = useRef<HTMLDivElement>(null);
  const isResizing = useRef(false);
  const justResized = useRef(false);
  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const panel = panelRef.current;
      if (!panel) return;
      isResizing.current = true;
      const startX = e.clientX;
      const root = document.documentElement;
      const startWidth = parseInt(
        root.style.getPropertyValue("--sidebar-preview-width") ||
          String(sidebarWidth),
        10,
      );
      const indicator = indicatorRef.current;

      // Create raw DOM capture layer — blocks any iframe from stealing events
      const capture = document.createElement("div");
      capture.style.cssText =
        "position:fixed;inset:0;z-index:999999;cursor:col-resize;";
      document.body.appendChild(capture);

      const onMove = (ev: MouseEvent) => {
        if (!isResizing.current) return;
        if (indicator) {
          indicator.style.left = `${ev.clientX}px`;
          indicator.style.display = "block";
        }
      };
      const onUp = (ev: MouseEvent) => {
        if (!isResizing.current) return;
        isResizing.current = false;
        if (indicator) indicator.style.display = "none";
        capture.remove();
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        // Apply resize
        const delta = ((startX - ev.clientX) / window.innerWidth) * 100;
        const val = Math.round(Math.min(Math.max(startWidth + delta, 25), 75));
        root.style.setProperty("--sidebar-preview-width", `${val}%`);
        setSidebarWidth(val);
        if (panel) panel.style.maxWidth = `${val}%`;
        localStorage.setItem("sidebar-preview-width", String(val));
        justResized.current = true;
        setTimeout(() => {
          justResized.current = false;
        }, 100);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [sidebarWidth],
  );

  const fileName = path.split("/").pop() || path;
  const ext = getFileExtension(fileName);
  const binaryFile = isBinaryFile(ext);
  const imageFile = isImageFile(fileName);
  const pdfFile = isPdfFile(ext);
  const wordFile = isWordFile(ext);
  const legacyDocFile = isLegacyDocFile(ext);
  const excelFile = isExcelFile(ext);
  const pptxFile = isPptxFile(ext);
  // Keep pptFile for backward compatibility
  const pptFile = isPptFile(ext);
  const htmlFile = isHtmlFile(ext);
  const codeFile = isCodeFile(ext);
  const markdownFile = isMarkdownFile(fileName);
  const previewable = isPreviewableFile(ext);
  const excalidrawFile = isExcalidrawFile(ext);
  const videoFile = isVideoFile(ext);

  // Memoize language detection for performance
  const language = useMemo(() => detectLanguage(fileName), [fileName]);

  // 判断是否有文本内容（二进制文件、Office文件等没有文本内容）
  const hasTextContent = useMemo(() => {
    return !!(
      data?.content &&
      !binaryFile &&
      !wordFile &&
      !excelFile &&
      !pptFile &&
      !htmlFile &&
      !excalidrawFile
    );
  }, [
    data?.content,
    binaryFile,
    wordFile,
    excelFile,
    pptFile,
    htmlFile,
    excalidrawFile,
  ]);

  // Memoize char count - show file size for binary files
  const displaySize = useMemo(() => {
    if (!hasTextContent && fileSize) {
      return fileSize;
    }
    return data?.content?.length || 0;
  }, [hasTextContent, fileSize, data?.content]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setImageUrl(null);
    setPdfUrl(null);
    setPptUrl(null);
    setPptxBuffer(null);
    setHtmlUrl(null);
    setHtmlContent("");
    setVideoUrl(null);
    setArrayBuffer(null);
    setExcalidrawData("");
    setResolvedUrl(null);

    const loadContent = async () => {
      // 如果传入了外部图片 URL，直接使用
      if (externalImageUrl) {
        setImageUrl(externalImageUrl);
        setData({ content: "", path });
        setLoading(false);
        return;
      }

      // 优先使用传入的 content
      if (content !== undefined) {
        // HTML 文件创建 blob URL 用于 iframe 渲染
        if (htmlFile) {
          const blob = new Blob([content], { type: "text/html" });
          const url = URL.createObjectURL(blob);
          setHtmlUrl(url);
          setHtmlContent(content);
          setData({ content: "", path });
        } else {
          setData({ content, path });
        }
        setLoading(false);
        return;
      }

      // 如果有 s3Key 或 signedUrl，从 S3 获取内容
      if (s3Key || signedUrl) {
        try {
          // 优先使用传入的 signedUrl，否则通过 s3Key 获取
          const url =
            signedUrl || (s3Key ? await uploadApi.getSignedUrl(s3Key) : null);

          if (!url) {
            throw new Error("No URL available");
          }

          setResolvedUrl(url);

          // 图片文件直接使用签名 URL
          if (imageFile) {
            setImageUrl(url);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          // PDF 文件使用 iframe 嵌入
          if (pdfFile) {
            setPdfUrl(url);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          // 视频文件直接使用签名 URL
          if (videoFile) {
            setVideoUrl(url);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          // PPT 文件处理
          if (pptFile) {
            if (pptxFile) {
              // .pptx 文件获取 ArrayBuffer 用于本地预览
              // Use Office Online viewer for .pptx files (same as .ppt)
              setPptUrl(url);
              setData({ content: "", path });
            } else {
              // .ppt 文件使用 Office Online viewer
              setPptUrl(url);
              setData({ content: "", path });
            }
            setLoading(false);
            return;
          }

          // HTML 文件使用 iframe 嵌入
          if (htmlFile) {
            setHtmlUrl(url);
            // 同时获取内容用于查看源代码
            try {
              const response = await fetch(url);
              if (response.ok) {
                const text = await response.text();
                setHtmlContent(text);
              }
            } catch (e) {
              console.error("Failed to fetch HTML content:", e);
            }
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          // Excalidraw files - load as text and pass to preview
          if (excalidrawFile) {
            const response = await fetch(url);
            if (!response.ok) {
              throw new Error(`Failed to fetch file: ${response.status}`);
            }
            const text = await response.text();
            setExcalidrawData(text);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          // 旧版 .doc 文件不支持预览，保存 URL 用于下载
          if (legacyDocFile) {
            setDocUrl(url);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          // 其他文件获取内容
          const response = await fetch(url);
          if (!response.ok) {
            throw new Error(`Failed to fetch file: ${response.status}`);
          }

          // 根据文件类型处理内容
          if (binaryFile) {
            // 二进制文件，只设置路径用于下载
            setData({ content: "", path });
          } else if (wordFile || excelFile) {
            // Word/Excel 文件需要作为 ArrayBuffer 处理
            const buffer = await response.arrayBuffer();
            setArrayBuffer(buffer);
            setData({ content: "", path });
          } else if (!previewable) {
            // 不支持预览的文件类型，自动下载
            setData({ content: "", path });
            // 延迟一下再下载，让UI先渲染
            setTimeout(() => {
              const a = document.createElement("a");
              a.href = url;
              a.download = fileName;
              a.click();
            }, 100);
          } else {
            // 文本文件，读取内容
            const text = await response.text();
            setData({ content: text, path });
          }
          setLoading(false);
        } catch (err) {
          console.error("Failed to load file from S3:", err);
          setError(t("documents.failedToLoadFromS3", "从存储加载文件失败"));
          setLoading(false);
        }
        return;
      }

      // 没有内容也没有 s3Key
      setError(t("documents.noContent", "文件内容不可用"));
      setLoading(false);
    };

    loadContent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, content, s3Key, signedUrl, externalImageUrl]);

  // Revoke blob URLs on change or unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (htmlUrl?.startsWith("blob:")) {
        URL.revokeObjectURL(htmlUrl);
      }
    };
  }, [htmlUrl]);

  // Handle ESC key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Lock body scroll in center/modal mode; sidebar mode keeps scroll enabled
  useEffect(() => {
    if (viewMode !== "sidebar") {
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = "";
      };
    }
  }, [viewMode]);

  const handleCopy = async () => {
    if (data?.content) {
      await navigator.clipboard.writeText(data.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = async () => {
    // Cross-origin URLs: fetch as blob to ensure download attribute filename is respected
    const downloadUrl = signedUrl || resolvedUrl || externalImageUrl;
    if (downloadUrl) {
      try {
        const response = await fetch(downloadUrl);
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
      } catch {
        // Fallback: open in new tab if fetch fails (e.g., CORS blocked)
        window.open(downloadUrl, "_blank");
      }
      return;
    }

    // 兜底：使用内存中的内容下载
    if (data?.content) {
      const blob = new Blob([data.content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  };

  const fileInfo = getFileTypeInfo(fileName);
  const Icon = fileInfo.icon;

  const isSidebar = viewMode === "sidebar";
  // Hide button text labels when sidebar is too narrow
  const [hideBtnLabels, setHideBtnLabels] = useState(false);
  useEffect(() => {
    if (!isSidebar) {
      setHideBtnLabels(false);
      return;
    }

    const check = () => {
      const pct =
        parseFloat(
          getComputedStyle(document.documentElement).getPropertyValue(
            "--sidebar-preview-width",
          ),
        ) || sidebarWidth;
      setHideBtnLabels((pct / 100) * window.innerWidth < 500);
    };

    check();
    window.addEventListener("resize", check);
    // Drag updates CSS variable on <html> style attr — observe it
    const observer = new MutationObserver(check);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["style"],
    });
    return () => {
      window.removeEventListener("resize", check);
      observer.disconnect();
    };
  }, [isSidebar, sidebarWidth]);

  return createPortal(
    <div
      className={`fixed inset-0 z-[200] flex flex-col ${
        isSidebar
          ? "bg-black/50 sm:bg-transparent sm:pointer-events-none sm:items-end sm:justify-stretch"
          : "sm:items-center sm:justify-center bg-black/70"
      }`}
      onClick={() => {
        if (!isResizing.current && !justResized.current) onClose();
      }}
    >
      {/* Resize indicator line — follows mouse, no reflow */}
      <div
        ref={indicatorRef}
        className="sm:block fixed top-0 bottom-0 z-[201] pointer-events-none"
        style={{
          display: "none",
          left: 0,
          width: "2px",
          backgroundColor: "var(--theme-primary)",
          opacity: 0.4,
        }}
      />
      <div
        ref={isSidebar ? panelRef : undefined}
        className={`w-full flex flex-col bg-white dark:bg-[#1e1e1e] pointer-events-auto ${
          isSidebar
            ? "h-full sm:rounded-l-2xl relative shadow-[-4px_0_24px_-4px_rgba(0,0,0,0.12)] dark:shadow-[-4px_0_24px_-4px_rgba(0,0,0,0.4)]"
            : `overflow-hidden shadow-2xl ring-1 ring-black/5 dark:ring-white/10 transition-all duration-300 ease-out ${
                isFullscreen
                  ? "h-full sm:h-full sm:max-w-none sm:rounded-none"
                  : "sm:max-w-3xl lg:max-w-4xl h-full sm:h-[80vh] sm:rounded-2xl"
              }`
        }`}
        {...(isSidebar ? { "data-sidebar-panel": "" } : {})}
        style={
          isSidebar
            ? { maxWidth: "100%", minWidth: "min(320px, 80vw)" }
            : undefined
        }
        onClick={(e) => e.stopPropagation()}
      >
        {/* Resize handle — outside overflow-hidden */}
        {isSidebar && (
          <div
            className="hidden sm:block absolute left-0 top-0 bottom-0 -translate-x-1/2 z-10 cursor-col-resize pointer-events-auto group"
            onMouseDown={handleResizeStart}
          >
            <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-1 rounded-full bg-transparent group-hover:bg-[var(--theme-primary)]/50 transition-colors duration-200" />
          </div>
        )}
        {/* Header */}
        <div className="flex items-center gap-2 sm:gap-3 px-3 sm:px-5 py-3 sm:py-4 border-b border-stone-200 dark:border-[#333] shrink-0 bg-gradient-to-r from-stone-50 to-white dark:from-[#252526] dark:to-[#1e1e1e] whitespace-nowrap">
          {/* File Icon */}
          <FileIcon icon={Icon} bg={fileInfo.bg} color={fileInfo.color} />
          {/* File Info */}
          <div className="flex-1 min-w-[120px] sm:min-w-[180px]">
            <h3
              className="font-bold text-stone-900 dark:text-stone-100 text-sm sm:text-base"
              title={fileName}
            >
              <span className="block truncate">{fileName}</span>
            </h3>
            <div className="flex items-center gap-1.5 sm:gap-2 text-xs text-stone-500 dark:text-stone-400">
              {codeFile && (
                <span className="px-1.5 py-0.5 rounded bg-stone-100 dark:bg-[#2d2d30] font-mono text-xs sm:text-xs">
                  {language}
                </span>
              )}
              <span className="text-xs sm:text-xs">
                {!hasTextContent
                  ? t("documents.binary")
                  : t("documents.chars", { count: displaySize })}
              </span>
            </div>
          </div>
          {/* Actions */}
          <div className="flex items-center gap-0.5 sm:gap-1 relative z-10 shrink-0">
            {/* Source/Preview toggle for markdown files */}
            {markdownFile && data?.content && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setViewSource(!viewSource);
                }}
                className="flex items-center justify-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-2 sm:py-2 rounded-xl text-xs sm:text-sm font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-200/80 dark:hover:bg-stone-700/60 active:bg-stone-200 dark:active:bg-stone-600/60 transition-all duration-200 active:scale-95 cursor-pointer"
                title={
                  viewSource ? t("documents.preview") : t("documents.source")
                }
              >
                {viewSource ? (
                  <>
                    <Eye size={16} />
                    {!hideBtnLabels && (
                      <span className="hidden sm:inline">
                        {t("documents.preview")}
                      </span>
                    )}
                  </>
                ) : (
                  <>
                    <Code2 size={16} />
                    {!hideBtnLabels && (
                      <span className="hidden sm:inline">
                        {t("documents.source")}
                      </span>
                    )}
                  </>
                )}
              </button>
            )}
            {/* Sidebar / Center view toggle - desktop only */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setViewMode(isSidebar ? "center" : "sidebar");
              }}
              className="flex items-center justify-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-2 sm:py-2 rounded-xl text-xs sm:text-sm font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-200/80 dark:hover:bg-stone-700/60 active:bg-stone-200 dark:active:bg-stone-600/60 transition-all duration-200 active:scale-95 cursor-pointer"
              title={
                isSidebar
                  ? t("documents.centerView", "Center view")
                  : t("documents.sidebarView", "Sidebar view")
              }
            >
              {isSidebar ? (
                <>
                  <Maximize size={16} />
                  {!hideBtnLabels && (
                    <span className="hidden sm:inline">
                      {t("documents.centerView")}
                    </span>
                  )}
                </>
              ) : (
                <>
                  <PanelRight size={16} />
                  {!hideBtnLabels && (
                    <span className="hidden sm:inline">
                      {t("documents.sidebarView")}
                    </span>
                  )}
                </>
              )}
            </button>
            {/* Fullscreen button - desktop only */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setIsFullscreen(!isFullscreen);
              }}
              className="flex items-center justify-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-2 sm:py-2 rounded-xl text-xs sm:text-sm font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-200/80 dark:hover:bg-stone-700/60 active:bg-stone-200 dark:active:bg-stone-600/60 transition-all duration-200 active:scale-95 cursor-pointer"
              title={
                isFullscreen
                  ? t("documents.exitFullscreen")
                  : t("documents.fullscreen")
              }
            >
              {isFullscreen ? (
                <>
                  <Minimize2 size={16} />
                  {!hideBtnLabels && (
                    <span className="hidden sm:inline">
                      {t("documents.exitFullscreen")}
                    </span>
                  )}
                </>
              ) : (
                <>
                  <Maximize2 size={16} />
                  {!hideBtnLabels && (
                    <span className="hidden sm:inline">
                      {t("documents.fullscreen")}
                    </span>
                  )}
                </>
              )}
            </button>
            {(data?.content ||
              s3Key ||
              signedUrl ||
              externalImageUrl ||
              resolvedUrl) && (
              <>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDownload();
                  }}
                  className="flex items-center justify-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-2 sm:py-2 rounded-xl text-xs sm:text-sm font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-200/80 dark:hover:bg-stone-700/60 active:bg-stone-200 dark:active:bg-stone-600/60 transition-all duration-200 active:scale-95 cursor-pointer"
                  title={t("documents.download")}
                >
                  <Download size={16} />
                  {!hideBtnLabels && (
                    <span className="hidden sm:inline">
                      {t("documents.download")}
                    </span>
                  )}
                </button>
                {data?.content && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCopy();
                    }}
                    className="flex items-center justify-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-2 sm:py-2 rounded-xl text-xs sm:text-sm font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-200/80 dark:hover:bg-stone-700/60 active:bg-stone-200 dark:active:bg-stone-600/60 transition-all duration-200 active:scale-95 cursor-pointer"
                  >
                    {copied ? (
                      <>
                        <Check
                          size={16}
                          className="text-green-500 dark:text-green-400"
                        />
                        {!hideBtnLabels && (
                          <span className="text-green-500 dark:text-green-400 hidden sm:inline">
                            {t("documents.copied")}
                          </span>
                        )}
                      </>
                    ) : (
                      <>
                        <Copy size={16} />
                        {!hideBtnLabels && (
                          <span className="hidden sm:inline">
                            {t("documents.copy")}
                          </span>
                        )}
                      </>
                    )}
                  </button>
                )}
              </>
            )}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onClose();
              }}
              className="flex items-center justify-center w-9 h-9 sm:w-9 sm:h-9 rounded-xl hover:bg-stone-200/80 dark:hover:bg-stone-700/60 active:bg-stone-200 dark:active:bg-stone-600/60 transition-all duration-200 active:scale-95 cursor-pointer"
              aria-label={t("common.close")}
            >
              <X size={20} className="text-stone-500 dark:text-stone-400" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto min-h-0">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 sm:py-20 gap-4">
              <div className="relative">
                <LoadingSpinner size="lg" />
                <div className="absolute inset-0 animate-ping">
                  <LoadingSpinner size="lg" static />
                </div>
              </div>
              <p className="text-sm text-stone-500 dark:text-stone-400 font-medium">
                {t("documents.loadingFileContent")}
              </p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-16 sm:py-20 gap-4 px-4">
              <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-red-100 dark:bg-red-900/30">
                <AlertCircle size={28} className="text-red-500" />
              </div>
              <div className="text-center">
                <p className="text-sm text-red-600 dark:text-red-400 font-medium mb-2">
                  {error}
                </p>
                <p className="text-xs text-stone-400 dark:text-stone-500">
                  {t("documents.unableToLoadContent")}
                </p>
              </div>
            </div>
          ) : binaryFile && !imageFile && !pdfFile && !videoFile ? (
            <div className="flex flex-col items-center justify-center py-16 sm:py-20 gap-4 px-4">
              <div
                className={`flex items-center justify-center w-20 h-20 rounded-2xl ${fileInfo.bg}`}
              >
                <Icon size={36} className={fileInfo.color} />
              </div>
              <div className="text-center">
                <p className="text-sm text-stone-700 dark:text-stone-300 font-medium mb-2">
                  {t("documents.binaryFilePreview")}
                </p>
                <p className="text-xs text-stone-400 dark:text-stone-500 max-w-sm">
                  {t("documents.binaryFileHint")}
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDownload();
                }}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-white font-medium text-sm transition-all duration-200 active:scale-95 cursor-pointer"
              >
                <Download size={16} />
                {t("documents.downloadFile")}
              </button>
            </div>
          ) : pdfFile ? (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full min-h-[400px]">
                  <LoadingSpinner size="lg" />
                </div>
              }
            >
              <div className="h-full min-h-[400px]">
                {pdfUrl && <PdfPreview url={pdfUrl} />}
              </div>
            </Suspense>
          ) : videoFile && videoUrl ? (
            <div className="flex items-center justify-center h-full bg-gradient-to-b from-stone-900 to-stone-950 min-h-[400px] p-4 sm:p-8">
              <div className="relative w-full max-w-4xl mx-auto">
                <video
                  controls
                  autoPlay={false}
                  className="w-full max-h-[65vh] rounded-xl shadow-2xl ring-1 ring-white/10"
                  src={videoUrl}
                  style={{ margin: "0 auto", display: "block" }}
                >
                  <track kind="captions" />
                  {t("documents.videoNotSupported")}
                </video>
              </div>
            </div>
          ) : pptFile && (pptUrl || pptxBuffer) ? (
            <div className="h-full min-h-[400px]">
              <PptPreview
                url={pptUrl || ""}
                arrayBuffer={pptxBuffer}
                fileName={fileName}
                t={t}
              />
            </div>
          ) : htmlFile && htmlUrl ? (
            <div className="h-full min-h-[400px]">
              <HtmlPreview content={htmlContent} />
            </div>
          ) : legacyDocFile && docUrl ? (
            <div className="flex flex-col items-center justify-center h-full min-h-[400px] p-4 sm:p-6">
              <div className="max-w-sm sm:max-w-md w-full text-center">
                <div className="flex items-center justify-center w-20 h-20 rounded-2xl bg-blue-100 dark:bg-blue-900/40 mx-auto mb-4">
                  <Icon
                    size={36}
                    className="text-blue-600 dark:text-blue-400"
                  />
                </div>
                <h3 className="text-base font-medium text-stone-700 dark:text-stone-200 mb-2">
                  {t("documents.docNotSupported") || "不支持预览旧版 Word 文档"}
                </h3>
                <p className="text-sm text-stone-500 dark:text-stone-400 mb-6">
                  {t("documents.docConvertHint") ||
                    "该文件为旧版 .doc 格式，请将其转换为 .docx 格式后预览，或直接下载文件。"}
                </p>
                <button
                  onClick={handleDownload}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  <Download size={16} />
                  {t("documents.download") || "下载文件"}
                </button>
              </div>
            </div>
          ) : wordFile && arrayBuffer ? (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full min-h-[400px]">
                  <LoadingSpinner size="lg" />
                </div>
              }
            >
              <WordPreview arrayBuffer={arrayBuffer} t={t} />
            </Suspense>
          ) : excelFile && arrayBuffer ? (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full min-h-[400px]">
                  <LoadingSpinner size="lg" />
                </div>
              }
            >
              <ExcelPreview
                arrayBuffer={arrayBuffer}
                fileName={fileName}
                t={t}
              />
            </Suspense>
          ) : imageFile || imageUrl ? (
            <>
              <div className="flex items-center justify-center p-4 sm:p-8 bg-stone-50 dark:bg-stone-800/50 min-h-[200px] overflow-auto">
                <img
                  src={imageUrl || `data:image/${ext};base64,${data?.content}`}
                  alt={fileName}
                  className={`rounded-lg shadow-lg object-contain cursor-pointer hover:opacity-90 transition-opacity ${
                    isFullscreen
                      ? "max-w-full max-h-full"
                      : "max-w-full max-h-[50vh] sm:max-h-[60vh]"
                  }`}
                  onClick={(e) => {
                    e.stopPropagation();
                    setShowImageViewer(true);
                  }}
                />
              </div>
              {showImageViewer && (
                <ImageViewer
                  isOpen={showImageViewer}
                  src={imageUrl || `data:image/${ext};base64,${data?.content}`}
                  onClose={() => setShowImageViewer(false)}
                />
              )}
            </>
          ) : excalidrawFile && excalidrawData ? (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full">
                  <LoadingSpinner size="lg" />
                </div>
              }
            >
              <div className="h-full min-h-[400px] max-h-full overflow-hidden">
                <ExcalidrawPreview data={excalidrawData} />
              </div>
            </Suspense>
          ) : markdownFile ? (
            viewSource ? (
              <PlainTextViewer content={data?.content || ""} />
            ) : (
              <MarkdownRenderer content={data?.content || ""} _t={t} />
            )
          ) : (
            <CodeRenderer
              content={data?.content || ""}
              language={language}
              t={t}
            />
          )}
        </div>

        {/* Footer - simplified on mobile */}
        <div className="px-3 sm:px-5 py-2 sm:py-3 border-t border-stone-200 dark:border-[#333] bg-stone-50 dark:bg-[#252526]">
          <div className="flex items-center justify-between text-xs sm:text-xs text-stone-400 dark:text-stone-500">
            <div className="flex items-center gap-1.5 sm:gap-2 min-w-0 flex-1">
              <span className="font-medium text-stone-500 dark:text-stone-400 hidden xs:inline">
                {t("documents.path")}:
              </span>
              <span className="font-mono text-stone-600 dark:text-stone-300 truncate text-xs sm:text-xs">
                {path}
              </span>
            </div>
            <div className="flex items-center gap-1 shrink-0 ml-2">
              <span className="hidden sm:inline">
                {t("documents.pressEscToClose")}
              </span>
            </div>
          </div>
        </div>

        {/* Safe area for mobile */}
        <div className="h-safe-area-inset-bottom bg-stone-50 dark:bg-[#252526] sm:hidden" />
      </div>
    </div>,
    document.body,
  );
}
