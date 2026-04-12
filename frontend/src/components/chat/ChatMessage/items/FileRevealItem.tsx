import { useState, useEffect, useRef } from "react";
import { clsx } from "clsx";
import { ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner, ImageViewer } from "../../../common";
import DocumentPreview from "../../../documents/DocumentPreview";
import { closeCurrentToolPanel } from "./ToolResultPanel";
import { getFileTypeInfo } from "../../../documents/utils";
import { getFullUrl } from "../../../../services/api";

function MediaSkeleton({ aspectRatio = "16/9" }: { aspectRatio?: string }) {
  return (
    <div
      className="w-full bg-stone-100 dark:bg-stone-800 animate-pulse flex items-center justify-center"
      style={{ aspectRatio }}
    >
      <svg
        className="w-10 h-10 text-stone-300 dark:text-stone-600"
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
}: {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
}) {
  const { t } = useTranslation();
  const [showPreview, setShowPreview] = useState(false);
  const [imageViewerSrc, setImageViewerSrc] = useState<string | null>(null);
  const [mediaLoaded, setMediaLoaded] = useState(false);

  let filePath = "";
  let description = "";
  let s3Key = "";
  let s3Url = "";
  let fileSize: number | undefined = undefined;
  let error = "";

  if (result) {
    try {
      let parsed: FileRevealResult;

      if (typeof result === "object") {
        parsed = result as unknown as FileRevealResult;
      } else {
        let jsonStr = result;
        const contentMatch = result.match(/content='(.+?)'(\s|$)/);
        if (contentMatch) {
          jsonStr = contentMatch[1].replace(/\\'/g, "'");
        }
        parsed = JSON.parse(jsonStr);
      }

      if ("key" in parsed && "url" in parsed) {
        s3Key = parsed.key;
        s3Url = getFullUrl(parsed.url) || "";
        fileSize = parsed.size;
        if (parsed._meta) {
          filePath = parsed._meta.path;
          description = parsed._meta.description || "";
        } else {
          filePath = parsed.name;
        }
      } else if (parsed.type === "file_reveal" && "file" in parsed) {
        filePath = parsed.file.path;
        description = parsed.file.description || "";
        s3Key = parsed.file.s3_key || "";
        fileSize = parsed.file.size;
        error = parsed.file.error || "";
      }
    } catch {
      filePath = (args.path as string) || "";
      description = (args.description as string) || "";
    }
  } else {
    filePath = (args.path as string) || "";
    description = (args.description as string) || "";
  }

  const fileName = filePath.split("/").pop() || filePath;
  const fileInfo = getFileTypeInfo(filePath);
  const FileIcon = fileInfo.icon;
  const color = fileInfo.color;
  const bg = fileInfo.bg;
  const isImage = fileInfo.category === "image";
  const isVideo = fileInfo.category === "video";
  const canPreview = isImage || isVideo;

  // Auto-open sidebar preview on desktop when file is ready
  const hasClosedPreview = useRef(false);
  useEffect(() => {
    if (
      !success ||
      !filePath ||
      isImage ||
      showPreview ||
      hasClosedPreview.current
    )
      return;
    if (window.innerWidth >= 640) {
      closeCurrentToolPanel();
      setShowPreview(true);
    }
  }, [success, filePath, isImage, showPreview]);

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

  if (cancelled && !result) {
    return (
      <div className="my-2 flex items-center gap-3 px-4 py-3 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20">
        <div className={`p-2.5 rounded-lg ${bg}`}>
          <FileIcon size={20} className={color} />
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
          {t("chat.message.cancelled")}
        </div>
      </div>
    );
  }

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
    <div className="my-2 sm:my-3 min-w-0">
      {showPreview && filePath && !isImage && (
        <DocumentPreview
          path={filePath}
          s3Key={s3Key || undefined}
          signedUrl={s3Url || undefined}
          fileSize={fileSize}
          onClose={() => {
            hasClosedPreview.current = true;
            setShowPreview(false);
          }}
        />
      )}

      {imageViewerSrc && (
        <ImageViewer
          src={imageViewerSrc}
          isOpen={!!imageViewerSrc}
          onClose={() => setImageViewerSrc(null)}
        />
      )}

      {canPreview && s3Url && success ? (
        <div
          className={clsx(
            "w-full rounded-xl border overflow-hidden transition-colors transition-shadow",
            "border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-900",
            "hover:shadow-lg hover:border-stone-300 dark:hover:border-stone-600",
          )}
        >
          <div
            className="relative group cursor-pointer"
            style={{ aspectRatio: isImage ? "16/10" : "16/9" }}
            onClick={() => isImage && setImageViewerSrc(s3Url)}
          >
            {!mediaLoaded && (
              <div className="absolute inset-0">
                <MediaSkeleton />
              </div>
            )}
            {isImage ? (
              <img
                src={s3Url}
                alt={fileName}
                className="absolute inset-0 w-full h-full object-cover z-[1]"
                loading="lazy"
                onLoad={() => setMediaLoaded(true)}
                onError={() => setMediaLoaded(true)}
              />
            ) : (
              s3Url && (
                <video
                  src={s3Url}
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
            {isImage && (
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center">
                <div className="opacity-0 group-hover:opacity-100 transition-opacity p-2 rounded-full bg-white/90 dark:bg-stone-800/90 shadow-lg">
                  <ExternalLink
                    size={16}
                    className="text-stone-600 dark:text-stone-300"
                  />
                </div>
              </div>
            )}
          </div>

          <div
            className="flex items-center gap-2 px-3 py-2 bg-stone-50 dark:bg-stone-800/50 border-t border-stone-200 dark:border-stone-700"
            onClick={() => {
              if (!isImage) {
                closeCurrentToolPanel();
                setShowPreview(true);
              }
            }}
          >
            <div className={`p-1.5 rounded-md shrink-0 ${bg}`}>
              <FileIcon size={14} className={color} />
            </div>
            <span className="text-xs font-medium text-stone-700 dark:text-stone-300 truncate flex-1">
              {fileName}
            </span>
            {description && (
              <span className="text-xs text-stone-400 dark:text-stone-500 truncate max-w-[200px]">
                {description}
              </span>
            )}
          </div>
        </div>
      ) : (
        <button
          onClick={() => {
            if (!filePath || !success) return;
            if (isImage && s3Url) {
              setImageViewerSrc(s3Url);
            } else {
              closeCurrentToolPanel();
              setShowPreview(true);
            }
          }}
          className={clsx(
            "w-full flex items-center gap-3 p-4 rounded-xl border transition-colors transition-transform cursor-pointer text-left",
            success
              ? "border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-900 hover:shadow-lg hover:border-stone-300 dark:hover:border-stone-600 hover:scale-[1.005]"
              : "border-stone-200 dark:border-stone-700 bg-stone-50 dark:bg-stone-800 opacity-70",
          )}
          disabled={!filePath || !success}
        >
          <div className={`p-2.5 rounded-lg shrink-0 ${bg}`}>
            <FileIcon size={20} className={color} />
          </div>

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

          {success && filePath && (
            <div className="shrink-0 p-2 rounded-lg bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400">
              <ExternalLink size={16} />
            </div>
          )}
        </button>
      )}
    </div>
  );
}
