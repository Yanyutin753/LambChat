import { useState, useCallback, useId, useRef } from "react";
import { useClipboardCopy } from "../../hooks/useClipboardCopy";
import { useCodeMirrorReady } from "../../hooks/useCodeMirrorReady";
import { BackIcon } from "../common/BackIcon";
import { FileIcon } from "../common/FileIcon";
import { FloatingIconButton, ToolbarIconButton } from "../common";
import {
  X,
  Copy,
  Check,
  AlertCircle,
  Download,
  Expand,
  Code2,
  PanelRight,
  Columns2,
  Share2,
  MoreHorizontal,
  Search,
} from "lucide-react";
import {
  formatFileSize as formatFileSizeUtil,
  shouldShowLanguageBadge,
} from "./utils";
import { ResourceCardMenu } from "../common/ResourceCardMenu";
import { getFullUrl } from "../../services/api/config";
import type { DocumentPreviewState } from "./useDocumentPreviewState";

type ToolbarProps = { embedded?: boolean } & Pick<
  DocumentPreviewState,
  | "t"
  | "data"
  | "copied"
  | "copying"
  | "copyFailed"
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
  | "panelRef"
  | "setViewSource"
  | "setViewMode"
  | "handleFullscreenToggle"
  | "exitFullscreen"
>;

const TOOLBAR_ICON_SIZE = 16;

export default function DocumentPreviewToolbar({
  embedded = false,
  t,
  data,
  copied,
  copying,
  copyFailed,
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
  panelRef,
  setViewSource,
  setViewMode,
  handleFullscreenToggle,
}: ToolbarProps) {
  const [menuPosition, setMenuPosition] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const closeMenu = useCallback((restoreFocus = false) => {
    setMenuPosition(null);
    if (restoreFocus) menuRef.current?.querySelector("button")?.focus();
  }, []);

  const fileUrl =
    getFullUrl(resolvedUrl) ||
    getFullUrl(signedUrl) ||
    getFullUrl(externalImageUrl);

  const {
    copied: linkCopied,
    failed: linkFailed,
    copying: linkCopying,
    copy: handleCopyLink,
  } = useClipboardCopy(fileUrl || "", t("documents.linkCopied", "Link copied"));

  const fileActions = [
    ...(!embedded
      ? [
          {
            label: isSidebar
              ? t("documents.centerView", "Center view")
              : t("documents.sidebarView", "Sidebar view"),
            icon: isSidebar ? (
              <Columns2 size={TOOLBAR_ICON_SIZE} />
            ) : (
              <PanelRight size={TOOLBAR_ICON_SIZE} />
            ),
            onClick: () => {
              onUserInteraction?.();
              setViewMode(isSidebar ? "center" : "sidebar");
            },
          },
          {
            label: t("documents.fullscreen"),
            icon: <Expand size={TOOLBAR_ICON_SIZE} />,
            onClick: () => {
              onUserInteraction?.();
              if (isSidebar) setViewMode("center");
              handleFullscreenToggle();
            },
          },
        ]
      : []),
    ...(fileUrl
      ? [
          {
            label: t("documents.copyLink", "Copy link"),
            disabled: linkCopying,
            icon: linkFailed ? (
              <AlertCircle size={TOOLBAR_ICON_SIZE} />
            ) : linkCopied ? (
              <Check size={TOOLBAR_ICON_SIZE} />
            ) : (
              <Share2 size={TOOLBAR_ICON_SIZE} />
            ),
            onClick: handleCopyLink,
          },
        ]
      : []),
    ...(data?.content && !unsupportedPreviewFile
      ? [
          {
            label: t("documents.copy"),
            disabled: copying,
            icon: copyFailed ? (
              <AlertCircle size={TOOLBAR_ICON_SIZE} />
            ) : copied ? (
              <Check size={TOOLBAR_ICON_SIZE} />
            ) : (
              <Copy size={TOOLBAR_ICON_SIZE} />
            ),
            onClick: handleCopy,
          },
        ]
      : []),
  ];

  const searchable = hasTextContent && (!markdownFile || viewSource);
  const searchReady = useCodeMirrorReady(panelRef, searchable);
  const handleSearch = () => {
    const editor = panelRef.current?.querySelector<HTMLElement>(".cm-editor");
    if (!editor) return;
    void import("../common/codeMirrorSearchExtensions").then(
      ({ openCodeMirrorSearch }) => openCodeMirrorSearch(editor),
    );
  };

  // Fullscreen: floating exit button — matches SkillFormFullscreen style
  if (isFullscreen) {
    return (
      <>
        {searchable && (
          <FloatingIconButton
            onClick={handleSearch}
            disabled={!searchReady}
            style={{
              top: "calc(1rem + var(--app-safe-area-top-active, var(--app-safe-area-top, 0px)))",
              right: "4.25rem",
            }}
            aria-label={t("common.search")}
            title={t("common.search")}
            icon={<Search size={18} />}
          />
        )}
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
      </>
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
      {embedded ? (
        <Icon size={16} className="shrink-0 text-theme-text-secondary" />
      ) : (
        <FileIcon icon={Icon} bg={fileInfo.bg} color={fileInfo.color} compact />
      )}
      <div className="document-preview-file-info flex-1 min-w-0 overflow-hidden">
        <h3
          className="text-13 sm:text-14 font-medium font-sans text-[var(--theme-text)] truncate"
          title={fileName}
        >
          {fileName}
        </h3>
        {!embedded && (
          <div className="flex items-center gap-1.5 text-12 text-[var(--theme-text-secondary)] mt-0.5">
            {shouldShowLanguageBadge(codeFile, language, fileName) && (
              <span className="document-preview-language font-mono text-11 shrink-0">
                {language}
              </span>
            )}
            <span className="text-12 truncate font-sans">
              {hasTextContent
                ? t("documents.chars", { count: displaySize })
                : fileSize
                  ? formatFileSizeUtil(fileSize)
                  : t(fileInfo.label, fileInfo.label)}
            </span>
          </div>
        )}
      </div>
      <div className="document-preview-toolbar-actions ml-auto flex items-center gap-1 relative z-10 shrink-0">
        {searchable && (
          <ToolbarIconButton
            disabled={!searchReady}
            title={t("common.search")}
            aria-label={t("common.search")}
            icon={<Search size={TOOLBAR_ICON_SIZE} />}
            onClick={handleSearch}
          />
        )}
        {markdownFile && data?.content && (
          <button
            type="button"
            className="document-preview-source-toggle"
            aria-pressed={viewSource}
            title={viewSource ? t("documents.preview") : t("documents.source")}
            onClick={() => setViewSource(!viewSource)}
          >
            <Code2 size={TOOLBAR_ICON_SIZE} aria-hidden="true" />
            <span>
              {viewSource ? t("documents.preview") : t("documents.source")}
            </span>
          </button>
        )}
        {(data?.content ||
          s3Key ||
          signedUrl ||
          externalImageUrl ||
          resolvedUrl) && (
          <ToolbarIconButton
            title={t("documents.download")}
            icon={<Download size={TOOLBAR_ICON_SIZE} />}
            onClick={handleDownload}
          />
        )}
        <div className="document-preview-more-actions" ref={menuRef}>
          <ToolbarIconButton
            title={t("nav.more")}
            aria-label={t("nav.more")}
            aria-haspopup="menu"
            aria-expanded={Boolean(menuPosition)}
            aria-controls={menuPosition ? menuId : undefined}
            onClick={(event) => {
              if (menuPosition) {
                closeMenu(true);
                return;
              }
              const rect = event.currentTarget.getBoundingClientRect();
              setMenuPosition({ x: rect.left, y: rect.bottom + 4 });
            }}
            icon={<MoreHorizontal size={TOOLBAR_ICON_SIZE} />}
          />
          {menuPosition && (
            <ResourceCardMenu
              id={menuId}
              title={t("nav.more")}
              position={menuPosition}
              onClose={closeMenu}
              actions={fileActions}
            />
          )}
        </div>
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
