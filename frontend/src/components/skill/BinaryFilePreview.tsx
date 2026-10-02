import { SceneIllustration } from "../common/SceneIllustration";
import { useMemo, useState, useCallback, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { ImageWithSkeleton } from "../chat/ChatMessage/ImageWithSkeleton";
import {
  FileIcon,
  Image,
  Download,
  Film,
  Music,
  FileArchive,
} from "lucide-react";
import { getFullUrl } from "../../services/api/config";
import { Button, ImageViewer, ToolbarIconButton } from "../common";
import { SkillFileLoadState } from "./SkillFileLoadState";

interface BinaryFilePreviewProps {
  url: string;
  mime_type: string;
  size: number;
  fileName: string;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isImage(mime: string) {
  return mime.startsWith("image/");
}

function isVideo(mime: string) {
  return mime.startsWith("video/");
}

function isAudio(mime: string) {
  return mime.startsWith("audio/");
}

function isPdf(mime: string) {
  return mime === "application/pdf";
}

function getFileIcon(mime: string) {
  if (isImage(mime)) return Image;
  if (isVideo(mime)) return Film;
  if (isAudio(mime)) return Music;
  if (mime.includes("zip") || mime.includes("tar") || mime.includes("archive"))
    return FileArchive;
  return FileIcon;
}

function getIconColor(mime: string) {
  if (isImage(mime)) return "text-emerald-500";
  if (isVideo(mime)) return "text-purple-500";
  if (isAudio(mime)) return "text-pink-500";
  if (mime.includes("zip") || mime.includes("tar")) return "text-amber-500";
  return "text-[var(--theme-text-secondary)]";
}

function getIconBg(mime: string) {
  if (isImage(mime)) return "bg-emerald-500/10";
  if (isVideo(mime)) return "bg-purple-500/10";
  if (isAudio(mime)) return "bg-pink-500/10";
  if (mime.includes("zip") || mime.includes("tar")) return "bg-amber-500/10";
  return "bg-[var(--theme-bg-card)]";
}

export function BinaryFilePreview({
  url,
  mime_type,
  size,
  fileName,
}: BinaryFilePreviewProps) {
  const { t } = useTranslation();
  const fullUrl = useMemo(() => getFullUrl(url) || url, [url]);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [loadedImage, setLoadedImage] = useState<string>();
  const [failedSource, setFailedSource] = useState<string>();
  const [retryAttempt, setRetryAttempt] = useState(0);
  const contentRef = useRef<HTMLDivElement>(null);
  const hasError = failedSource === fullUrl;
  useEffect(() => {
    setFailedSource(undefined);
    setLoadedImage(undefined);
    setRetryAttempt(0);
    setViewerOpen(false);
  }, [fullUrl, mime_type]);
  const handleError = () => {
    if (contentRef.current?.contains(document.activeElement))
      contentRef.current.focus();
    setFailedSource(fullUrl);
  };

  const Icon = getFileIcon(mime_type);
  const iconColor = getIconColor(mime_type);
  const iconBg = getIconBg(mime_type);

  const handleDownload = useCallback(() => {
    const a = document.createElement("a");
    a.href = fullUrl;
    a.download = fileName;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }, [fullUrl, fileName]);

  return (
    <div className="flex h-full min-h-[18rem] sm:min-h-[24rem] flex-col rounded-2xl bg-[var(--theme-bg)] overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2.5 px-3 sm:px-4 py-2.5 border-b border-[var(--theme-border)] shrink-0">
        <div
          className={`flex items-center justify-center w-9 h-9 rounded-xl ${iconBg}`}
        >
          <Icon size={18} className={iconColor} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-14 font-medium text-[var(--theme-text)] truncate">
            {fileName}
          </p>
          <p
            className="truncate text-11 text-[var(--theme-text-secondary)]"
            title={`${mime_type} · ${formatSize(size)}`}
          >
            {mime_type} · {formatSize(size)}
          </p>
        </div>
        <ToolbarIconButton
          onClick={handleDownload}
          icon={<Download size={16} />}
          aria-label={t("documents.download")}
          title={t("documents.download")}
        />
      </div>

      {/* Content area */}
      <div
        ref={contentRef}
        tabIndex={-1}
        className="flex-1 min-h-0 overflow-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--theme-primary)]/50"
      >
        {hasError ? (
          <SkillFileLoadState
            path={fileName}
            error={t(
              isImage(mime_type)
                ? "imageViewer.loadFailed"
                : isVideo(mime_type)
                  ? "documents.videoLoadFailed"
                  : "files.loadFailed",
            )}
            onRetry={() => {
              contentRef.current?.focus();
              setFailedSource(undefined);
              setLoadedImage(undefined);
              setRetryAttempt((attempt) => attempt + 1);
            }}
          />
        ) : (
          <>
            {/* Image preview */}
            {isImage(mime_type) && (
              <div className="relative flex items-center justify-center p-4 sm:p-6 min-h-full">
                <ImageWithSkeleton
                  key={`${fullUrl}:${retryAttempt}`}
                  src={fullUrl}
                  alt={fileName}
                  skipUrlResolve
                  onClick={() => loadedImage === fullUrl && setViewerOpen(true)}
                  wrapperClassName="w-full max-w-4xl"
                  className="max-w-full max-h-[60dvh] rounded-lg shadow-md"
                  style={{ objectFit: "contain" }}
                  onLoad={() => setLoadedImage(fullUrl)}
                  onError={handleError}
                />
              </div>
            )}

            {/* Video preview */}
            {isVideo(mime_type) && (
              <div className="relative flex items-center justify-center bg-[var(--theme-bg-subtle)] p-4 sm:p-6 min-h-full">
                <video
                  key={`${fullUrl}:${retryAttempt}`}
                  src={fullUrl}
                  controls
                  preload="metadata"
                  autoPlay={false}
                  playsInline
                  aria-label={fileName}
                  onError={handleError}
                  className="w-full max-w-4xl max-h-[60dvh] rounded-lg"
                >
                  <track kind="captions" />
                </video>
              </div>
            )}

            {/* Audio preview */}
            {isAudio(mime_type) && (
              <div className="flex flex-col items-center justify-center gap-6 py-12 px-4 min-h-full">
                <div className="flex flex-col items-center gap-2">
                  <SceneIllustration scene="files" />
                  <Music size={18} className={iconColor} />
                </div>
                <audio
                  key={`${fullUrl}:${retryAttempt}`}
                  src={fullUrl}
                  controls
                  preload="metadata"
                  aria-label={fileName}
                  onError={handleError}
                  className="w-full max-w-md"
                />
              </div>
            )}

            {/* PDF preview */}
            {isPdf(mime_type) && (
              <iframe
                src={fullUrl}
                className="w-full h-full min-h-[400px] border-0"
                title={fileName}
              />
            )}

            {/* Generic binary file (non-previewable) */}
            {!isImage(mime_type) &&
              !isVideo(mime_type) &&
              !isAudio(mime_type) &&
              !isPdf(mime_type) && (
                <div className="flex flex-col items-center justify-center gap-4 py-12 px-4 min-h-full">
                  <div className="flex flex-col items-center gap-2">
                    <SceneIllustration scene="files" />
                    <Icon size={18} className={iconColor} />
                  </div>
                  <div className="text-center">
                    <p className="text-14 font-medium text-[var(--theme-text)] mb-1">
                      {t("skills.binaryPreview.title")}
                    </p>
                    <p className="text-12 text-[var(--theme-text-secondary)] max-w-xs">
                      {t("skills.binaryPreview.unsupportedHint")}
                    </p>
                  </div>
                  <Button
                    onClick={handleDownload}
                    variant="primary"
                    size="lg"
                    leftIcon={<Download size={16} />}
                    className="mt-2"
                  >
                    {t("skills.binaryPreview.download")}
                  </Button>
                </div>
              )}
          </>
        )}
      </div>

      {/* ImageViewer modal */}
      {isImage(mime_type) && (
        <ImageViewer
          src={fullUrl}
          alt={fileName}
          isOpen={viewerOpen}
          onClose={() => setViewerOpen(false)}
        />
      )}
    </div>
  );
}
