import { useState, useCallback } from "react";
import toast from "react-hot-toast";
import { BackIcon } from "../common/BackIcon";
import { FileIcon } from "../common/FileIcon";
import { FloatingIconButton, ToolbarIconButton } from "../common";
import {
  X,
  Copy,
  Check,
  Download,
  Expand,
  Shrink,
  Eye,
  Code2,
  PanelRight,
  Columns2,
  Share2,
} from "lucide-react";
import { formatFileSize as formatFileSizeUtil } from "./utils";
import type { DocumentPreviewState } from "./useDocumentPreviewState";

type ToolbarProps = Pick<
  DocumentPreviewState,
  | "t"
  | "data"
  | "copied"
  | "viewSource"
  | "isSidebar"
  | "isFullscreen"
  | "markdownFile"
  | "codeFile"
  | "hasTextContent"
  | "displaySize"
  | "fileSize"
  | "fileName"
  | "language"
  | "fileInfo"
  | "Icon"
  | "s3Key"
  | "signedUrl"
  | "externalImageUrl"
  | "resolvedUrl"
  | "unsupportedPreviewFile"
  | "onUserInteraction"
  | "onClose"
  | "effectiveOnBack"
  | "handleCopy"
  | "handleDownload"
  | "toolbarRef"
  | "setViewSource"
  | "setViewMode"
  | "handleFullscreenToggle"
  | "exitFullscreen"
>;

export default function DocumentPreviewToolbar({
  t,
  data,
  copied,
  viewSource,
  isSidebar,
  isFullscreen,
  markdownFile,
  codeFile,
  hasTextContent,
  displaySize,
  fileSize,
  fileName,
  language,
  fileInfo,
  Icon,
  s3Key,
  signedUrl,
  externalImageUrl,
  resolvedUrl,
  unsupportedPreviewFile,
  onUserInteraction,
  onClose,
  effectiveOnBack,
  handleCopy,
  handleDownload,
  toolbarRef,
  setViewSource,
  setViewMode,
  handleFullscreenToggle,
  exitFullscreen,
}: ToolbarProps) {
  const [linkCopied, setLinkCopied] = useState(false);

  const fileUrl = resolvedUrl || signedUrl || externalImageUrl;

  const handleCopyLink = useCallback(() => {
    if (!fileUrl) return;
    navigator.clipboard.writeText(fileUrl).then(() => {
      setLinkCopied(true);
      toast.success(t("documents.linkCopied", "Link copied"));
      setTimeout(() => setLinkCopied(false), 2000);
    });
  }, [fileUrl, t]);

  // Fullscreen: floating exit button — matches SkillFormFullscreen style
  if (isFullscreen) {
    return (
      <FloatingIconButton
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
        className="top-4"
        title={t("common.close")}
        icon={<X size={18} />}
      />
    );
  }

  return (
    <div
      ref={toolbarRef}
      className="flex items-center gap-1.5 sm:gap-2.5 px-2 sm:px-4 py-2 sm:py-3 border-b border-[var(--theme-border)] overflow-hidden"
    >
      {effectiveOnBack && (
        <ToolbarIconButton
          onClick={() => {
            effectiveOnBack();
          }}
          title={t("common.back", "Back")}
          icon={<BackIcon size={16} />}
        />
      )}
      <FileIcon icon={Icon} bg={fileInfo.bg} color={fileInfo.color} />
      <div className="flex-1 min-w-0 overflow-hidden">
        <h3
          className="text-[13px] sm:text-sm font-medium text-[var(--theme-text)] truncate"
          title={fileName}
        >
          {fileName}
        </h3>
        <div className="flex items-center gap-1 sm:gap-1.5 text-xs text-[var(--theme-text-secondary)] mt-0.5">
          {codeFile && (
            <span className="px-1 py-0 sm:px-1.5 sm:py-0.5 rounded bg-[var(--theme-primary-light)] font-mono text-[10px] sm:text-xs shrink-0">
              {language}
            </span>
          )}
          <span className="text-[10px] sm:text-xs truncate">
            {hasTextContent
              ? t("documents.chars", { count: displaySize })
              : fileSize
                ? formatFileSizeUtil(fileSize)
                : fileInfo.label}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-px sm:gap-1 relative z-10 shrink-0">
        {markdownFile && data?.content && (
          <ToolbarIconButton
            onClick={() => {
              setViewSource(!viewSource);
            }}
            title={viewSource ? t("documents.preview") : t("documents.source")}
            icon={viewSource ? <Eye size={16} /> : <Code2 size={16} />}
          />
        )}
        <ToolbarIconButton
          onClick={() => {
            onUserInteraction?.();
            if (isSidebar) {
              setViewMode("center");
            } else {
              setViewMode("sidebar");
              if (isFullscreen) exitFullscreen();
            }
          }}
          title={
            isSidebar
              ? t("documents.centerView", "Center view")
              : t("documents.sidebarView", "Sidebar view")
          }
          icon={isSidebar ? <Columns2 size={16} /> : <PanelRight size={16} />}
        />
        <ToolbarIconButton
          onClick={() => {
            onUserInteraction?.();
            if (!isFullscreen && isSidebar) {
              setViewMode("center");
            }
            handleFullscreenToggle();
          }}
          title={
            isFullscreen
              ? t("documents.exitFullscreen")
              : t("documents.fullscreen")
          }
          icon={isFullscreen ? <Shrink size={16} /> : <Expand size={16} />}
        />
        {(data?.content ||
          s3Key ||
          signedUrl ||
          externalImageUrl ||
          resolvedUrl) && (
          <>
            <ToolbarIconButton
              onClick={() => {
                handleDownload();
              }}
              title={t("documents.download")}
              icon={<Download size={16} />}
            />
            {fileUrl && (
              <ToolbarIconButton
                onClick={() => {
                  handleCopyLink();
                }}
                title={t("documents.copyLink", "Copy link")}
                icon={
                  linkCopied ? (
                    <Check
                      size={16}
                      className="text-green-500 dark:text-green-400"
                    />
                  ) : (
                    <Share2 size={16} />
                  )
                }
              />
            )}
            {data?.content && !unsupportedPreviewFile && (
              <ToolbarIconButton
                onClick={() => {
                  handleCopy();
                }}
                title={t("documents.copy")}
                icon={
                  copied ? (
                    <Check
                      size={16}
                      className="text-green-500 dark:text-green-400"
                    />
                  ) : (
                    <Copy size={16} />
                  )
                }
              />
            )}
          </>
        )}
        <ToolbarIconButton
          onClick={() => {
            onClose();
          }}
          title={t("common.close")}
          aria-label={t("common.close")}
          icon={<X size={16} />}
        />
      </div>
    </div>
  );
}
