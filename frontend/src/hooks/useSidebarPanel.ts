import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type MutableRefObject,
  type RefObject,
} from "react";

import type { RightPanelKind } from "../components/common/rightPanelCoordinator";
import {
  clampPanelWidthPct,
  getRightPanelPresentation,
  resizePanelWidthPct,
  sanitizePanelWidthPct,
  type RightPanelPresentation,
} from "./rightPanelLayout";
import { notifyRightPanelWidthChanged } from "./rightPanelWidthEvents";

export interface SidebarPanelOptions {
  open: boolean;
  onClose: () => void;
  kind?: RightPanelKind;
  /** localStorage key for persisting sidebar width */
  widthStorageKey: string;
  /** CSS variable name for sidebar width */
  widthCssVar: string;
  /** Default width percentage */
  defaultWidthPct?: number;
  /** Minimum usable panel width in pixels */
  minPanelPx?: number;
  /** Minimum workspace width preserved beside a docked panel */
  minMainPx?: number;
  /** data-attribute name set on <html> while this docked panel is active */
  dataAttr?: string;
  /** Explicit presentation for center/native-fullscreen content modes */
  presentationOverride?: "overlay" | "fullscreen";
}

export interface ResizeSeparatorProps {
  role: "separator";
  tabIndex: number;
  "aria-orientation": "vertical";
  "aria-valuemin": number;
  "aria-valuemax": number;
  "aria-valuenow": number;
  onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => void;
  onDoubleClick: () => void;
}

export interface SidebarPanelReturn {
  isMobile: boolean;
  presentation: RightPanelPresentation;
  animateIn: boolean;
  sidebarWidth: number;
  panelRef: RefObject<HTMLDivElement | null>;
  indicatorRef: RefObject<HTMLDivElement | null>;
  dragHandleRef: RefObject<HTMLDivElement | null>;
  swipeElementRef: RefObject<HTMLElement | null>;
  isResizing: MutableRefObject<boolean>;
  justResized: MutableRefObject<boolean>;
  handleResizeStart: (event: ReactMouseEvent) => void;
  resizeSeparatorProps: ResizeSeparatorProps;
  resetSidebarWidth: () => void;
}

const _compressCounts = new Map<string, number>();
let _modalCount = 0;
let _previousBodyOverflow = "";
let _previousBodyPaddingRight = "";

function getWidthBounds({
  viewportWidth,
  minPanelPx,
  minMainPx,
}: {
  viewportWidth: number;
  minPanelPx: number;
  minMainPx: number;
}): { minimum: number; maximum: number } {
  const safeViewportWidth = Math.max(viewportWidth, 1);
  const minimum = Math.min(
    100,
    Math.ceil((minPanelPx / safeViewportWidth) * 100),
  );
  const requestedMaximum = Math.floor(
    ((safeViewportWidth - minMainPx) / safeViewportWidth) * 100,
  );
  return {
    minimum,
    maximum: Math.max(minimum, Math.min(100, requestedMaximum)),
  };
}

export function useSidebarPanel({
  open,
  onClose,
  kind,
  widthStorageKey,
  widthCssVar,
  defaultWidthPct = 35,
  minPanelPx = 320,
  minMainPx = 560,
  dataAttr = "data-sidebar-preview",
  presentationOverride,
}: SidebarPanelOptions): SidebarPanelReturn {
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const preferredWidthRef = useRef(
    sanitizePanelWidthPct(
      localStorage.getItem(widthStorageKey),
      defaultWidthPct,
    ),
  );
  const [sidebarWidth, setSidebarWidth] = useState(() =>
    clampPanelWidthPct({
      requestedPct: preferredWidthRef.current,
      viewportWidth: window.innerWidth,
      minPanelPx,
      minMainPx,
    }),
  );
  const [animateIn, setAnimateIn] = useState(false);

  const responsivePresentation = getRightPanelPresentation(viewportWidth);
  const presentation =
    responsivePresentation === "fullscreen"
      ? "fullscreen"
      : presentationOverride ?? responsivePresentation;
  const isMobile = presentation === "fullscreen";
  const panelKind: RightPanelKind =
    kind ?? (dataAttr === "data-editor-sidebar" ? "editor" : "content");

  const panelRef = useRef<HTMLDivElement>(null);
  const indicatorRef = useRef<HTMLDivElement>(null);
  const dragHandleRef = useRef<HTMLDivElement>(null);
  const swipeElementRef = useRef<HTMLElement>(null);
  const isResizing = useRef(false);
  const justResized = useRef(false);
  const resizeCaptureRef = useRef<HTMLDivElement | null>(null);
  const resizeListenersRef = useRef<{
    move: (event: MouseEvent) => void;
    up: (event: MouseEvent) => void;
  } | null>(null);
  const justResizedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );

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

  useEffect(() => {
    const handleViewportResize = () => {
      const nextViewportWidth = window.innerWidth;
      setViewportWidth(nextViewportWidth);
      setSidebarWidth(
        clampPanelWidthPct({
          requestedPct: preferredWidthRef.current,
          viewportWidth: nextViewportWidth,
          minPanelPx,
          minMainPx,
        }),
      );
    };

    window.addEventListener("resize", handleViewportResize);
    return () => window.removeEventListener("resize", handleViewportResize);
  }, [minMainPx, minPanelPx]);

  useEffect(() => {
    if (!open) return;

    setAnimateIn(false);
    let cancelled = false;
    const firstFrame = requestAnimationFrame(() => {
      const secondFrame = requestAnimationFrame(() => {
        if (!cancelled) setAnimateIn(true);
      });
      if (cancelled) cancelAnimationFrame(secondFrame);
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(firstFrame);
    };
  }, [open, presentation]);

  useLayoutEffect(() => {
    document.documentElement.style.setProperty(widthCssVar, `${sidebarWidth}%`);
    notifyRightPanelWidthChanged(
      open
        ? {
            open: true,
            kind: panelKind,
            presentation,
            widthPct: sidebarWidth,
            widthPx:
              presentation === "fullscreen"
                ? viewportWidth
                : Math.round((viewportWidth * sidebarWidth) / 100),
            viewportWidth,
          }
        : null,
    );
  }, [open, panelKind, presentation, sidebarWidth, viewportWidth, widthCssVar]);

  useLayoutEffect(() => {
    if (!open) return;

    if (presentation === "docked") {
      const previous = _compressCounts.get(dataAttr) ?? 0;
      _compressCounts.set(dataAttr, previous + 1);
      if (previous === 0) {
        document.documentElement.setAttribute(dataAttr, "open");
      }

      return () => {
        const current = _compressCounts.get(dataAttr) ?? 1;
        if (current <= 1) {
          _compressCounts.delete(dataAttr);
          document.documentElement.removeAttribute(dataAttr);
        } else {
          _compressCounts.set(dataAttr, current - 1);
        }
      };
    }

    if (_modalCount === 0) {
      _previousBodyOverflow = document.body.style.overflow;
      _previousBodyPaddingRight = document.body.style.paddingRight;
      const scrollbarWidth = Math.max(
        0,
        window.innerWidth - document.documentElement.clientWidth,
      );
      document.body.style.overflow = "hidden";
      if (scrollbarWidth > 0) {
        document.body.style.paddingRight = `${scrollbarWidth}px`;
      }
    }
    _modalCount += 1;

    return () => {
      _modalCount = Math.max(0, _modalCount - 1);
      if (_modalCount === 0) {
        document.body.style.overflow = _previousBodyOverflow;
        document.body.style.paddingRight = _previousBodyPaddingRight;
      }
    };
  }, [open, presentation, dataAttr]);

  useEffect(() => {
    if (!open) return;

    const handleEscape = (event: KeyboardEvent) => {
      if (document.fullscreenElement) return;
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [open, onClose]);

  useEffect(() => {
    if (presentation === "docked") return;
    cleanupResize(indicatorRef.current);
  }, [cleanupResize, presentation]);

  useEffect(() => {
    const indicator = indicatorRef.current;
    return () => {
      cleanupResize(indicator);
      if (justResizedTimerRef.current) {
        clearTimeout(justResizedTimerRef.current);
      }
    };
  }, [cleanupResize]);

  const persistWidth = useCallback(
    (requestedPct: number) => {
      preferredWidthRef.current = requestedPct;
      const nextWidth = clampPanelWidthPct({
        requestedPct,
        viewportWidth,
        minPanelPx,
        minMainPx,
      });
      setSidebarWidth(nextWidth);
      localStorage.setItem(widthStorageKey, String(nextWidth));
    },
    [minMainPx, minPanelPx, viewportWidth, widthStorageKey],
  );

  const markJustResized = useCallback(() => {
    justResized.current = true;
    if (justResizedTimerRef.current) {
      clearTimeout(justResizedTimerRef.current);
    }
    justResizedTimerRef.current = setTimeout(() => {
      justResized.current = false;
      justResizedTimerRef.current = null;
    }, 100);
  }, []);

  const handleResizeStart = useCallback(
    (event: ReactMouseEvent) => {
      if (presentation !== "docked") return;

      event.preventDefault();
      event.stopPropagation();
      isResizing.current = true;
      const startX = event.clientX;
      const startWidth = sidebarWidth;
      const indicator = indicatorRef.current;

      const capture = document.createElement("div");
      capture.style.cssText =
        "position:fixed;inset:0;z-index:999999;cursor:col-resize;";
      document.body.appendChild(capture);
      resizeCaptureRef.current = capture;

      const onMove = (moveEvent: MouseEvent) => {
        if (!isResizing.current) return;
        if (indicator) {
          indicator.style.left = `${moveEvent.clientX}px`;
          indicator.style.display = "block";
        }
      };
      const onUp = (upEvent: MouseEvent) => {
        if (!isResizing.current) return;
        cleanupResize(indicator);
        const delta = ((startX - upEvent.clientX) / viewportWidth) * 100;
        persistWidth(startWidth + delta);
        markJustResized();
      };
      resizeListenersRef.current = { move: onMove, up: onUp };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [
      cleanupResize,
      markJustResized,
      persistWidth,
      presentation,
      sidebarWidth,
      viewportWidth,
    ],
  );

  const resetSidebarWidth = useCallback(() => {
    persistWidth(defaultWidthPct);
    markJustResized();
  }, [defaultWidthPct, markJustResized, persistWidth]);

  const handleResizeKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLElement>) => {
      const nextWidth = resizePanelWidthPct({
        currentPct: sidebarWidth,
        viewportWidth,
        minPanelPx,
        minMainPx,
        defaultPct: defaultWidthPct,
        key: event.key,
        shiftKey: event.shiftKey,
      });
      if (nextWidth === null) return;

      event.preventDefault();
      persistWidth(nextWidth);
      markJustResized();
    },
    [
      defaultWidthPct,
      markJustResized,
      minMainPx,
      minPanelPx,
      persistWidth,
      sidebarWidth,
      viewportWidth,
    ],
  );

  const { minimum, maximum } = getWidthBounds({
    viewportWidth,
    minPanelPx,
    minMainPx,
  });

  return {
    isMobile,
    presentation,
    animateIn,
    sidebarWidth,
    panelRef,
    indicatorRef,
    dragHandleRef,
    swipeElementRef,
    isResizing,
    justResized,
    handleResizeStart,
    resizeSeparatorProps: {
      role: "separator",
      tabIndex: 0,
      "aria-orientation": "vertical",
      "aria-valuemin": minimum,
      "aria-valuemax": maximum,
      "aria-valuenow": sidebarWidth,
      onKeyDown: handleResizeKeyDown,
      onDoubleClick: resetSidebarWidth,
    },
    resetSidebarWidth,
  };
}
