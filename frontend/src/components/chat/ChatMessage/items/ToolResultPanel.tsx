/* eslint-disable react-refresh/only-export-components */
import {
  useState,
  useEffect,
  useRef,
  useCallback,
  useLayoutEffect,
} from "react";
import { createPortal } from "react-dom";
import { X, CheckCircle, XCircle, Ban } from "lucide-react";
import { LoadingSpinner } from "../../../common";

import { useSwipeToClose } from "../../../../hooks/useSwipeToClose";
import type { CollapsibleStatus } from "../../../common/CollapsiblePill";
import { registerToolPanel } from "./toolPanelRegistry";
export { closeCurrentToolPanel } from "./toolPanelRegistry";

// Reference counter so that the old panel's cleanup cannot remove the attribute
// while the new panel is still open (useLayoutEffect cleanup fires in a later
// render cycle than the new panel's setup).
let _compressionCount = 0;

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
  /** Called when the user explicitly manipulates the panel UI */
  onUserInteraction?: () => void;
}

const statusConfig: Record<
  CollapsibleStatus,
  { bg: string; color: string; icon: React.ReactNode }
> = {
  idle: {
    bg: "bg-stone-100 dark:bg-stone-800",
    color: "text-stone-500 dark:text-stone-400",
    icon: null,
  },
  loading: {
    bg: "bg-amber-100/80 dark:bg-amber-900/30",
    color: "text-amber-600 dark:text-amber-400",
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
    bg: "bg-amber-100/80 dark:bg-amber-900/30",
    color: "text-amber-600 dark:text-amber-400",
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
  viewMode = "sidebar",
  headerActions,
  customHeader,
  footer,
  overlayClass,
  panelClass,
  panelElementRef,
  onUserInteraction,
}: ToolResultPanelProps) {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 640);
  const [animateIn, setAnimateIn] = useState(false);

  // Double-rAF: first frame paints the panel off-screen (translate-y-full),
  // second frame kicks off the slide-in animation.  This guarantees zero
  // white flash on all browsers — a single rAF can still leak one painted
  // frame on mobile WebKit.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    requestAnimationFrame(() => {
      if (cancelled) return;
      requestAnimationFrame(() => {
        if (cancelled) return;
        setAnimateIn(true);
      });
    });
    return () => {
      cancelled = true;
    };
  }, [open]);
  const panelOwnerRef = useRef(
    Symbol(`tool-result-panel:${title || "untitled"}`),
  );
  const latestOnCloseRef = useRef(onClose);
  const [sidebarWidth, setSidebarWidth] = useState(
    () =>
      parseInt(localStorage.getItem("sidebar-preview-width") || "35", 10) || 35,
  );
  const panelRef = useRef<HTMLDivElement>(null);
  const indicatorRef = useRef<HTMLDivElement>(null);
  const isResizing = useRef(false);
  const justResized = useRef(false);
  const resizeCaptureRef = useRef<HTMLDivElement | null>(null);
  const resizeListenersRef = useRef<{
    move: (ev: MouseEvent) => void;
    up: (ev: MouseEvent) => void;
  } | null>(null);

  // Track viewport size
  useEffect(() => {
    latestOnCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    setIsMobile(mq.matches); // set initial value immediately
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // Persist sidebar width
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--sidebar-preview-width",
      `${sidebarWidth}%`,
    );
    localStorage.setItem("sidebar-preview-width", String(sidebarWidth));
  }, [sidebarWidth]);

  // Layout-level side-effects (run synchronously before paint to prevent flash).
  // Combined into a single useLayoutEffect to avoid multiple layout flushes.
  useLayoutEffect(() => {
    if (!open) return;

    // Desktop sidebar: signal main layout compression
    if (!isMobile && viewMode !== "center") {
      _compressionCount++;
      if (_compressionCount === 1) {
        document.documentElement.setAttribute("data-sidebar-preview", "open");
      }
    }

    // Mobile bottom-sheet / center fullscreen: lock body scroll
    if (isMobile || viewMode === "center") {
      const scrollbarWidth =
        window.innerWidth - document.documentElement.clientWidth;
      document.body.style.overflow = "hidden";
      if (scrollbarWidth > 0) {
        document.body.style.paddingRight = `${scrollbarWidth}px`;
      }
    }

    return () => {
      if (!isMobile && viewMode !== "center") {
        _compressionCount--;
        if (_compressionCount === 0) {
          document.documentElement.removeAttribute("data-sidebar-preview");
        }
      }
      if (isMobile || viewMode === "center") {
        document.body.style.overflow = "";
        document.body.style.paddingRight = "";
      }
    };
  }, [open, isMobile, viewMode]);

  // ESC key
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (document.fullscreenElement) return;
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Register as the active panel (singleton — closes any previous panel)
  useEffect(() => {
    if (!open) return;
    return registerToolPanel(panelOwnerRef.current, () =>
      latestOnCloseRef.current(),
    );
  }, [open]);

  // Cleanup drag resize resources (used on mouseup and on unmount)
  const cleanupResize = useCallback((indicator: HTMLDivElement | null) => {
    isResizing.current = false;
    if (indicator) indicator.style.display = "none";
    const capture = resizeCaptureRef.current;
    if (capture) {
      capture.remove();
      resizeCaptureRef.current = null;
    }
    const listeners = resizeListenersRef.current;
    if (listeners) {
      window.removeEventListener("mousemove", listeners.move);
      window.removeEventListener("mouseup", listeners.up);
      resizeListenersRef.current = null;
    }
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  // Cleanup resize on unmount to prevent leaked DOM/listeners
  useEffect(() => {
    const indicator = indicatorRef.current;
    return () => {
      if (isResizing.current) cleanupResize(indicator);
    };
  }, [cleanupResize]);

  // Desktop drag resize
  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      onUserInteraction?.();
      isResizing.current = true;
      const startX = e.clientX;
      const root = document.documentElement;
      const startWidth = parseInt(
        root.style.getPropertyValue("--sidebar-preview-width") ||
          String(sidebarWidth),
        10,
      );
      const indicator = indicatorRef.current;

      const capture = document.createElement("div");
      capture.style.cssText =
        "position:fixed;inset:0;z-index:999999;cursor:col-resize;";
      document.body.appendChild(capture);
      resizeCaptureRef.current = capture;

      const onMove = (ev: MouseEvent) => {
        if (!isResizing.current) return;
        if (indicator) {
          indicator.style.left = `${ev.clientX}px`;
          indicator.style.display = "block";
        }
      };
      const onUp = (ev: MouseEvent) => {
        if (!isResizing.current) return;
        cleanupResize(indicator);
        const delta = ((startX - ev.clientX) / window.innerWidth) * 100;
        const val = Math.round(Math.min(Math.max(startWidth + delta, 25), 75));
        root.style.setProperty("--sidebar-preview-width", `${val}%`);
        setSidebarWidth(val);
        if (panelRef.current) panelRef.current.style.maxWidth = `${val}%`;
        localStorage.setItem("sidebar-preview-width", String(val));
        justResized.current = true;
        setTimeout(() => {
          justResized.current = false;
        }, 100);
      };
      resizeListenersRef.current = { move: onMove, up: onUp };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [sidebarWidth, cleanupResize, onUserInteraction],
  );

  // Mobile swipe to close
  const sheetRef = useSwipeToClose({
    onClose,
    enabled: open && isMobile,
  });

  if (!open) return null;

  const cfg = statusConfig[status];
  const isCenter = viewMode === "center";
  const isSidebar = !isCenter;
  const hasCustomHeader = !!customHeader;

  const content = (
    <div
      className={`w-full flex flex-col bg-white dark:bg-[#1e1e1e] pointer-events-auto ${
        panelClass
          ? panelClass
          : isCenter
            ? "overflow-hidden h-full relative"
            : isMobile
              ? `max-h-[92vh] rounded-t-2xl overflow-hidden shadow-[0_-8px_40px_-8px_rgba(0,0,0,0.2)] dark:shadow-[0_-8px_40px_-8px_rgba(0,0,0,0.5)] ${
                  animateIn
                    ? "animate-[slide-up-fullscreen_280ms_cubic-bezier(0.16,1,0.3,1)_backwards]"
                    : ""
                }`
              : `h-full relative shadow-[-4px_0_24px_-4px_rgba(0,0,0,0.12)] dark:shadow-[-4px_0_24px_-4px_rgba(0,0,0,0.4)] ${
                  animateIn
                    ? "animate-[slide-in-right_200ms_ease-out_backwards]"
                    : ""
                }`
      }`}
      ref={(el) => {
        // Merge refs
        if (isMobile && !isCenter && sheetRef) {
          (sheetRef as React.MutableRefObject<HTMLElement | null>).current = el;
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
              minWidth: "min(400px, 80vw)",
              ...(animateIn ? {} : { transform: "translateX(100%)" }),
            }
          : !animateIn && !panelClass && !isCenter
            ? isMobile
              ? { transform: "translateY(100%)" }
              : undefined
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
            className="hidden sm:block absolute left-0 top-0 bottom-0 -translate-x-1/2 z-10 cursor-col-resize pointer-events-auto group"
            onMouseDown={handleResizeStart}
          >
            <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-1 rounded-full bg-transparent group-hover:bg-[var(--theme-primary)]/50 transition-colors duration-200" />
          </div>
        </>
      )}

      {/* Header section — sidebar mode always; center mode only when customHeader is provided */}
      {(isSidebar || (isCenter && hasCustomHeader)) && (
        <div className="flex flex-col shrink-0 bg-gradient-to-r from-stone-50 to-white dark:from-stone-800/50 dark:to-[#1e1e1e]">
          {/* Mobile drag handle — sidebar mode only */}
          {isMobile && isSidebar && (
            <div className="flex justify-center pt-2 pb-1">
              <div className="w-9 h-1 rounded-full bg-stone-300 dark:bg-stone-600" />
            </div>
          )}
          {hasCustomHeader ? (
            customHeader
          ) : (
            <div className="flex items-center gap-2 sm:gap-3 px-2 sm:px-4 py-2 sm:py-3 border-b border-stone-200 dark:border-stone-700 shrink-0 whitespace-nowrap">
              {/* Status + Icon */}
              <div
                className={`flex items-center justify-center size-10 rounded-xl shrink-0 ${cfg.bg}`}
              >
                {status === "loading" ? (
                  <LoadingSpinner
                    size="sm"
                    className="shrink-0"
                    color={cfg.color || "text-blue-600 dark:text-blue-400"}
                  />
                ) : (
                  <span
                    className={cfg.color || "text-blue-600 dark:text-blue-400"}
                  >
                    {cfg.icon || icon}
                  </span>
                )}
              </div>

              {/* Title */}
              {title && (
                <div className="flex-1 min-w-0">
                  <h3
                    className="font-medium text-sm text-stone-900 dark:text-stone-100 truncate"
                    title={title}
                  >
                    {title}
                  </h3>
                  {subtitle && (
                    <p
                      className="text-xs text-stone-500 dark:text-stone-400 mt-0.5 truncate"
                      title={subtitle}
                    >
                      {subtitle}
                    </p>
                  )}
                </div>
              )}

              {/* Extra header actions */}
              {headerActions}

              {/* Close */}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onClose();
                }}
                className="flex items-center justify-center size-10 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800 active:bg-stone-200 dark:active:bg-stone-700 text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 transition-colors duration-150 active:scale-95 cursor-pointer shrink-0"
                aria-label="Close"
              >
                <X size={16} className="sm:w-[18px] sm:h-[18px]" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Floating close button (center mode only, no customHeader) */}
      {isCenter && !hasCustomHeader && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onClose();
          }}
          className="absolute top-3 right-3 z-[310] flex items-center justify-center w-10 h-10 rounded-full bg-black/70 hover:bg-black/90 text-white shadow-lg transition-all duration-200 cursor-pointer"
          aria-label="Close"
        >
          <X size={18} />
        </button>
      )}

      {/* Content */}
      <div
        className={`flex-1 overflow-auto min-h-0 overscroll-contain ${
          isCenter && !hasCustomHeader ? "!overflow-hidden" : ""
        }`}
      >
        {children}
      </div>

      {/* Footer */}
      {footer && <div className="shrink-0">{footer}</div>}
    </div>
  );

  return createPortal(
    <div
      className={`fixed inset-0 z-[200] flex flex-col ${
        overlayClass
          ? overlayClass
          : isCenter
            ? "bg-stone-900"
            : isMobile
              ? "bg-black/50 items-end justify-end"
              : "bg-black/50 sm:bg-transparent sm:pointer-events-none sm:items-end sm:justify-stretch"
      }`}
      onClick={() => {
        if (!isResizing.current && !justResized.current) onClose();
      }}
    >
      {content}
    </div>,
    document.body,
  );
}
