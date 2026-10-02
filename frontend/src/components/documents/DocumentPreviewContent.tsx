import { SceneIllustration } from "../common/SceneIllustration";
import { Suspense, lazy } from "react";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { Button } from "../common/ui/Button";
import { ImageViewer } from "../common/ImageViewer";
import { ImageWithSkeleton } from "../chat/ChatMessage/ImageWithSkeleton";
import { mediaProxyFallbackSrc } from "./documentFetchCache";
import CodeRenderer from "./previews/CodeRenderer";
import MarkdownRenderer from "./previews/MarkdownRenderer";
import HtmlPreview from "./previews/HtmlPreview";

const PdfPreview = lazy(() => import("./previews/PdfPreview"));
const PptPreview = lazy(() => import("./previews/PptPreview"));
const WordPreview = lazy(() => import("./previews/WordPreview"));
const ExcelPreview = lazy(() => import("./previews/ExcelPreview"));
const ExcalidrawPreview = lazy(() => import("./previews/ExcalidrawPreview"));
const CadPreview = lazy(() => import("./previews/CadPreview"));
const FileFallbackPanel = lazy(() => import("./previews/FileFallbackPanel"));
import type { DocumentPreviewState } from "./useDocumentPreviewState";

type ContentProps = Pick<
  DocumentPreviewState,
  | "t"
  | "data"
  | "loading"
  | "error"
  | "retryLoad"
  | "imageUrl"
  | "pdfUrl"
  | "pptUrl"
  | "pptxBuffer"
  | "cadUrl"
  | "cadKind"
  | "htmlUrl"
  | "htmlContent"
  | "videoUrl"
  | "audioUrl"
  | "docUrl"
  | "arrayBuffer"
  | "excalidrawData"
  | "showImageViewer"
  | "viewSource"
  | "path"
  | "initialLine"
  | "language"
  | "ext"
  | "fileName"
  | "fileInfo"
  | "Icon"
  | "markdownFile"
  | "htmlFile"
  | "pptFile"
  | "excelFile"
  | "wordPreviewFile"
  | "legacyDocFile"
  | "excalidrawFile"
  | "resolvedImageFile"
  | "resolvedVideoFile"
  | "resolvedAudioFile"
  | "resolvedPdfFile"
  | "resolvedBinaryFile"
  | "unsupportedPreviewFile"
  | "resolvedUrl"
  | "signedUrl"
  | "setShowImageViewer"
>;

export default function DocumentPreviewContent({
  t,
  data,
  loading,
  error,
  retryLoad,
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
  showImageViewer,
  viewSource,
  path,
  initialLine,
  language,
  ext,
  fileName,
  fileInfo,
  Icon,
  markdownFile,
  htmlFile,
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
  resolvedUrl,
  signedUrl,
  setShowImageViewer,
}: ContentProps) {
  const suspenseFallback = (
    <div className="flex items-center justify-center h-full min-h-0">
      <LoadingSpinner size="lg" />
    </div>
  );

  if (loading) {
    return (
      <div className="flex min-h-full flex-col items-center justify-center py-8 gap-4">
        <div className="relative">
          <LoadingSpinner size="lg" color="text-[var(--theme-primary)]" />
          <div className="absolute inset-0 animate-ping">
            <LoadingSpinner
              size="lg"
              static
              color="text-[var(--theme-primary)]"
            />
          </div>
        </div>
        <p
          role="status"
          className="text-14 text-theme-text-secondary font-medium"
        >
          {t("documents.loadingFileContent")}
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-full flex-col items-center justify-center py-8 gap-4 px-4">
        <SceneIllustration scene="files" />
        <div role="alert" className="text-center max-w-md break-words">
          <p className="text-14 text-theme-error font-medium mb-2">{error}</p>
          <p className="text-12 text-theme-text-secondary">
            {t("documents.unableToLoadContent")}
          </p>
        </div>
        {retryLoad && (
          <Button size="lg" onClick={retryLoad}>
            {t("common.retry")}
          </Button>
        )}
      </div>
    );
  }

  if (
    resolvedBinaryFile &&
    !resolvedImageFile &&
    !resolvedPdfFile &&
    !resolvedVideoFile &&
    !resolvedAudioFile
  ) {
    return (
      <Suspense fallback={suspenseFallback}>
        <FileFallbackPanel
          icon={Icon}
          iconBg={fileInfo.bg}
          iconColor={fileInfo.color}
          title={t("documents.binaryFilePreview")}
          description={t("documents.binaryFileHint")}
          downloadUrl={resolvedUrl || signedUrl}
          fileName={fileName}
          downloadLabel={t("documents.downloadFile")}
        />
      </Suspense>
    );
  }

  if (unsupportedPreviewFile) {
    return (
      <Suspense fallback={suspenseFallback}>
        <FileFallbackPanel
          icon={Icon}
          iconBg={fileInfo.bg}
          iconColor={fileInfo.color}
          title={t("documents.unsupportedFilePreview", "暂不支持预览此文件")}
          description={t(
            "documents.unsupportedFileHint",
            "此文件类型暂不支持在线预览，请下载后查看。",
          )}
          downloadUrl={resolvedUrl || signedUrl}
          fileName={fileName}
          downloadLabel={t("documents.downloadFile")}
        />
      </Suspense>
    );
  }

  if (resolvedPdfFile) {
    return (
      <Suspense fallback={suspenseFallback}>
        <div className="h-full min-h-0">
          {pdfUrl && <PdfPreview url={pdfUrl} />}
        </div>
      </Suspense>
    );
  }

  if (resolvedVideoFile && videoUrl) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center overflow-hidden bg-theme-bg-subtle p-4 sm:p-8">
        <div className="relative flex h-full min-h-0 w-full max-w-4xl items-center justify-center mx-auto">
          <video
            controls
            playsInline
            aria-label={fileName}
            autoPlay={false}
            className="h-full w-full max-h-full object-contain"
            src={videoUrl}
            style={{ margin: "0 auto", display: "block" }}
            onError={(e) => {
              const fallback = mediaProxyFallbackSrc(e.currentTarget);
              if (fallback) e.currentTarget.src = fallback;
            }}
          >
            <track kind="captions" />
            {t("documents.videoNotSupported")}
          </video>
        </div>
      </div>
    );
  }

  if (resolvedAudioFile && audioUrl) {
    return (
      <div className="h-full min-h-0 overflow-auto bg-theme-bg-subtle">
        <div className="flex min-h-full items-center justify-center p-4 sm:p-8">
          <audio
            controls
            aria-label={fileName}
            className="w-full max-w-lg"
            src={audioUrl}
            onError={(e) => {
              const fallback = mediaProxyFallbackSrc(e.currentTarget);
              if (fallback) e.currentTarget.src = fallback;
            }}
          >
            {t("documents.audioNotSupported", "您的浏览器不支持音频播放")}
          </audio>
        </div>
      </div>
    );
  }

  if (cadKind) {
    return (
      <Suspense fallback={suspenseFallback}>
        <div className="h-full min-h-0">
          <CadPreview fileName={fileName} kind={cadKind} url={cadUrl} t={t} />
        </div>
      </Suspense>
    );
  }

  if (pptFile && (pptUrl || pptxBuffer)) {
    return (
      <Suspense fallback={suspenseFallback}>
        <div className="h-full min-h-0">
          <PptPreview
            url={resolvedUrl || signedUrl || pptUrl || ""}
            arrayBuffer={pptxBuffer}
            fileName={fileName}
            t={t}
          />
        </div>
      </Suspense>
    );
  }

  if (htmlFile && htmlUrl) {
    return (
      <div className="h-full min-h-0">
        <HtmlPreview content={htmlContent} />
      </div>
    );
  }

  if (legacyDocFile && docUrl) {
    return (
      <Suspense fallback={suspenseFallback}>
        <FileFallbackPanel
          icon={Icon}
          iconBg="bg-blue-100 dark:bg-blue-900/40"
          iconColor="text-blue-600 dark:text-blue-400"
          title={t("documents.docNotSupported") || "不支持预览旧版 Word 文档"}
          description={
            t("documents.docConvertHint") ||
            "该文件为旧版 .doc 格式，请将其转换为 .docx 格式后预览，或直接下载文件。"
          }
          downloadUrl={docUrl}
          fileName={fileName}
          downloadLabel={t("documents.download") || "下载文件"}
        />
      </Suspense>
    );
  }

  if (wordPreviewFile && arrayBuffer) {
    return (
      <Suspense fallback={suspenseFallback}>
        <WordPreview arrayBuffer={arrayBuffer} t={t} />
      </Suspense>
    );
  }

  if (excelFile && arrayBuffer) {
    return (
      <Suspense fallback={suspenseFallback}>
        <ExcelPreview arrayBuffer={arrayBuffer} fileName={fileName} t={t} />
      </Suspense>
    );
  }

  if (resolvedImageFile || imageUrl) {
    return (
      <>
        <div className="flex items-center justify-center p-4 sm:p-8 bg-stone-50 dark:bg-stone-800/50 h-full overflow-auto">
          <ImageWithSkeleton
            src={imageUrl || `data:image/${ext};base64,${data?.content}`}
            alt={fileName}
            skipUrlResolve
            inline
            className="rounded-lg shadow-lg max-w-full max-h-full"
            style={{ cursor: "pointer", objectFit: "contain" }}
            onClick={() => setShowImageViewer(true)}
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
    );
  }

  if (excalidrawFile && excalidrawData) {
    return (
      <Suspense fallback={suspenseFallback}>
        <div className="h-full min-h-[400px] max-h-full overflow-hidden">
          <ExcalidrawPreview data={excalidrawData} />
        </div>
      </Suspense>
    );
  }

  if (markdownFile) {
    return viewSource ? (
      <CodeRenderer content={data?.content || ""} filePath={path} t={t} />
    ) : (
      <MarkdownRenderer content={data?.content || ""} _t={t} />
    );
  }

  return (
    <CodeRenderer
      content={data?.content || ""}
      language={language}
      t={t}
      initialLine={initialLine}
    />
  );
}
