import {
  useState,
  useEffect,
  useRef,
  useCallback,
  useLayoutEffect,
} from "react";
import { useSwipeToClose } from "./useSwipeToClose";
import { notifyRightPanelWidthChanged } from "./rightPanelWidthEvents";

export interface SidebarPanelOptions {
  open: boolean;
  onClose: () => void;
  /** localStorage key for persisting sidebar width */
  widthStorageKey: string;
  /** CSS variable name for sidebar width */
  widthCssVar: string;
  /** Default width percentage */
  defaultWidthPct?: number;
  /** data-attribute name set on <html> when sidebar is open on desktop (e.g. "data-sidebar-preview") */
  dataAttr?: string;
}

export interface SidebarPanelReturn {
  isMobile: boolean;
  animateIn: boolean;
  sidebarWidth: number;
  panelRef: React.RefObject<HTMLDivElement | null>;
  indicatorRef: React.RefObject<HTMLDivElement | null>;
  dragHandleRef: React.RefObject<HTMLDivElement | null>;
  swipeElementRef: React.RefObject<HTMLElement | null>;
  isResizing: React.MutableRefObject<boolean>;
  justResized: React.MutableRefObject<boolean>;
  handleResizeStart: (e: React.MouseEvent) => void;
}

const _compressCounts = new Map<string, number>();

export function useSidebarPanel({
  open,
  onClose,
  widthStorageKey,
  widthCssVar,
  defaultWidthPct = 35,
  dataAttr = "data-sidebar-preview",
}: SidebarPanelOptions): SidebarPanelReturn {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 640);
  const [animateIn, setAnimateIn] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(
    () =>
      parseInt(
        localStorage.getItem(widthStorageKey) || String(defaultWidthPct),
        10,
      ) || defaultWidthPct,
  );

  const panelRef = useRef<HTMLDivElement>(null);
  const indicatorRef = useRef<HTMLDivElement>(null);
  const dragHandleRef = useRef<HTMLDivElement>(null);
  const isResizing = useRef(false);
  const justResized = useRef(false);
  const resizeCaptureRef = useRef<HTMLDivElement | null>(null);
  const resizeListenersRef = useRef<{
    move: (ev: MouseEvent) => void;
    up: (ev: MouseEvent) => void;
  } | null>(null);

  // Mobile detection
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // Double-rAF animation to prevent flash
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

  // Persist sidebar width
  useEffect(() => {
    document.documentElement.style.setProperty(widthCssVar, `${sidebarWidth}%`);
    localStorage.setItem(widthStorageKey, String(sidebarWidth));
    notifyRightPanelWidthChanged();
  }, [sidebarWidth, widthCssVar, widthStorageKey]);

  // Layout compression + body scroll lock
  useLayoutEffect(() => {
    if (!open) return;

    if (!isMobile) {
      const prev = _compressCounts.get(dataAttr) || 0;
      _compressCounts.set(dataAttr, prev + 1);
      if (prev === 0) {
        document.documentElement.setAttribute(dataAttr, "open");
      }
    }

    if (isMobile) {
      const scrollbarWidth =
        window.innerWidth - document.documentElement.clientWidth;
      document.body.style.overflow = "hidden";
      if (scrollbarWidth > 0) {
        document.body.style.paddingRight = `${scrollbarWidth}px`;
      }
    }

    return () => {
      if (!isMobile) {
        const prev = _compressCounts.get(dataAttr) || 1;
        _compressCounts.set(dataAttr, prev - 1);
        if (prev === 1) {
          document.documentElement.removeAttribute(dataAttr);
        }
      }
      if (isMobile) {
        document.body.style.overflow = "";
        document.body.style.paddingRight = "";
      }
    };
  }, [open, isMobile, dataAttr]);

  // ESC to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (document.fullscreenElement) return;
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

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

  // Desktop drag resize
  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      isResizing.current = true;
      const startX = e.clientX;
      const root = document.documentElement;
      const startWidth = parseInt(
        root.style.getPropertyValue(widthCssVar) || String(sidebarWidth),
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
        root.style.setProperty(widthCssVar, `${val}%`);
        setSidebarWidth(val);
        localStorage.setItem(widthStorageKey, String(val));
        notifyRightPanelWidthChanged();
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
    [sidebarWidth, cleanupResize, widthCssVar, widthStorageKey],
  );

  // Mobile swipe to close
  const swipeElementRef = useSwipeToClose({
    onClose,
    enabled: open && isMobile,
    dragHandleRef,
  });

  return {
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
  };
}
