import { useState, useCallback, useEffect, useRef } from "react";
import toast from "react-hot-toast";
import { BackIcon } from "../common/BackIcon";
import { FileIcon } from "../common/FileIcon";
import {
  FilterDropdown,
  FloatingIconButton,
  ToolbarIconButton,
  ViewerDropdownMenuItem,
} from "../common";
import {
  X,
  Copy,
  Check,
  Download,
  Expand,
  Code2,
  PanelRight,
  Columns2,
  Share2,
  MoreHorizontal,
} from "lucide-react";
import {
  formatFileSize as formatFileSizeUtil,
  shouldShowLanguageBadge,
} from "./utils";
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
}: ToolbarProps) {
  const [linkCopied, setLinkCopied] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        setMenuOpen(false);
        menuRef.current?.querySelector("button")?.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [menuOpen]);

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

  const fileActions = [
    {
      title: isSidebar
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
      title: t("documents.fullscreen"),
      icon: <Expand size={TOOLBAR_ICON_SIZE} />,
      onClick: () => {
        onUserInteraction?.();
        if (isSidebar) setViewMode("center");
        handleFullscreenToggle();
      },
    },
    ...(fileUrl
      ? [
          {
            title: t("documents.copyLink", "Copy link"),
            icon: linkCopied ? (
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
            title: t("documents.copy"),
            icon: copied ? (
              <Check size={TOOLBAR_ICON_SIZE} />
            ) : (
              <Copy size={TOOLBAR_ICON_SIZE} />
            ),
            onClick: handleCopy,
          },
        ]
      : []),
  ];

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
      <div className="document-preview-file-info flex-1 min-w-0 overflow-hidden">
        <h3
          className="text-13 sm:text-14 font-medium font-sans text-[var(--theme-text)] truncate"
          title={fileName}
        >
          {fileName}
        </h3>
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
      </div>
      <div className="document-preview-toolbar-actions ml-auto flex items-center gap-1 relative z-10 shrink-0">
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
          <FilterDropdown
            open={menuOpen}
            onOpenChange={setMenuOpen}
            trigger={
              <ToolbarIconButton
                title={t("nav.more")}
                aria-label={t("nav.more")}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen(!menuOpen)}
                icon={<MoreHorizontal size={TOOLBAR_ICON_SIZE} />}
              />
            }
          >
            {fileActions.map((action) => (
              <ViewerDropdownMenuItem
                key={action.title}
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  action.onClick();
                }}
              >
                {action.icon}
                {action.title}
              </ViewerDropdownMenuItem>
            ))}
          </FilterDropdown>
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
