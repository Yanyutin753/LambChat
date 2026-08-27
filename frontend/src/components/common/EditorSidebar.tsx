import { useCallback, useId } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { useSidebarPanel } from "../../hooks/useSidebarPanel";
import { BackIcon } from "./BackIcon";
import { ToolbarIconButton } from "./ui/ToolbarIconButton";
import { useRightPanelEntry, useRightPanelFocus } from "./useRightPanelEntry";

const STORAGE_KEY = "editor-sidebar-width";
const CSS_VAR = "--editor-sidebar-width";
const DEFAULT_WIDTH = 34;

export interface EditorSidebarProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: React.ReactNode;
  icon?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  /** "default" (34%) | "wide" (larger min-width) */
  width?: "default" | "wide";
  defaultWidthPct?: number;
  widthStorageKey?: string;
}

export function EditorSidebar({
  open,
  onClose,
  title,
  subtitle,
  icon,
  children,
  footer,
  width = "default",
  defaultWidthPct = DEFAULT_WIDTH,
  widthStorageKey = STORAGE_KEY,
}: EditorSidebarProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const entry = useRightPanelEntry({
    open,
    onClose,
    kind: "editor",
  });
  const shell = useSidebarPanel({
    open: entry.active,
    onClose,
    kind: "editor",
    widthStorageKey,
    widthCssVar: CSS_VAR,
    defaultWidthPct,
    minPanelPx: width === "wide" ? 400 : 320,
    dataAttr: "data-editor-sidebar",
  });

  useRightPanelFocus({
    open,
    active: entry.active,
    automatic: false,
    presentation: shell.presentation,
    panelRef: shell.panelRef,
    openerRef: entry.openerRef,
  });

  const handleOverlayClick = useCallback(() => {
    if (shell.justResized.current) return;
    onClose();
  }, [onClose, shell.justResized]);

  if (!open) return null;

  const isDocked = shell.presentation === "docked";
  const isFullscreen = shell.presentation === "fullscreen";
  const closeLabel = t("common.close", "Close");
  const backLabel = t("common.back", "Back");
  const resizeLabel = t("common.resizePanel", "Resize panel");

  return createPortal(
    <>
      {!isDocked && (
        <div
          className={`editor-sidebar-overlay ${
            shell.animateIn ? "editor-sidebar-overlay--visible" : ""
          }`}
          hidden={!entry.active}
          aria-hidden="true"
          onClick={handleOverlayClick}
        />
      )}

      <div
        ref={shell.panelRef}
        data-right-panel-root
        data-panel-kind="editor"
        data-panel-presentation={shell.presentation}
        hidden={!entry.active}
        aria-hidden={!entry.active ? true : undefined}
        inert={!entry.active ? true : undefined}
        role={isDocked ? "complementary" : "dialog"}
        aria-modal={isDocked ? undefined : true}
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`editor-sidebar right-panel-shell right-panel-shell--${
          shell.presentation
        } ${
          isFullscreen ? "editor-sidebar--mobile" : "editor-sidebar--sidebar"
        } ${width === "wide" ? "editor-sidebar--wide" : ""} ${
          shell.animateIn ? "editor-sidebar--animate-in" : ""
        }`}
        style={
          isFullscreen
            ? undefined
            : { width: `var(${CSS_VAR}, ${DEFAULT_WIDTH}%)` }
        }
        onClick={(event) => event.stopPropagation()}
      >
        {isDocked && (
          <>
            <div
              ref={shell.indicatorRef}
              className="hidden sm:block fixed top-0 bottom-0 z-[301] pointer-events-none"
              style={{
                display: "none",
                left: 0,
                width: "2px",
                backgroundColor: "var(--theme-primary)",
                opacity: 0.4,
              }}
            />
            <div
              className="right-panel-resize-handle hidden sm:block absolute left-0 top-0 bottom-0 -translate-x-1/2 z-10 cursor-col-resize pointer-events-auto group"
              aria-label={resizeLabel}
              {...shell.resizeSeparatorProps}
              onMouseDown={shell.handleResizeStart}
            >
              <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-1 rounded-full bg-transparent group-hover:bg-[var(--theme-primary)]/50 transition-colors duration-200" />
            </div>
          </>
        )}

        <div className="flex flex-col shrink-0 bg-gradient-to-r from-stone-50 to-white dark:from-stone-800 dark:to-[#292524]">
          <div className="editor-sidebar-header">
            <div className="editor-sidebar-header-left">
              {entry.hasPrevious && (
                <ToolbarIconButton
                  variant="muted"
                  onClick={onClose}
                  aria-label={backLabel}
                  title={backLabel}
                  icon={<BackIcon size={16} />}
                />
              )}
              {icon && <div className="editor-sidebar-header-icon">{icon}</div>}
              <div className="min-w-0">
                <div
                  id={titleId}
                  className="editor-sidebar-header-title font-serif"
                >
                  {title}
                </div>
                {subtitle && (
                  <div className="editor-sidebar-header-subtitle">
                    {subtitle}
                  </div>
                )}
              </div>
            </div>
            <ToolbarIconButton
              variant="muted"
              onClick={onClose}
              className="editor-sidebar-close-btn"
              aria-label={closeLabel}
              title={closeLabel}
              icon={<X size={16} />}
            />
          </div>
        </div>

        <div className="editor-sidebar-body">{children}</div>

        {footer && <div className="editor-sidebar-footer">{footer}</div>}
      </div>
    </>,
    document.body,
  );
}
