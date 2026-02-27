import { useState, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  X,
  Loader2,
  AlertCircle,
  Copy,
  Check,
  Download,
  ChevronDown,
  Maximize2,
  Minimize2,
} from "lucide-react";
import { uploadApi } from "../../services/api";

// Import utilities
import {
  getFileExtension,
  isBinaryFile,
  isImageFile,
  isPdfFile,
  isWordFile,
  isExcelFile,
  isPptFile,
  isHtmlFile,
  isCodeFile,
  isMarkdownFile,
  isPreviewableFile,
  getFileTypeColor,
  detectLanguage,
} from "./utils";

// Import preview components
import CodeRenderer from "./previews/CodeRenderer";
import MarkdownRenderer from "./previews/MarkdownRenderer";
import PdfPreview from "./previews/PdfPreview";
import PptPreview from "./previews/PptPreview";
import WordPreview from "./previews/WordPreview";
import ExcelPreview from "./previews/ExcelPreview";
import HtmlPreview from "./previews/HtmlPreview";

// Re-export utilities for external use
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
  getFileTypeColor,
  detectLanguage,
} from "./utils";

// Export components for external use
export { default as CodeRenderer } from "./previews/CodeRenderer";
export { default as MarkdownRenderer } from "./previews/MarkdownRenderer";
export { default as PdfPreview } from "./previews/PdfPreview";
export { default as PptPreview } from "./previews/PptPreview";
export { default as WordPreview } from "./previews/WordPreview";
export { default as ExcelPreview } from "./previews/ExcelPreview";
export { default as HtmlPreview } from "./previews/HtmlPreview";

interface DocumentPreviewProps {
  path: string;
  content?: string; // File content passed from parent (from agent events)
  s3Key?: string; // S3 object key for fetching content via signed URL
  fileSize?: number; // File size in bytes
  onClose: () => void;
}

export default function DocumentPreview({
  path,
  content,
  s3Key,
  fileSize,
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
  const [htmlUrl, setHtmlUrl] = useState<string | null>(null);
  const [htmlContent, setHtmlContent] = useState<string>("");
  const [arrayBuffer, setArrayBuffer] = useState<ArrayBuffer | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const fileName = path.split("/").pop() || path;
  const ext = getFileExtension(fileName);
  const binaryFile = isBinaryFile(ext);
  const imageFile = isImageFile(fileName);
  const pdfFile = isPdfFile(ext);
  const wordFile = isWordFile(ext);
  const excelFile = isExcelFile(ext);
  const pptFile = isPptFile(ext);
  const htmlFile = isHtmlFile(ext);
  const codeFile = isCodeFile(ext);
  const markdownFile = isMarkdownFile(fileName);
  const previewable = isPreviewableFile(ext);

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
      !htmlFile
    );
  }, [data?.content, binaryFile, wordFile, excelFile, pptFile, htmlFile]);

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
    setHtmlUrl(null);
    setHtmlContent("");
    setArrayBuffer(null);

    const loadContent = async () => {
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

      // 如果有 s3Key，从 S3 获取内容
      if (s3Key) {
        try {
          const signedUrl = await uploadApi.getSignedUrl(s3Key);

          // 图片文件直接使用签名 URL
          if (imageFile) {
            setImageUrl(signedUrl);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          // PDF 文件使用 iframe 嵌入
          if (pdfFile) {
            setPdfUrl(signedUrl);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          // PPT 文件使用 Office Online viewer 嵌入
          if (pptFile) {
            setPptUrl(signedUrl);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          // HTML 文件使用 iframe 嵌入
          if (htmlFile) {
            setHtmlUrl(signedUrl);
            // 同时获取内容用于查看源代码
            try {
              const response = await fetch(signedUrl);
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

          // 其他文件获取内容
          const response = await fetch(signedUrl);
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
              a.href = signedUrl;
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
  }, [
    path,
    content,
    s3Key,
    imageFile,
    pdfFile,
    pptFile,
    htmlFile,
    binaryFile,
    wordFile,
    excelFile,
    t,
  ]);

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

  // Lock body scroll
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  const handleCopy = async () => {
    if (data?.content) {
      await navigator.clipboard.writeText(data.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = async () => {
    // 优先使用 S3 签名 URL 下载
    if (s3Key) {
      try {
        const signedUrl = await uploadApi.getSignedUrl(s3Key);
        const a = document.createElement("a");
        a.href = signedUrl;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } catch (err) {
        console.error("Failed to download file:", err);
      }
      return;
    }

    // 没有 s3Key 时，使用内存中的内容下载
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

  const colors = getFileTypeColor(fileName);
  const Icon = colors.icon;

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex flex-col sm:items-center sm:justify-center bg-black/70"
      onClick={onClose}
    >
      <div
        className={`w-full flex flex-col bg-white dark:bg-stone-900 shadow-2xl overflow-hidden ring-1 ring-black/5 dark:ring-white/10 ${
          isFullscreen
            ? "h-full sm:h-full sm:max-w-none sm:rounded-none"
            : "sm:max-w-3xl lg:max-w-4xl h-full sm:h-[80vh] sm:rounded-2xl"
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-2 sm:gap-3 px-3 sm:px-5 py-3 sm:py-4 border-b border-stone-200 dark:border-stone-800 shrink-0 bg-gradient-to-r from-stone-50 to-white dark:from-stone-900 dark:to-stone-900">
          {/* File Icon */}
          <div
            className={`flex items-center justify-center w-10 h-10 sm:w-11 sm:h-11 rounded-xl ${colors.bg}`}
          >
            <Icon
              size={20}
              className={`sm:w-[22px] sm:h-[22px] ${colors.color}`}
            />
          </div>
          {/* File Info */}
          <div className="flex-1 min-w-0">
            <h3
              className="font-bold text-stone-900 dark:text-stone-100 text-sm sm:text-base"
              title={fileName}
            >
              <span className="filename-truncate block">{fileName}</span>
            </h3>
            <div className="flex items-center gap-1.5 sm:gap-2 text-xs text-stone-500 dark:text-stone-400 flex-wrap">
              {codeFile && (
                <span className="px-1.5 py-0.5 rounded bg-stone-100 dark:bg-stone-800 font-mono text-[10px] sm:text-xs">
                  {language}
                </span>
              )}
              <span className="text-[11px] sm:text-xs">
                {!hasTextContent
                  ? t("documents.binary")
                  : t("documents.chars", { count: displaySize })}
              </span>
            </div>
          </div>
          {/* Actions */}
          <div className="flex items-center gap-0.5 sm:gap-1 relative z-10">
            {/* Fullscreen button - desktop only */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setIsFullscreen(!isFullscreen);
              }}
              className="hidden sm:flex items-center justify-center w-9 h-9 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-all duration-200 active:scale-95 cursor-pointer"
              title={
                isFullscreen
                  ? t("documents.exitFullscreen")
                  : t("documents.fullscreen")
              }
            >
              {isFullscreen ? (
                <Minimize2
                  size={18}
                  className="text-stone-500 dark:text-stone-400"
                />
              ) : (
                <Maximize2
                  size={18}
                  className="text-stone-500 dark:text-stone-400"
                />
              )}
            </button>
            {(data?.content || s3Key) && (
              <>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDownload();
                  }}
                  className="flex items-center justify-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-2 sm:py-2 rounded-xl text-xs sm:text-sm font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-all duration-200 active:scale-95 cursor-pointer"
                  title={t("documents.download")}
                >
                  <Download size={16} />
                  <span className="hidden sm:inline">
                    {t("documents.download")}
                  </span>
                </button>
                {data?.content && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCopy();
                    }}
                    className="flex items-center justify-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-2 sm:py-2 rounded-xl text-xs sm:text-sm font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-all duration-200 active:scale-95 cursor-pointer"
                  >
                    {copied ? (
                      <>
                        <Check size={16} className="text-green-500" />
                        <span className="text-green-500 hidden sm:inline">
                          {t("documents.copied")}
                        </span>
                      </>
                    ) : (
                      <>
                        <Copy size={16} />
                        <span className="hidden sm:inline">
                          {t("documents.copy")}
                        </span>
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
              className="flex items-center justify-center w-9 h-9 sm:w-9 sm:h-9 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 transition-all duration-200 active:scale-95 cursor-pointer"
              aria-label={t("common.close")}
            >
              <ChevronDown
                size={24}
                className="sm:hidden text-stone-500 dark:text-stone-400"
              />
              <X
                size={18}
                className="hidden sm:block text-stone-500 dark:text-stone-400"
              />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto min-h-0">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 sm:py-20 gap-4">
              <div className="relative">
                <Loader2 size={32} className="animate-spin text-amber-500" />
                <div className="absolute inset-0 animate-ping">
                  <Loader2 size={32} className="text-amber-500/30" />
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
          ) : binaryFile && !imageFile && !pdfFile ? (
            <div className="flex flex-col items-center justify-center py-16 sm:py-20 gap-4 px-4">
              <div
                className={`flex items-center justify-center w-20 h-20 rounded-2xl ${colors.bg}`}
              >
                <Icon size={36} className={colors.color} />
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
            <div className="h-full min-h-[400px]">
              {pdfUrl && <PdfPreview url={pdfUrl} />}
            </div>
          ) : pptFile && pptUrl ? (
            <div className="h-full min-h-[400px]">
              <PptPreview url={pptUrl} />
            </div>
          ) : htmlFile && htmlUrl ? (
            <div className="h-full min-h-[400px]">
              <HtmlPreview content={htmlContent} />
            </div>
          ) : wordFile && arrayBuffer ? (
            <WordPreview arrayBuffer={arrayBuffer} t={t} />
          ) : excelFile && arrayBuffer ? (
            <ExcelPreview arrayBuffer={arrayBuffer} fileName={fileName} t={t} />
          ) : imageFile ? (
            <div className="flex items-center justify-center p-4 sm:p-8 bg-stone-50 dark:bg-stone-800/50 min-h-[200px] overflow-auto">
              <img
                src={imageUrl || `data:image/${ext};base64,${data?.content}`}
                alt={fileName}
                className={`rounded-lg shadow-lg object-contain cursor-pointer hover:opacity-90 transition-opacity ${
                  isFullscreen
                    ? "max-w-full max-h-full"
                    : "max-w-full max-h-[50vh] sm:max-h-[60vh]"
                }`}
                onClick={(e) => e.stopPropagation()}
              />
            </div>
          ) : markdownFile ? (
            <div className="p-4 sm:p-6 lg:p-8">
              <MarkdownRenderer content={data?.content || ""} t={t} />
            </div>
          ) : (
            <CodeRenderer
              content={data?.content || ""}
              language={language}
              t={t}
            />
          )}
        </div>

        {/* Footer - simplified on mobile */}
        <div className="px-3 sm:px-5 py-2 sm:py-3 border-t border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-900">
          <div className="flex items-center justify-between text-[10px] sm:text-xs text-stone-400 dark:text-stone-500">
            <div className="flex items-center gap-1.5 sm:gap-2 min-w-0 flex-1">
              <span className="font-medium text-stone-500 dark:text-stone-400 hidden xs:inline">
                {t("documents.path")}:
              </span>
              <span className="font-mono text-stone-600 dark:text-stone-300 truncate text-[11px] sm:text-xs">
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
        <div className="h-safe-area-inset-bottom bg-stone-50 dark:bg-stone-900 sm:hidden" />
      </div>
    </div>,
    document.body,
  );
}
