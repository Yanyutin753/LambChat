import {
  useState,
  useEffect,
  useMemo,
  useRef,
  useCallback,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { uploadApi } from "../../services/api";
import {
  buildUploadProxyUrl,
  buildUploadProxyUrlFromKey,
  getFullUrl,
} from "../../services/api/config";
import {
  getSidebarHistoryLength,
  goBackSidebar,
  subscribeSidebarHistory,
} from "../chat/ChatMessage/items/sidebarHistoryStore";
import {
  fetchDocumentArrayBuffer,
  fetchDocumentText,
} from "./documentFetchCache";
import {
  getFileExtension,
  isBinaryFile,
  isImageFile,
  isPdfFile,
  isWordPreviewFile,
  isLegacyDocFile,
  isExcelFile,
  isPptFile,
  isCadFile,
  isDxfFile,
  isDwgFile,
  isHtmlFile,
  isCodeFile,
  isMarkdownFile,
  isExcalidrawFile,
  isVideoFile,
  isAudioFile,
  getFileTypeInfo,
  detectLanguage,
} from "./utils";
import { copyToClipboard } from "../../utils/clipboard";
import {
  isProjectPreviewFullscreen,
  requestProjectPreviewFullscreen,
} from "../chat/ChatMessage/items/projectPreviewFullscreen";
import {
  hasFileViewerContribution,
  type PluginRuntimeContributionStates,
} from "../../extensions/coreContributions";
import { hasPluginAssetSlot } from "../../extensions/pluginAssetSlots";

export interface DocumentPreviewProps {
  path: string;
  content?: string;
  s3Key?: string;
  signedUrl?: string;
  fileSize?: number;
  imageUrl?: string;
  mimeType?: string;
  initialLine?: number;
  onClose: () => void;
  onUserInteraction?: () => void;
  registryKey?: string;
  onBack?: () => void;
  mobileFillViewport?: boolean;
  footer?: ReactNode;
  runtimePlugins?: PluginRuntimeContributionStates;
}

export function useDocumentPreviewState(props: DocumentPreviewProps) {
  const {
    path,
    content,
    s3Key,
    signedUrl,
    fileSize,
    imageUrl: externalImageUrl,
    mimeType,
    onBack,
    runtimePlugins,
  } = props;

  const { t } = useTranslation();

  // Sidebar history
  const [historyAvailable, setHistoryAvailable] = useState(
    () => getSidebarHistoryLength() > 0,
  );
  useEffect(() => {
    return subscribeSidebarHistory(() => {
      setHistoryAvailable(getSidebarHistoryLength() > 0);
    });
  }, []);
  const effectiveOnBack =
    onBack ?? (historyAvailable ? goBackSidebar : undefined);

  // Data state
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
  const [cadUrl, setCadUrl] = useState<string | null>(null);
  const [cadKind, setCadKind] = useState<"dxf" | "dwg" | null>(null);
  const [htmlUrl, setHtmlUrl] = useState<string | null>(null);
  const [htmlContent, setHtmlContent] = useState<string>("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [docUrl, setDocUrl] = useState<string | null>(null);
  const [arrayBuffer, setArrayBuffer] = useState<ArrayBuffer | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const isFullscreenRef = useRef(false);
  // Keep ref in sync for use in callbacks without stale closures
  useEffect(() => {
    isFullscreenRef.current = isFullscreen;
  }, [isFullscreen]);

  const panelRef = useRef<HTMLDivElement | null>(null);

  // Sync with browser Fullscreen API (targets the panel element)
  useEffect(() => {
    const syncFullscreenState = () => {
      setIsFullscreen(
        isProjectPreviewFullscreen({ element: panelRef.current }),
      );
    };
    syncFullscreenState();
    document.addEventListener("fullscreenchange", syncFullscreenState);
    return () =>
      document.removeEventListener("fullscreenchange", syncFullscreenState);
  }, []);

  const handleFullscreenToggle = useCallback(() => {
    if (document.fullscreenElement) {
      // Browser is fullscreen — exit
      document.exitFullscreen?.().catch(() => {});
    } else if (isFullscreenRef.current) {
      // CSS-only fullscreen — exit
      setIsFullscreen(false);
    } else {
      // Enter fullscreen — try browser API first, fall back to CSS-only
      void requestProjectPreviewFullscreen({ element: panelRef.current }).then(
        (entered) => {
          if (!entered) setIsFullscreen(true);
        },
      );
    }
  }, []);

  const exitFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => {});
    } else {
      setIsFullscreen(false);
    }
  }, []);
  const [showImageViewer, setShowImageViewer] = useState(false);
  const [excalidrawData, setExcalidrawData] = useState<string>("");
  const [viewSource, setViewSource] = useState(false);
  const [viewMode, setViewMode] = useState<"center" | "sidebar">("sidebar");
  const [resolvedUrl, setResolvedUrl] = useState<string | null>(null);
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 640);
  const toolbarRef = useRef<HTMLDivElement>(null);

  // Mobile detection
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // File type detection
  const fileName = path.split("/").pop() || path;
  const ext = getFileExtension(fileName);
  const binaryFile = isBinaryFile(ext);
  const imageFile = isImageFile(ext);
  const pdfFile = isPdfFile(ext);
  const wordPreviewFile = isWordPreviewFile(ext);
  const legacyDocFile = isLegacyDocFile(ext);
  const excelFile = isExcelFile(ext);
  const pptFile = isPptFile(ext);
  const cadFile = isCadFile(ext);
  const dxfFile = isDxfFile(ext);
  const dwgFile = isDwgFile(ext);
  const htmlFile = isHtmlFile(ext);
  const codeFile = isCodeFile(ext);
  const markdownFile = isMarkdownFile(fileName);
  const excalidrawFile = isExcalidrawFile(ext);
  const videoFile = isVideoFile(ext);
  const audioFile = isAudioFile(ext);
  const advancedFileViewersEnabled =
    hasFileViewerContribution("code", runtimePlugins) &&
    hasPluginAssetSlot("file_viewer", runtimePlugins);

  // MIME-based fallback
  const mime = mimeType?.toLowerCase();
  const resolvedImageFile = imageFile || !!mime?.startsWith("image/");
  const resolvedVideoFile = videoFile || !!mime?.startsWith("video/");
  const resolvedAudioFile = audioFile || !!mime?.startsWith("audio/");
  const resolvedPdfFile = pdfFile || mime === "application/pdf";
  const resolvedBinaryFile =
    binaryFile && !resolvedVideoFile && !resolvedAudioFile;
  const hasSupportedPreview =
    resolvedImageFile ||
    resolvedVideoFile ||
    resolvedAudioFile ||
    (advancedFileViewersEnabled &&
      (resolvedPdfFile ||
        cadFile ||
        pptFile ||
        htmlFile ||
        wordPreviewFile ||
        excelFile ||
        excalidrawFile ||
        markdownFile ||
        codeFile));
  const unsupportedPreviewFile = !hasSupportedPreview && !resolvedBinaryFile;

  // Memoized values
  const language = useMemo(() => detectLanguage(fileName), [fileName]);

  const hasTextContent = useMemo(() => {
    return !!(
      data?.content &&
      !unsupportedPreviewFile &&
      !resolvedBinaryFile &&
      (!advancedFileViewersEnabled ||
        (!excelFile && !pptFile && !cadFile && !htmlFile && !excalidrawFile))
    );
  }, [
    advancedFileViewersEnabled,
    data?.content,
    unsupportedPreviewFile,
    resolvedBinaryFile,
    excelFile,
    pptFile,
    cadFile,
    htmlFile,
    excalidrawFile,
  ]);

  const displaySize = useMemo(() => {
    if (!hasTextContent && fileSize) {
      return fileSize;
    }
    return data?.content?.length || 0;
  }, [hasTextContent, fileSize, data?.content]);

  // Content loading
  useEffect(() => {
    setLoading(true);
    setError(null);
    setImageUrl(null);
    setPdfUrl(null);
    setPptUrl(null);
    setPptxBuffer(null);
    setCadUrl(null);
    setCadKind(null);
    setHtmlUrl(null);
    setHtmlContent("");
    setVideoUrl(null);
    setAudioUrl(null);
    setArrayBuffer(null);
    setExcalidrawData("");
    setResolvedUrl(null);

    const loadContent = async () => {
      if (externalImageUrl) {
        setImageUrl(externalImageUrl);
        setData({ content: "", path });
        setLoading(false);
        return;
      }

      if (content !== undefined && !(pptFile && (s3Key || signedUrl))) {
        if (unsupportedPreviewFile) {
          setData({ content, path });
          setLoading(false);
          return;
        }

        if (advancedFileViewersEnabled && dxfFile) {
          const blob = new Blob([content], { type: "text/plain" });
          const url = URL.createObjectURL(blob);
          setCadUrl(url);
          setCadKind("dxf");
          setData({ content: "", path });
          setLoading(false);
          return;
        }

        if (advancedFileViewersEnabled && dwgFile) {
          setCadKind("dwg");
          setData({ content: "", path });
          setLoading(false);
          return;
        }

        if (advancedFileViewersEnabled && htmlFile) {
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

      if (s3Key || signedUrl) {
        try {
          const resolvedSignedUrl = getFullUrl(signedUrl) || signedUrl;
          const url =
            resolvedSignedUrl ||
            (s3Key
              ? buildUploadProxyUrlFromKey(s3Key) ||
                (await uploadApi.getSignedUrl(s3Key))
              : null);

          if (!url) {
            throw new Error("No URL available");
          }

          setResolvedUrl(url);
          const readUrl = buildUploadProxyUrl(url) || url;

          if (resolvedImageFile) {
            setImageUrl(url);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          if (advancedFileViewersEnabled && resolvedPdfFile) {
            const buffer = await fetchDocumentArrayBuffer(readUrl);
            const blob = new Blob([buffer], { type: "application/pdf" });
            const previewUrl = URL.createObjectURL(blob);
            setPdfUrl(previewUrl);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          if (resolvedVideoFile) {
            setVideoUrl(url);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          if (resolvedAudioFile) {
            setAudioUrl(url);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          if (advancedFileViewersEnabled && cadFile) {
            setCadUrl(readUrl);
            setCadKind(dxfFile ? "dxf" : "dwg");
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          if (advancedFileViewersEnabled && pptFile) {
            const buffer = await fetchDocumentArrayBuffer(readUrl);
            setPptxBuffer(buffer);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          if (advancedFileViewersEnabled && htmlFile) {
            setHtmlUrl(url);
            try {
              const text = await fetchDocumentText(readUrl);
              setHtmlContent(text);
            } catch (e) {
              console.error("Failed to fetch HTML content:", e);
            }
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          if (advancedFileViewersEnabled && excalidrawFile) {
            const text = await fetchDocumentText(readUrl);
            setExcalidrawData(text);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          if (legacyDocFile) {
            setDocUrl(url);
            setData({ content: "", path });
            setLoading(false);
            return;
          }

          if (resolvedBinaryFile) {
            setData({ content: "", path });
          } else if (unsupportedPreviewFile) {
            setData({ content: "", path });
          } else if (advancedFileViewersEnabled && (wordPreviewFile || excelFile)) {
            const buffer = await fetchDocumentArrayBuffer(readUrl);
            setArrayBuffer(buffer);
            setData({ content: "", path });
          } else {
            const text = await fetchDocumentText(readUrl);
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

      setError(t("documents.noContent", "文件内容不可用"));
      setLoading(false);
    };

    loadContent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    path,
    content,
    s3Key,
    signedUrl,
    externalImageUrl,
    mimeType,
    advancedFileViewersEnabled,
  ]);

  // Blob URL cleanup
  useEffect(() => {
    return () => {
      if (htmlUrl?.startsWith("blob:")) {
        URL.revokeObjectURL(htmlUrl);
      }
      if (cadUrl?.startsWith("blob:")) {
        URL.revokeObjectURL(cadUrl);
      }
      if (pdfUrl?.startsWith("blob:")) {
        URL.revokeObjectURL(pdfUrl);
      }
    };
  }, [cadUrl, htmlUrl, pdfUrl]);

  // Action handlers
  const handleCopy = async () => {
    if (data?.content) {
      await copyToClipboard(data.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = async () => {
    const downloadUrl =
      getFullUrl(signedUrl) || resolvedUrl || getFullUrl(externalImageUrl);
    if (downloadUrl) {
      try {
        const response = await fetch(
          buildUploadProxyUrl(downloadUrl) || downloadUrl,
        );
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
        window.open(downloadUrl, "_blank");
      }
      return;
    }

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

  // Computed values
  const fileInfo = getFileTypeInfo(fileName, mimeType);
  const Icon = fileInfo.icon;
  const isSidebar = viewMode === "sidebar";

  return {
    // Props
    path,
    initialLine: props.initialLine,
    onClose: props.onClose,
    onUserInteraction: props.onUserInteraction,
    registryKey: props.registryKey,
    mobileFillViewport: props.mobileFillViewport,
    footer: props.footer,
    s3Key,
    signedUrl,
    externalImageUrl,

    // Translation
    t,

    // Data state
    data,
    loading,
    error,
    copied,
    imageUrl,
    pdfUrl,
    pptUrl,
    pptxBuffer,
    cadUrl,
    cadKind,
    htmlUrl,
    htmlContent,
    videoUrl,
    audioUrl,
    docUrl,
    arrayBuffer,
    excalidrawData,
    resolvedUrl,
    showImageViewer,
    viewSource,
    viewMode,
    isFullscreen,
    isMobile,

    // File type flags
    fileName,
    ext,
    codeFile,
    markdownFile,
    htmlFile,
    cadFile,
    pptFile,
    excelFile,
    wordPreviewFile,
    legacyDocFile,
    excalidrawFile,
    resolvedImageFile,
    resolvedVideoFile,
    resolvedAudioFile,
    resolvedPdfFile,
    resolvedBinaryFile,
    unsupportedPreviewFile,
    hasTextContent,
    advancedFileViewersEnabled,

    // Computed
    language,
    displaySize,
    fileInfo,
    Icon,
    isSidebar,

    // Handlers
    effectiveOnBack,
    handleCopy,
    handleDownload,

    // Setters
    setShowImageViewer,
    setViewSource,
    setViewMode,
    handleFullscreenToggle,
    exitFullscreen,

    // Refs
    toolbarRef,
    panelRef,

    // Props for conditional checks
    fileSize,
  };
}

export type DocumentPreviewState = ReturnType<typeof useDocumentPreviewState>;
