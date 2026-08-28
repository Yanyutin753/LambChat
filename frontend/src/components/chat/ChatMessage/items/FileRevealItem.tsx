import { useState, useEffect, useMemo, useCallback } from "react";
import { clsx } from "clsx";
import { ExternalLink, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner, ImageViewer, VideoViewer } from "../../../common";
import { ImageWithSkeleton } from "../ImageWithSkeleton";
import {
  getFileExtension,
  getFileTypeInfo,
  isExcalidrawFile,
} from "../../../documents/utils";
import { ExcalidrawCardPreview } from "../../../documents/previews/ExcalidrawCardPreview";
import { getFullUrl } from "../../../../services/api";
import {
  getFileRevealAutoOpenKey,
  markFileRevealPreviewAutoOpened,
  shouldAutoOpenFileRevealPreview,
} from "./fileRevealAutoOpen";
import type { RevealPreviewRequest } from "./revealPreviewData";
import type { RevealPreviewOpenSource } from "./revealPreviewState";
import { openRevealPreview } from "./revealPreviewActions";
import { RevealStatusLabel, RevealStatusText } from "./RevealStatusText";
import { useSessionImageGallery } from "../sessionImageGallery";

function MediaSkeleton({ aspectRatio = "16/9" }: { aspectRatio?: string }) {
  return (
    <div
      className="w-full bg-theme-bg-subtle animate-pulse flex items-center justify-center rounded-lg"
      style={{ aspectRatio }}
    >
      <svg
        className="w-10 h-10 text-theme-text-tertiary"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15"
        />
      </svg>
    </div>
  );
}

// 新格式：与 UploadResult 一致
interface FileRevealResultNew {
  key: string;
  url: string;
  name: string;
  type: "image" | "video" | "audio" | "document";
  mimeType: string;
  size: number;
  _meta?: {
    path: string;
    description?: string;
  };
}

// 旧格式：带 error 的情况
interface FileInfo {
  path: string;
  description?: string;
  s3_url?: string;
  s3_key?: string;
  size?: number;
  error?: string;
}

interface FileRevealResultOld {
  type: "file_reveal";
  file: FileInfo;
}

type FileRevealResult = FileRevealResultNew | FileRevealResultOld;

export function FileRevealItem({
  args,
  result,
  success,
  isPending,
  cancelled,
  allowAutoPreview,
  activePreview,
  onOpenPreview,
  startedAt,
  completedAt,
}: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
  allowAutoPreview?: boolean;
  activePreview?: RevealPreviewRequest | null;
  onOpenPreview?: (
    preview: RevealPreviewRequest,
    source?: RevealPreviewOpenSource,
  ) => boolean;
  startedAt?: string;
  completedAt?: string;
}) {
  const { t } = useTranslation();
  const durationFooter = useMemo(() => {
    if (!startedAt || !completedAt) return undefined;
    const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
    if (ms < 0) return undefined;
    const seconds = Math.round(ms / 1000);
    const text =
      seconds < 60
        ? t("chat.message.toolTimeSeconds", { count: seconds })
        : t("chat.message.toolTimeMinutes", {
            minutes: Math.floor(seconds / 60),
            seconds: seconds % 60,
          });
    return (
      <span className="inline-flex items-center gap-1 text-xs text-[var(--theme-text-secondary)] tabular-nums px-2">
        <Clock size={11} className="shrink-0" />
        {text}
      </span>
    );
  }, [startedAt, completedAt, t]);
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);
  const [videoViewerSrc, setVideoViewerSrc] = useState<string | null>(null);
  const [mediaLoaded, setMediaLoaded] = useState(false);
  const sessionImageGallery = useSessionImageGallery();

  const parsed = useMemo(() => {
    let filePath = "";
    let description = "";
    let s3Key = "";
    let s3Url = "";
    let fileSize: number | undefined;
    let error = "";

    if (result) {
      try {
        let r: FileRevealResult;
        if (typeof result === "object") {
          r = result as unknown as FileRevealResult;
        } else {
          let jsonStr = result;
          const m = result.match(/content='(.+?)'(\s|$)/);
          if (m) jsonStr = m[1].replace(/\\'/g, "'");
          r = JSON.parse(jsonStr);
        }
        if ("key" in r && "url" in r) {
          s3Key = r.key;
          s3Url = getFullUrl(r.url) || "";
          fileSize = r.size;
          if (r._meta) {
            filePath = r._meta.path;
            description = r._meta.description || "";
          } else {
            filePath = r.name;
          }
        } else if (r.type === "file_reveal" && "file" in r) {
          filePath = r.file.path;
          description = r.file.description || "";
          s3Key = r.file.s3_key || "";
          s3Url = getFullUrl(r.file.s3_url) || "";
          fileSize = r.file.size;
          error = r.file.error || "";
        }
      } catch {
        filePath = (args.path as string) || "";
        description = (args.description as string) || "";
      }
    } else {
      filePath = (args.path as string) || "";
      description = (args.description as string) || "";
    }

    return { filePath, description, s3Key, s3Url, fileSize, error };
  }, [result, args.path, args.description]);

  const fileName = parsed.filePath.split("/").pop() || parsed.filePath;
  const fileInfo = getFileTypeInfo(parsed.filePath);
  const FileIcon = fileInfo.icon;
  const color = fileInfo.color;
  const bg = fileInfo.bg;
  const isImage = fileInfo.category === "image";
  const isVideo = fileInfo.category === "video";
  const isAudio = fileInfo.category === "audio";
  const isExcalidraw = isExcalidrawFile(getFileExtension(parsed.filePath));
  const canPreview = isImage || isVideo || isAudio;
  const previewAutoOpenKey = getFileRevealAutoOpenKey({
    s3Key: parsed.s3Key,
    s3Url: parsed.s3Url,
    filePath: parsed.filePath,
  });
  const isPreviewOpen =
    activePreview?.kind === "file" &&
    activePreview.previewKey === previewAutoOpenKey;

  const previewRequest = useMemo(
    (): RevealPreviewRequest | null =>
      previewAutoOpenKey
        ? {
            kind: "file",
            previewKey: previewAutoOpenKey,
            filePath: parsed.filePath,
            s3Key: parsed.s3Key || undefined,
            signedUrl: parsed.s3Url || undefined,
            fileSize: parsed.fileSize,
            footer: durationFooter,
          }
        : null,
    [
      previewAutoOpenKey,
      parsed.filePath,
      parsed.s3Key,
      parsed.s3Url,
      parsed.fileSize,
      durationFooter,
    ],
  );

  const openPreview = useCallback(
    (source: RevealPreviewOpenSource) => {
      if (!previewAutoOpenKey || !previewRequest) return;
      openRevealPreview(previewRequest, source, onOpenPreview);
    },
    [previewAutoOpenKey, onOpenPreview, previewRequest],
  );
  const openImagePreview = useCallback(
    (src: string) => {
      sessionImageGallery?.openImage(src, fileName || undefined, {
        group: "reveal-file",
      });
      if (!sessionImageGallery) {
        setImageViewerSrc(src);
      }
    },
    [fileName, sessionImageGallery],
  );

  // Auto-open sidebar preview on desktop when file is ready
  useEffect(() => {
    const decision = shouldAutoOpenFileRevealPreview({
      success,
      filePath: parsed.filePath,
      isImage,
      showPreview: isPreviewOpen,
      isDesktop: window.innerWidth >= 640,
      allowAutoPreview,
      previewKey: previewAutoOpenKey,
    });
    if (!decision) return;

    const opened =
      previewRequest &&
      openRevealPreview(previewRequest, "auto", onOpenPreview);
    if (opened) {
      markFileRevealPreviewAutoOpened(previewAutoOpenKey);
    }
  }, [
    success,
    parsed.filePath,
    isImage,
    isPreviewOpen,
    allowAutoPreview,
    previewAutoOpenKey,
    onOpenPreview,
    previewRequest,
  ]);

  if (isPending) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-theme-border bg-theme-bg-card dark:bg-theme-bg">
        <div className={`p-2.5 rounded-lg ${bg}`}>
          <LoadingSpinner size="sm" className={color} />
        </div>
        <RevealStatusText title={fileName} subtitle={parsed.description} />
        <RevealStatusLabel>{t("chat.message.running")}</RevealStatusLabel>
      </div>
    );
  }

  if (cancelled && !result) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20">
        <div className={`p-2.5 rounded-lg ${bg}`}>
          <FileIcon size={20} className={color} />
        </div>
        <RevealStatusText title={fileName} subtitle={parsed.description} />
        <RevealStatusLabel>{t("chat.message.cancelled")}</RevealStatusLabel>
      </div>
    );
  }

  if (parsed.error) {
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
            {parsed.error}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="my-2 sm:my-3 min-w-0">
      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          isOpen={!!imageViewerSrc}
          onClose={() => setImageViewerSrc(null)}
        />
      )}
      {videoViewerSrc && (
        <VideoViewer
          src={videoViewerSrc}
          isOpen={!!videoViewerSrc}
          onClose={() => setVideoViewerSrc(null)}
          title={fileName || undefined}
        />
      )}

      {(canPreview || isExcalidraw) && parsed.s3Url && success ? (
        <div
          className={clsx(
            "rounded-xl border overflow-hidden transition-colors transition-shadow",
            "border-theme-border bg-theme-bg-card dark:bg-theme-bg",
            "hover:shadow-lg hover:border-theme-border-hover",
            isImage && "max-w-md",
          )}
        >
          {isAudio ? (
            <div className="px-4 py-4">
              <audio
                controls
                className="w-full"
                src={parsed.s3Url}
                preload="metadata"
              />
            </div>
          ) : (
            <div
              className="relative group/img cursor-pointer"
              style={isImage ? undefined : { aspectRatio: "16/9" }}
              onClick={() => {
                if (isImage) openImagePreview(parsed.s3Url);
                else if (isVideo) setVideoViewerSrc(parsed.s3Url);
                else if (isExcalidraw) openPreview("manual");
              }}
            >
              {!mediaLoaded && !isExcalidraw && (
                <div className="absolute inset-0">
                  <MediaSkeleton />
                </div>
              )}
              {isImage ? (
                <ImageWithSkeleton
                  src={parsed.s3Url}
                  alt={fileName}
                  skipUrlResolve
                  inline
                  className="w-full h-auto object-contain z-[1] rounded-lg"
                  onLoad={() => setMediaLoaded(true)}
                  onError={() => setMediaLoaded(true)}
                />
              ) : isExcalidraw ? (
                <ExcalidrawCardPreview url={parsed.s3Url} />
              ) : (
                parsed.s3Url && (
                  <video
                    src={parsed.s3Url}
                    controls
                    preload="metadata"
                    className="w-full h-full bg-black relative z-[1]"
                    playsInline
                    onLoadedData={() => setMediaLoaded(true)}
                    onCanPlay={() => setMediaLoaded(true)}
                    onError={() => setMediaLoaded(true)}
                  />
                )
              )}
              {(isImage || isVideo || isExcalidraw) && (
                <>
                  <div className="absolute top-2 right-2 opacity-0 group-hover/img:opacity-100 transition-opacity pointer-events-none z-[2]">
                    <div className="p-1.5 rounded-lg bg-black/40 shadow pointer-events-auto">
                      <ExternalLink size={14} className="text-white" />
                    </div>
                  </div>
                  {isImage && (fileName || parsed.description) && (
                    <div className="absolute bottom-0 left-0 right-0 opacity-0 group-hover/img:opacity-100 transition-opacity z-[2]">
                      <div className="px-2 py-1.5 bg-gradient-to-t from-black/60 to-transparent">
                        <span className="text-[11px] text-white/90 truncate block font-serif">
                          {parsed.description || fileName}
                        </span>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          <div
            className={clsx(
              "flex items-center gap-2 px-3 py-2 bg-theme-bg dark:bg-theme-bg-subtle/50 border-t border-theme-border",
              isAudio && "border-t-0",
            )}
            onClick={() => {
              if (!isImage && !isAudio) openPreview("manual");
            }}
          >
            <div className={`p-1.5 rounded-md shrink-0 ${bg}`}>
              <FileIcon size={14} className={color} />
            </div>
            <span className="text-xs font-medium text-theme-text-secondary min-w-0 truncate flex-1">
              {fileName}
            </span>
            {parsed.description && (
              <span className="text-xs text-theme-text-tertiary truncate max-w-[200px]">
                {parsed.description}
              </span>
            )}
          </div>
        </div>
      ) : (
        <button
          onClick={() => {
            if (!parsed.filePath || !success) return;
            if (isImage && parsed.s3Url) {
              openImagePreview(parsed.s3Url);
            } else {
              openPreview("manual");
            }
          }}
          className={clsx(
            "w-full flex items-center gap-3 p-4 rounded-xl border transition-colors transition-transform cursor-pointer text-left",
            success
              ? "border-theme-border bg-theme-bg-card dark:bg-theme-bg hover:shadow-lg hover:border-theme-border-hover hover:scale-[1.005]"
              : "border-theme-border bg-theme-bg-subtle opacity-70",
          )}
          disabled={!parsed.filePath || !success}
        >
          <div className={`p-2.5 rounded-lg shrink-0 ${bg}`}>
            <FileIcon size={20} className={color} />
          </div>

          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-theme-text truncate">
              {fileName}
            </div>
            {parsed.description && (
              <div className="text-xs text-theme-text-tertiary truncate mt-1">
                {parsed.description}
              </div>
            )}
          </div>

          {success && parsed.filePath && (
            <div className="shrink-0 p-2 rounded-lg bg-theme-bg-subtle text-theme-text-tertiary">
              <ExternalLink size={16} />
            </div>
          )}
        </button>
      )}
    </div>
  );
}
