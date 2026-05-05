import {
  useState,
  useEffect,
  useRef,
  useCallback,
  useLayoutEffect,
} from "react";
import { X } from "lucide-react";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";

const STORAGE_KEY = "editor-sidebar-width";
const MIN_WIDTH = 320;
const MAX_WIDTH_RATIO = 0.75;
const DEFAULT_WIDTH_PCT = 30;

export interface EditorSidebarProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: React.ReactNode;
  icon?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  /** "default" (400px) | "wide" (500px) */
  width?: "default" | "wide";
}

// Track open count so multiple sidebars don't fight over the HTML attribute
let _compressCount = 0;

export function EditorSidebar({
  open,
  onClose,
  title,
  subtitle,
  icon,
  children,
  footer,
  width = "default",
}: EditorSidebarProps) {
  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia("(max-width: 639px)").matches,
  );
  const [animateIn, setAnimateIn] = useState(false);
  const dragHandleRef = useRef<HTMLDivElement | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  // --- Resize state ---
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return parseInt(stored, 10) || DEFAULT_WIDTH_PCT;
    return DEFAULT_WIDTH_PCT;
  });
  const indicatorRef = useRef<HTMLDivElement>(null);
  const isResizing = useRef(false);
  const justResized = useRef(false);
  const resizeCaptureRef = useRef<HTMLDivElement | null>(null);
  const resizeListenersRef = useRef<{
    move: (ev: MouseEvent) => void;
    up: (ev: MouseEvent) => void;
  } | null>(null);

  // Persist width to CSS variable + localStorage
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--editor-sidebar-width",
      `${sidebarWidth}%`,
    );
    localStorage.setItem(STORAGE_KEY, String(sidebarWidth));
  }, [sidebarWidth]);

  // Cleanup drag resize resources
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

  // Cleanup on unmount
  useEffect(() => {
    const indicator = indicatorRef.current;
    return () => {
      if (isResizing.current) cleanupResize(indicator);
    };
  }, [cleanupResize]);

  // Desktop drag resize handler
  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      isResizing.current = true;
      const startX = e.clientX;
      const startWidth = sidebarWidth;
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
        const maxW = MAX_WIDTH_RATIO * 100;
        const val = Math.round(
          Math.min(
            Math.max(startWidth + delta, (MIN_WIDTH / window.innerWidth) * 100),
            maxW,
          ),
        );
        setSidebarWidth(val);
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
    [sidebarWidth, cleanupResize],
  );

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // Double-RAF animation to prevent flash
  useEffect(() => {
    if (!open) return;
    setAnimateIn(false);
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

  // Compress main layout on desktop
  useLayoutEffect(() => {
    if (!open || isMobile) return;
    _compressCount++;
    if (_compressCount === 1) {
      document.documentElement.setAttribute("data-editor-sidebar", "open");
    }
    return () => {
      _compressCount--;
      if (_compressCount === 0) {
        document.documentElement.removeAttribute("data-editor-sidebar");
      }
    };
  }, [open, isMobile]);

  // Mobile body scroll lock
  useEffect(() => {
    if (open && isMobile) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open, isMobile]);

  // ESC to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.fullscreenElement) {
        onClose();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Swipe to close on mobile
  const swipeRef = useSwipeToClose({
    onClose,
    enabled: open && isMobile,
    dragHandleRef,
    scrollContainerRef: bodyRef,
  });

  const setRef = useCallback(
    (el: HTMLDivElement | null) => {
      panelRef.current = el;
      if (isMobile && swipeRef) {
        (swipeRef as React.RefObject<HTMLDivElement | null>).current = el;
      }
      if (!isMobile && dragHandleRef.current) {
        dragHandleRef.current = el;
      }
    },
    [isMobile, swipeRef],
  );

  // Overlay click — ignore if just resized
  const handleOverlayClick = useCallback(() => {
    if (justResized.current) return;
    onClose();
  }, [onClose]);

  if (!open) return null;

  return (
    <>
      {/* Overlay */}
      <div
        className={`editor-sidebar-overlay ${
          animateIn ? "editor-sidebar-overlay--visible" : ""
        }`}
        onClick={handleOverlayClick}
      />

      {/* Panel */}
      <div
        ref={setRef}
        className={`editor-sidebar ${
          isMobile ? "editor-sidebar--mobile" : "editor-sidebar--sidebar"
        } ${width === "wide" ? "editor-sidebar--wide" : ""} ${
          animateIn ? "editor-sidebar--animate-in" : ""
        }`}
        style={
          !isMobile
            ? { width: `var(--editor-sidebar-width, ${DEFAULT_WIDTH_PCT}%)` }
            : undefined
        }
        onClick={(e) => e.stopPropagation()}
      >
        {/* Desktop resize handle */}
        {!isMobile && (
          <>
            <div
              ref={indicatorRef}
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
              className="hidden sm:block absolute left-0 top-0 bottom-0 -translate-x-1/2 z-10 cursor-col-resize pointer-events-auto group"
              onMouseDown={handleResizeStart}
            >
              <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-1 rounded-full bg-transparent group-hover:bg-[var(--theme-primary)]/50 transition-colors duration-200" />
            </div>
          </>
        )}

        {/* Mobile drag handle */}
        {isMobile && (
          <div ref={dragHandleRef} className="editor-sidebar-drag-handle" />
        )}

        {/* Header */}
        <div className="editor-sidebar-header">
          <div className="editor-sidebar-header-left">
            {icon && <div className="editor-sidebar-header-icon">{icon}</div>}
            <div className="min-w-0">
              <div className="editor-sidebar-header-title">{title}</div>
              {subtitle && (
                <div className="editor-sidebar-header-subtitle hidden sm:block">
                  {subtitle}
                </div>
              )}
            </div>
          </div>
          <button onClick={onClose} className="editor-sidebar-close-btn">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div ref={bodyRef} className="editor-sidebar-body">
          {children}
        </div>

        {/* Footer (outside scroll area) */}
        {footer && <div className="editor-sidebar-footer">{footer}</div>}
      </div>
    </>
  );
}
