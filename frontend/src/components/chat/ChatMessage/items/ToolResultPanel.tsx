/* eslint-disable react-refresh/only-export-components */
import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { X, CheckCircle, XCircle, Ban } from "lucide-react";
import { LoadingSpinner } from "../../../common";
import { useSwipeToClose } from "../../../../hooks/useSwipeToClose";
import type { CollapsibleStatus } from "../../../common/CollapsiblePill";

// Module-level singleton: only one panel open at a time
let _currentClose: (() => void) | null = null;

/** Close any currently open ToolResultPanel (call before opening a new one) */
export function closeCurrentToolPanel() {
  if (_currentClose) {
    _currentClose();
    _currentClose = null;
  }
}

interface ToolResultPanelProps {
  open: boolean;
  onClose: () => void;
  title: string;
  icon: React.ReactNode;
  status: CollapsibleStatus;
  subtitle?: string;
  children: React.ReactNode;
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
    icon: <CheckCircle size={14} />,
  },
  error: {
    bg: "bg-red-100/80 dark:bg-red-900/30",
    color: "text-red-600 dark:text-red-400",
    icon: <XCircle size={14} />,
  },
  cancelled: {
    bg: "bg-amber-100/80 dark:bg-amber-900/30",
    color: "text-amber-600 dark:text-amber-400",
    icon: <Ban size={14} />,
  },
};

export function ToolResultPanel({
  open,
  onClose,
  title,
  icon,
  status,
  subtitle,
  children,
}: ToolResultPanelProps) {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 640);
  const [sidebarWidth, setSidebarWidth] = useState(() =>
    parseInt(localStorage.getItem("sidebar-preview-width") || "45", 10),
  );
  const panelRef = useRef<HTMLDivElement>(null);
  const indicatorRef = useRef<HTMLDivElement>(null);
  const isResizing = useRef(false);
  const justResized = useRef(false);

  // Track viewport size
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
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

  // Signal main layout compression (desktop sidebar mode)
  useEffect(() => {
    if (!open || isMobile) return;
    document.documentElement.setAttribute("data-sidebar-preview", "open");
    return () =>
      document.documentElement.removeAttribute("data-sidebar-preview");
  }, [open, isMobile]);

  // Body scroll lock
  useEffect(() => {
    if (!open) return;
    if (!isMobile) return; // sidebar mode keeps scroll
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open, isMobile]);

  // ESC key
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Register as the active panel (singleton — closes any previous panel)
  useEffect(() => {
    if (!open) return;
    _currentClose = onClose;
    return () => {
      if (_currentClose === onClose) _currentClose = null;
    };
  }, [open, onClose]);

  // Desktop drag resize
  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
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

      const onMove = (ev: MouseEvent) => {
        if (!isResizing.current) return;
        if (indicator) {
          indicator.style.left = `${ev.clientX}px`;
          indicator.style.display = "block";
        }
      };
      const onUp = (ev: MouseEvent) => {
        if (!isResizing.current) return;
        isResizing.current = false;
        if (indicator) indicator.style.display = "none";
        capture.remove();
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
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
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [sidebarWidth],
  );

  // Mobile swipe to close
  const sheetRef = useSwipeToClose({
    onClose,
    enabled: open && isMobile,
  });

  if (!open) return null;

  const cfg = statusConfig[status];

  const content = (
    <div
      className={`w-full flex flex-col bg-white dark:bg-[#1e1e1e] pointer-events-auto ${
        isMobile
          ? "max-h-[92vh] rounded-t-2xl overflow-hidden shadow-[0_-8px_40px_-8px_rgba(0,0,0,0.2)] dark:shadow-[0_-8px_40px_-8px_rgba(0,0,0,0.5)] animate-[slide-up-fullscreen_280ms_cubic-bezier(0.16,1,0.3,1)]"
          : "h-full sm:rounded-l-2xl relative shadow-[-4px_0_24px_-4px_rgba(0,0,0,0.12)] dark:shadow-[-4px_0_24px_-4px_rgba(0,0,0,0.4)] animate-[slide-in-right_200ms_ease-out]"
      }`}
      ref={(el) => {
        // Merge refs
        if (isMobile && sheetRef) {
          (sheetRef as React.MutableRefObject<HTMLElement | null>).current = el;
        }
        if (!isMobile) {
          (panelRef as React.MutableRefObject<HTMLDivElement | null>).current =
            el;
        }
      }}
      {...(!isMobile ? { "data-sidebar-panel": "" } : {})}
      style={
        !isMobile
          ? { maxWidth: `${sidebarWidth}%`, minWidth: "min(320px, 80vw)" }
          : undefined
      }
      onClick={(e) => e.stopPropagation()}
    >
      {/* Desktop resize handle */}
      {!isMobile && (
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

      {/* Header */}
      <div className="flex flex-col shrink-0 bg-gradient-to-r from-stone-50 to-white dark:from-[#252526] dark:to-[#1e1e1e]">
        {/* Mobile drag handle */}
        {isMobile && (
          <div className="flex justify-center pt-2 pb-1">
            <div className="w-9 h-1 rounded-full bg-stone-300 dark:bg-stone-600" />
          </div>
        )}
        <div className="flex items-center gap-2.5 px-4 sm:px-5 py-3 sm:py-4 border-b border-stone-200 dark:border-[#333]">
          {/* Status + Icon */}
          <div className="flex items-center gap-2 shrink-0">
            {status === "loading" ? (
              <LoadingSpinner
                size="xs"
                className="shrink-0"
                color="text-amber-500 dark:text-amber-400"
              />
            ) : (
              <div
                className={`flex items-center justify-center w-7 h-7 rounded-lg ${cfg.bg}`}
              >
                <span className={cfg.color}>{cfg.icon || icon}</span>
              </div>
            )}
          </div>

          {/* Title */}
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-stone-900 dark:text-stone-100 text-base truncate">
              {title}
            </h3>
            {subtitle && (
              <p className="text-xs text-stone-400 dark:text-stone-500 truncate mt-0.5">
                {subtitle}
              </p>
            )}
          </div>

          {/* Close */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
            className="flex items-center justify-center w-9 h-9 rounded-xl hover:bg-stone-200/80 dark:hover:bg-stone-700/60 active:bg-stone-200 dark:active:bg-stone-600/60 transition-all duration-200 active:scale-95 cursor-pointer shrink-0"
            aria-label="Close"
          >
            <X size={18} className="text-stone-500 dark:text-stone-400" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto min-h-0 overscroll-contain">
        {children}
      </div>
    </div>
  );

  return createPortal(
    <div
      className={`fixed inset-0 z-[300] flex flex-col ${
        isMobile
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
