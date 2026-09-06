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
import { getFullUrl } from "../../services/api/config";
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

const TOOLBAR_ICON_SIZE = 16;

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

  const fileUrl =
    getFullUrl(resolvedUrl) ||
    getFullUrl(signedUrl) ||
    getFullUrl(externalImageUrl);

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
        style={{
          top: "calc(1rem + var(--app-safe-area-top-active, var(--app-safe-area-top, 0px)))",
        }}
        title={t("common.close")}
        icon={<X size={18} />}
      />
    );
  }

  return (
    <div
      ref={toolbarRef}
      className="document-preview-toolbar flex items-center gap-1.5 sm:gap-2.5 px-2 sm:px-4 py-2 sm:py-3 border-b border-[var(--theme-border)] overflow-hidden"
    >
      {effectiveOnBack && (
        <ToolbarIconButton
          onClick={() => {
            effectiveOnBack();
          }}
          title={t("common.back", "Back")}
          icon={<BackIcon size={TOOLBAR_ICON_SIZE} />}
        />
      )}
      <FileIcon icon={Icon} bg={fileInfo.bg} color={fileInfo.color} compact />
      <div className="flex-[0_1_clamp(7rem,28%,12rem)] min-w-0 overflow-hidden">
        <h3
          className="text-13 sm:text-sm font-medium font-serif text-[var(--theme-text)] truncate"
          title={fileName}
        >
          {fileName}
        </h3>
        <div className="flex items-center gap-1 sm:gap-1.5 text-xs text-[var(--theme-text-secondary)] mt-0.5">
          {codeFile && (
            <span className="px-1 py-0 sm:px-1.5 sm:py-0.5 rounded bg-[var(--theme-primary-light)] font-mono text-10 sm:text-xs shrink-0 font-serif">
              {language}
            </span>
          )}
          <span className="text-10 sm:text-xs truncate font-serif">
            {hasTextContent
              ? t("documents.chars", { count: displaySize })
              : fileSize
                ? formatFileSizeUtil(fileSize)
                : t(fileInfo.label, fileInfo.label)}
          </span>
        </div>
      </div>
      <div className="document-preview-toolbar-actions ml-auto flex items-center gap-1 relative z-10 shrink-0">
        {markdownFile && data?.content && (
          <ToolbarIconButton
            onClick={() => {
              setViewSource(!viewSource);
            }}
            title={viewSource ? t("documents.preview") : t("documents.source")}
            icon={
              viewSource ? (
                <Eye size={TOOLBAR_ICON_SIZE} />
              ) : (
                <Code2 size={TOOLBAR_ICON_SIZE} />
              )
            }
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
          icon={
            isSidebar ? (
              <Columns2 size={TOOLBAR_ICON_SIZE} />
            ) : (
              <PanelRight size={TOOLBAR_ICON_SIZE} />
            )
          }
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
          icon={
            isFullscreen ? (
              <Shrink size={TOOLBAR_ICON_SIZE} />
            ) : (
              <Expand size={TOOLBAR_ICON_SIZE} />
            )
          }
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
              icon={<Download size={TOOLBAR_ICON_SIZE} />}
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
                      size={TOOLBAR_ICON_SIZE}
                      className="text-green-500 dark:text-green-400"
                    />
                  ) : (
                    <Share2 size={TOOLBAR_ICON_SIZE} />
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
                      size={TOOLBAR_ICON_SIZE}
                      className="text-green-500 dark:text-green-400"
                    />
                  ) : (
                    <Copy size={TOOLBAR_ICON_SIZE} />
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
          icon={<X size={TOOLBAR_ICON_SIZE} />}
        />
      </div>
    </div>
  );
}
