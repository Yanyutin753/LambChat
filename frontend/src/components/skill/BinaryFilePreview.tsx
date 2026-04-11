import { useMemo, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  FileIcon,
  Image,
  Download,
  Film,
  Music,
  FileArchive,
  Loader2,
} from "lucide-react";
import { getFullUrl } from "../../services/api/config";
import { ImageViewer } from "../common";

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
  const [imageLoaded, setImageLoaded] = useState(false);
  const [videoLoaded, setVideoLoaded] = useState(false);

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
          <p className="text-sm font-medium text-[var(--theme-text)] truncate">
            {fileName}
          </p>
          <p className="text-[11px] text-[var(--theme-text-secondary)]">
            {mime_type} · {formatSize(size)}
          </p>
        </div>
        <button
          type="button"
          onClick={handleDownload}
          className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-[var(--theme-text-secondary)] hover:bg-[var(--theme-bg-card)] transition-colors cursor-pointer"
          title={t("documents.download")}
        >
          <Download size={14} />
          <span className="hidden sm:inline">Download</span>
        </button>
      </div>

      {/* Content area */}
      <div className="flex-1 min-h-0 overflow-auto">
        {/* Image preview */}
        {isImage(mime_type) && (
          <div
            className="relative flex items-center justify-center p-4 sm:p-6 min-h-full cursor-zoom-in"
            onClick={() => imageLoaded && setViewerOpen(true)}
          >
            {!imageLoaded && (
              <div className="absolute inset-0 flex items-center justify-center bg-[var(--theme-bg-card)]/50 rounded-lg">
                <div className="flex flex-col items-center gap-3">
                  <Loader2
                    size={28}
                    className="animate-spin text-[var(--theme-text-secondary)]"
                  />
                  <span className="text-xs text-[var(--theme-text-secondary)]">
                    Loading...
                  </span>
                </div>
              </div>
            )}
            <img
              src={fullUrl}
              alt={fileName}
              onLoad={() => setImageLoaded(true)}
              onError={() => setImageLoaded(true)}
              className="max-w-full max-h-[60vh] rounded-lg object-contain shadow-md hover:opacity-90 transition-opacity"
            />
          </div>
        )}

        {/* Video preview */}
        {isVideo(mime_type) && (
          <div className="relative flex items-center justify-center bg-gradient-to-b from-stone-900 to-stone-950 p-4 sm:p-8 min-h-full">
            {!videoLoaded && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                  <Loader2 size={28} className="animate-spin text-white/60" />
                  <span className="text-xs text-white/50">
                    Loading video...
                  </span>
                </div>
              </div>
            )}
            <video
              src={fullUrl}
              controls
              preload="metadata"
              autoPlay={false}
              onLoadedData={() => setVideoLoaded(true)}
              onError={() => setVideoLoaded(true)}
              className={`w-full max-w-4xl max-h-[60vh] rounded-xl shadow-2xl ring-1 ring-white/10 transition-opacity duration-300 ${
                videoLoaded ? "opacity-100" : "opacity-0"
              }`}
            >
              <track kind="captions" />
            </video>
          </div>
        )}

        {/* Audio preview */}
        {isAudio(mime_type) && (
          <div className="flex flex-col items-center justify-center gap-6 py-12 px-4 min-h-full">
            <div
              className={`flex items-center justify-center w-20 h-20 rounded-2xl ${iconBg}`}
            >
              <Music size={36} className={iconColor} />
            </div>
            <audio src={fullUrl} controls className="w-full max-w-md" />
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
              <div
                className={`flex items-center justify-center w-20 h-20 rounded-2xl ${iconBg}`}
              >
                <Icon size={36} className={iconColor} />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-[var(--theme-text)] mb-1">
                  {t("skills.binaryPreview.title")}
                </p>
                <p className="text-xs text-[var(--theme-text-secondary)] max-w-xs">
                  {t("skills.binaryPreview.unsupportedHint")}
                </p>
              </div>
              <button
                onClick={handleDownload}
                className="mt-2 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[var(--theme-primary)] text-white text-sm font-medium hover:opacity-90 transition-all active:scale-95 cursor-pointer"
              >
                <Download size={16} />
                {t("skills.binaryPreview.download")}
              </button>
            </div>
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
