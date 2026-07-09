/* eslint-disable react-refresh/only-export-components */
import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { BackIcon } from "../../../common/BackIcon";
import {
  X,
  CheckCircle,
  XCircle,
  Ban,
  Columns2,
  PanelRight,
  Expand,
  Shrink,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner, ToolbarIconButton } from "../../../common";

import { useSidebarPanel } from "../../../../hooks/useSidebarPanel";
import type { CollapsibleStatus } from "../../../common/CollapsiblePill";
import { registerToolPanel } from "./toolPanelRegistry";
import {
  getSidebarHistoryLength,
  goBackSidebar,
  subscribeSidebarHistory,
  clearSidebarHistory,
} from "./sidebarHistoryStore";
export { closeCurrentToolPanel } from "./toolPanelRegistry";

const WIDTH_STORAGE_KEY = "sidebar-preview-width";
const WIDTH_CSS_VAR = "--sidebar-preview-width";
const DEFAULT_WIDTH_PCT = 60;

interface ToolResultPanelProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  icon?: React.ReactNode;
  status?: CollapsibleStatus;
  subtitle?: string;
  children: React.ReactNode;
  /** "sidebar" (default) = right side panel; "center" = fullscreen overlay */
  viewMode?: "sidebar" | "center";
  /** Controlled fullscreen state. When provided, the built-in fullscreen button is shown. */
  isFullscreen?: boolean;
  /** Callback when fullscreen state changes */
  onFullscreenChange?: (fullscreen: boolean) => void;
  /** Extra action buttons rendered in sidebar header, between title and close */
  headerActions?: React.ReactNode;
  /** Custom header replacing the default one (rendered outside scroll area) */
  customHeader?: React.ReactNode;
  /** Footer rendered below the scrollable content area */
  footer?: React.ReactNode;
  /** Custom overlay className (overrides default) */
  overlayClass?: string;
  /** Custom panel className (overrides default) */
  panelClass?: string;
  /** Optional external ref to the root panel element */
  panelElementRef?: React.Ref<HTMLDivElement>;
  /** Callback when view mode changes (for externally controlled viewMode) */
  onViewModeChange?: (mode: "sidebar" | "center") => void;
  /** Called when the user explicitly manipulates the panel UI */
  onUserInteraction?: () => void;
  /** Called when the user explicitly closes the panel UI */
  onUserClose?: () => void;
  /** Stable logical key to survive remounts without closing the same panel */
  registryKey?: string;
  /** Hide the built-in center/fullscreen buttons in the default header */
  hideViewToggle?: boolean;
  /** When true, mobile renders as full-viewport instead of bottom sheet */
  mobileFillViewport?: boolean;
  /** When provided, a back button is shown in the header */
  onBack?: () => void;
}

const statusConfig: Record<
  CollapsibleStatus,
  { bg: string; color: string; icon: React.ReactNode }
> = {
  idle: {
    bg: "bg-theme-bg-subtle",
    color: "text-theme-text-tertiary",
    icon: null,
  },
  loading: {
    bg: "bg-[color-mix(in_srgb,var(--theme-primary)_8%,transparent)]",
    color: "text-[var(--theme-primary)]",
    icon: null,
  },
  success: {
    bg: "bg-emerald-100/80 dark:bg-emerald-900/30",
    color: "text-emerald-600 dark:text-emerald-400",
    icon: <CheckCircle size={16} />,
  },
  error: {
    bg: "bg-red-100/80 dark:bg-red-900/30",
    color: "text-red-600 dark:text-red-400",
    icon: <XCircle size={16} />,
  },
  cancelled: {
    bg: "bg-[color-mix(in_srgb,var(--theme-primary)_8%,transparent)]",
    color: "text-[var(--theme-primary)]",
    icon: <Ban size={16} />,
  },
};

export function ToolResultPanel({
  open,
  onClose,
  title = "",
  icon,
  status = "idle",
  subtitle,
  children,
  viewMode: externalViewMode,
  isFullscreen: externalIsFullscreen,
  onFullscreenChange,
  headerActions,
  customHeader,
  footer,
  overlayClass,
  panelClass,
  panelElementRef,
  onUserInteraction,
  onUserClose,
  registryKey,
  hideViewToggle = false,
  onViewModeChange,
  onBack,
  mobileFillViewport,
}: ToolResultPanelProps) {
  const { t } = useTranslation();
  const [internalViewMode, setInternalViewMode] = useState<
    "sidebar" | "center"
  >(externalViewMode ?? "sidebar");
  const [internalIsFullscreen, setInternalIsFullscreen] = useState(false);
  const [contentReady, setContentReady] = useState(false);
  const toolbarRef = useRef<HTMLDivElement>(null);

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

  // Only use external viewMode when fully controlled (has onChange callback)
  // Otherwise treat externalViewMode as initial value and manage internally
  const isViewModeControlled = !!(externalViewMode && onViewModeChange);
  const effectiveViewMode = isViewModeControlled
    ? externalViewMode!
    : internalViewMode;
  const effectiveIsFullscreen = externalIsFullscreen ?? internalIsFullscreen;
  const isFullscreen = effectiveIsFullscreen;

  const handleUserClose = useCallback(() => {
    onUserClose?.();
    clearSidebarHistory();
    onClose();
  }, [onUserClose, onClose]);

  const {
    isMobile,
    animateIn,
    sidebarWidth,
    panelRef,
    indicatorRef,
    dragHandleRef,
    swipeElementRef,
    isResizing,
    justResized,
    handleResizeStart,
  } = useSidebarPanel({
    open,
    onClose: handleUserClose,
    widthStorageKey: WIDTH_STORAGE_KEY,
    widthCssVar: WIDTH_CSS_VAR,
    defaultWidthPct: DEFAULT_WIDTH_PCT,
    dataAttr: "data-sidebar-preview",
  });

  const viewMode = effectiveViewMode;

  const handleToggleViewMode = useCallback(() => {
    onUserInteraction?.();
    if (isViewModeControlled) {
      onViewModeChange!(viewMode === "sidebar" ? "center" : "sidebar");
      return;
    }
    setInternalViewMode((v) => {
      if (v === "center") {
        if (isFullscreen) {
          if (onFullscreenChange) onFullscreenChange(false);
          else if (externalIsFullscreen === undefined)
            setInternalIsFullscreen(false);
        }
      }
      return v === "sidebar" ? "center" : "sidebar";
    });
  }, [
    onUserInteraction,
    isViewModeControlled,
    onViewModeChange,
    viewMode,
    isFullscreen,
    onFullscreenChange,
    externalIsFullscreen,
  ]);

  const handleToggleFullscreen = useCallback(() => {
    onUserInteraction?.();
    const next = !isFullscreen;
    if (onFullscreenChange) {
      onFullscreenChange(next);
    } else if (externalIsFullscreen === undefined) {
      setInternalIsFullscreen(next);
    }
    if (next && viewMode === "sidebar" && !isViewModeControlled) {
      setInternalViewMode("center");
    }
  }, [
    onUserInteraction,
    isFullscreen,
    onFullscreenChange,
    externalIsFullscreen,
    viewMode,
    isViewModeControlled,
  ]);

  const panelOwnerRef = useRef(
    Symbol(`tool-result-panel:${title || "untitled"}`),
  );
  const latestOnCloseRef = useRef(onClose);

  // Track latest onClose for registry
  useEffect(() => {
    latestOnCloseRef.current = onClose;
  }, [onClose]);

  // Register as the active panel (singleton — closes any previous panel)
  useEffect(() => {
    if (!open) return;
    return registerToolPanel(
      panelOwnerRef.current,
      () => latestOnCloseRef.current(),
      registryKey,
    );
  }, [open, registryKey]);

  useEffect(() => {
    if (!open) {
      setContentReady(false);
      return;
    }

    setContentReady(false);

    const frameIds: number[] = [];
    frameIds.push(
      requestAnimationFrame(() => {
        frameIds.push(
          requestAnimationFrame(() => {
            setContentReady(true);
          }),
        );
      }),
    );

    return () => {
      frameIds.forEach((frameId) => cancelAnimationFrame(frameId));
    };
  }, [open, children]);

  // Override handleResizeStart to call onUserInteraction
  const handleResize = useCallback(
    (e: React.MouseEvent) => {
      onUserInteraction?.();
      handleResizeStart(e);
    },
    [onUserInteraction, handleResizeStart],
  );

  if (!open) return null;

  const cfg = statusConfig[status];
  const isCenter = viewMode === "center";
  const isSidebar = !isCenter;
  const hasCustomHeader = !!customHeader;

  const panelMode = isFullscreen
    ? "fullscreen"
    : isMobile
      ? "mobile"
      : isCenter
        ? "center"
        : "sidebar";

  const content = (
    <div
      className={`tool-console-panel w-full flex flex-col bg-theme-bg-card pointer-events-auto ${
        panelClass
          ? panelClass
          : isFullscreen
            ? "min-h-full min-w-full h-full w-full"
            : isMobile && mobileFillViewport
              ? "h-full"
              : isMobile
                ? `max-h-[92dvh] rounded-t-2xl overflow-hidden shadow-[0_-8px_40px_-8px_rgba(0,0,0,0.2)] dark:shadow-[0_-8px_40px_-8px_rgba(0,0,0,0.5)] ${
                    animateIn
                      ? "animate-[slide-up-fullscreen_280ms_cubic-bezier(0.16,1,0.3,1)_backwards]"
                      : ""
                  }`
                : isCenter
                  ? `overflow-hidden h-full relative transition-all duration-300 ease-out ${"sm:max-w-4xl lg:max-w-5xl xl:max-w-6xl sm:h-[80dvh] sm:rounded-2xl sm:my-auto"}`
                  : `h-full relative rounded-l-xl overflow-hidden shadow-[-4px_0_24px_-4px_rgba(0,0,0,0.12)] dark:shadow-[-4px_0_24px_-4px_rgba(0,0,0,0.4)] ${
                      animateIn
                        ? "animate-[slide-in-right_200ms_ease-out_backwards]"
                        : ""
                    }`
      }`}
      data-tool-panel-mode={panelMode}
      ref={(el) => {
        // Merge refs
        if (isMobile) {
          (panelRef as React.MutableRefObject<HTMLDivElement | null>).current =
            el;
          (
            swipeElementRef as React.MutableRefObject<HTMLElement | null>
          ).current = el;
        }
        if (!isMobile && isSidebar && !panelClass) {
          (panelRef as React.MutableRefObject<HTMLDivElement | null>).current =
            el;
        }
        if (typeof panelElementRef === "function") {
          panelElementRef(el);
        } else if (panelElementRef) {
          (
            panelElementRef as React.MutableRefObject<HTMLDivElement | null>
          ).current = el;
        }
      }}
      {...(isSidebar && !isMobile ? { "data-sidebar-panel": "" } : {})}
      style={
        isSidebar && !isMobile && !panelClass
          ? {
              maxWidth: `${sidebarWidth}%`,
              minWidth: "min(25vw, 400px)",
              ...(animateIn ? {} : { transform: "translateX(100%)" }),
            }
          : !animateIn && !panelClass && isMobile
            ? { transform: "translateY(100%)" }
            : undefined
      }
      onClick={(e) => e.stopPropagation()}
    >
      {/* Desktop resize handle (sidebar only, not when using custom panelClass) */}
      {isSidebar && !isMobile && !panelClass && (
        <>
          <div
            ref={indicatorRef}
            className="hidden sm:block fixed top-0 bottom-0 z-[201] pointer-events-none"
            style={{
              display: "none",
              left: 0,
              width: "2px",
              backgroundColor: "var(--theme-primary)",
              opacity: 0.4,
            }}
          />
          <div
            className="tool-console-resize-handle hidden sm:block absolute left-0 top-0 bottom-0 -translate-x-1/2 z-10 cursor-col-resize pointer-events-auto group"
            onMouseDown={handleResize}
          >
            <div className="tool-console-resize-handle__rail absolute inset-y-0 left-1/2 -translate-x-1/2 w-0.5 rounded-full bg-transparent transition-colors duration-200" />
          </div>
        </>
      )}

      {/* Header section — sidebar mode always; center/fullscreen mode; mobile always */}
      {(isSidebar || isMobile || isCenter || isFullscreen) && (
        <div
          ref={toolbarRef}
          className={`tool-console-chrome flex flex-col shrink-0 ${
            isFullscreen
              ? ""
              : "bg-gradient-to-r from-theme-bg-subtle to-theme-bg-card"
          }`}
        >
          {/* Mobile drag handle */}
          {isMobile && !isFullscreen && (
            <div ref={dragHandleRef} className="flex justify-center pt-4 pb-2">
              <div className="mobile-drag-handle w-9 h-1 rounded-full bg-theme-text-tertiary" />
            </div>
          )}
          {hasCustomHeader ? (
            customHeader
          ) : (
            <div className="tool-console-header flex items-center gap-2 px-2 sm:px-4 py-1.5 sm:py-2 border-b border-theme-border shrink-0 overflow-hidden">
              {/* Back button */}
              {effectiveOnBack && (
                <ToolbarIconButton
                  variant="muted"
                  onClick={() => {
                    effectiveOnBack();
                  }}
                  title={t("common.back", "Back")}
                  icon={<BackIcon size={16} />}
                />
              )}

              {/* Status + Icon */}
              <div
                className={`tool-console-header-icon flex items-center justify-center size-8 rounded-xl shrink-0 ${cfg.bg}`}
              >
                {status === "loading" ? (
                  <LoadingSpinner
                    size="sm"
                    className="shrink-0"
                    color={cfg.color || "text-[var(--theme-primary)]"}
                  />
                ) : (
                  <span className={cfg.color || "text-[var(--theme-primary)]"}>
                    {cfg.icon || icon}
                  </span>
                )}
              </div>

              {/* Title */}
              {title && (
                <div className="tool-console-title-row flex items-end gap-2 min-w-0 flex-1 overflow-hidden">
                  <h3
                    className="tool-console-title min-w-0 max-w-[40%] truncate font-medium text-sm text-theme-text"
                    title={title}
                  >
                    {title}
                  </h3>
                  {subtitle &&
                    (() => {
                      const segments = subtitle.split(/\s+/).filter(Boolean);
                      const isTagList =
                        segments.length > 1 &&
                        segments.every((s) => s.length <= 20);
                      if (!isTagList) {
                        return (
                          <span
                            className="tool-console-subtitle-pill inline-flex h-5 min-w-0 max-w-[45vw] sm:max-w-[min(32rem,52%)] items-end overflow-hidden px-0 pb-[1px] text-xs font-normal leading-none text-theme-text-tertiary"
                            title={subtitle}
                          >
                            <span className="block min-w-0 truncate">
                              {subtitle}
                            </span>
                          </span>
                        );
                      }
                      const maxVisible = 4;
                      const visible = segments.slice(0, maxVisible);
                      const overflow = segments.length - maxVisible;
                      return (
                        <div className="tool-console-subtitle-list inline-flex items-end gap-1 min-w-0 max-w-[45vw] sm:max-w-[min(32rem,52%)] overflow-hidden">
                          {visible.map((tag, i) => (
                            <span
                              key={i}
                              className="tool-console-subtitle-chip inline-flex items-end shrink-0 max-w-full px-0 h-5 pb-[1px] text-xs font-normal leading-none text-theme-text-tertiary"
                              title={tag}
                            >
                              <span className="block min-w-0 truncate">
                                {tag}
                              </span>
                            </span>
                          ))}
                          {overflow > 0 && (
                            <span className="tool-console-subtitle-overflow inline-flex items-end shrink-0 h-5 pb-[1px] text-xs font-normal leading-none text-theme-text-tertiary tabular-nums">
                              +{overflow}
                            </span>
                          )}
                        </div>
                      );
                    })()}
                </div>
              )}

              {/* Extra header actions */}
              {headerActions}

              {/* Center / Fullscreen / Close */}
              {!hideViewToggle && (
                <div className="tool-console-actions flex items-center gap-px sm:gap-1 shrink-0">
                  <ToolbarIconButton
                    variant="muted"
                    onClick={() => {
                      handleToggleViewMode();
                    }}
                    title={
                      isSidebar
                        ? t("documents.centerView", "Center view")
                        : t("documents.sidebarView", "Sidebar view")
                    }
                    icon={
                      isSidebar ? (
                        <Columns2 size={16} />
                      ) : (
                        <PanelRight size={16} />
                      )
                    }
                  />
                  <ToolbarIconButton
                    variant="muted"
                    onClick={() => {
                      handleToggleFullscreen();
                    }}
                    title={
                      isFullscreen
                        ? t("documents.exitFullscreen")
                        : t("documents.fullscreen")
                    }
                    icon={
                      isFullscreen ? <Shrink size={16} /> : <Expand size={16} />
                    }
                  />
                  <ToolbarIconButton
                    variant="muted"
                    onClick={() => {
                      handleUserClose();
                    }}
                    title={t("common.close")}
                    aria-label={t("common.close")}
                    icon={<X size={16} />}
                  />
                </div>
              )}
              {hideViewToggle && (
                <div className="tool-console-actions flex items-center gap-px sm:gap-1 shrink-0">
                  <ToolbarIconButton
                    variant="muted"
                    onClick={() => {
                      handleUserClose();
                    }}
                    aria-label={t("common.close")}
                    title={t("common.close")}
                    icon={<X size={16} />}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Content */}
      <div
        className={`tool-console-body relative flex-1 overflow-auto min-h-0 overscroll-contain ${
          isCenter && !hasCustomHeader && !isMobile && !isFullscreen
            ? "!overflow-hidden"
            : ""
        }`}
        aria-busy={!contentReady}
      >
        <div
          className={`tool-console-body__content h-full min-h-full transition-opacity duration-150 ${
            contentReady ? "opacity-100" : "opacity-0"
          }`}
          aria-hidden={!contentReady}
        >
          {children}
        </div>
        {!contentReady && (
          <div className="tool-console-body__loading absolute inset-0 z-[1] flex items-center justify-center">
            <LoadingSpinner
              size="md"
              color="text-theme-text-tertiary"
              className="shrink-0"
            />
          </div>
        )}
      </div>

      {/* Footer */}
      {footer && <div className="tool-console-footer shrink-0">{footer}</div>}
    </div>
  );

  return createPortal(
    <div
      className={`fixed inset-0 z-[200] flex flex-col ${
        isFullscreen
          ? "bg-transparent pointer-events-none"
          : "safe-area-viewport-padding"
      } ${
        overlayClass
          ? overlayClass
          : isFullscreen
            ? "bg-transparent pointer-events-none"
            : isMobile && mobileFillViewport
              ? "bg-black/50"
              : isMobile
                ? "bg-black/50 items-end justify-end"
                : isCenter
                  ? "sm:items-center sm:justify-center bg-black/70"
                  : "bg-black/50 sm:bg-transparent sm:pointer-events-none sm:items-end sm:justify-stretch"
      }`}
      onClick={() => {
        if (!isResizing.current && !justResized.current) handleUserClose();
      }}
    >
      {content}
    </div>,
    document.body,
  );
}
