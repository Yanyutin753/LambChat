import {
  type ReactNode,
  useState,
  useCallback,
  useEffect,
  useRef,
} from "react";
import { createPortal } from "react-dom";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";

type Placement = "top" | "bottom" | "auto";

interface TooltipProps {
  content: ReactNode;
  placement?: Placement;
  children: ReactNode;
  /** Extra className for the tooltip bubble */
  className?: string;
  /** z-index for the tooltip (default: 60) */
  zIndex?: number;
}

/** Long press duration (ms) before tooltip appears on touch */
const LONG_PRESS_MS = 500;
/** Auto-hide delay (ms) after long press tooltip appears */
const TOUCH_AUTO_HIDE_MS = 2000;

export function Tooltip({
  content,
  placement = "auto",
  children,
  className,
  zIndex = 60,
}: TooltipProps) {
  const [show, setShow] = useState(false);
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const longPressTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const touchHideTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const childElRef = useRef<HTMLElement | null>(null);
  const resolvedPlacement = useRef<"top" | "bottom">("top");

  // Get the actual child element (not the display:contents wrapper)
  const getChild = useCallback(
    () => wrapperRef.current?.firstElementChild as HTMLElement | null,
    [],
  );

  // Sync childElRef for the positioning hook
  useEffect(() => {
    childElRef.current = getChild();
  }, [getChild, show]);

  // --- Desktop: hover show/hide ---
  const handleMouseEnter = useCallback(() => {
    clearTimeout(touchHideTimer.current);
    clearTimeout(longPressTimer.current);
    setShow(true);
  }, []);

  const handleMouseLeave = useCallback(() => {
    hoverTimer.current = setTimeout(() => setShow(false), 150);
  }, []);

  // --- Touch: long press to show ---
  const handleTouchStart = useCallback(() => {
    clearTimeout(hoverTimer.current);
    clearTimeout(touchHideTimer.current);
    longPressTimer.current = setTimeout(() => {
      setShow(true);
      touchHideTimer.current = setTimeout(
        () => setShow(false),
        TOUCH_AUTO_HIDE_MS,
      );
    }, LONG_PRESS_MS);
  }, []);

  const handleTouchEnd = useCallback(() => {
    clearTimeout(longPressTimer.current);
  }, []);

  const handleTouchCancel = useCallback(() => {
    clearTimeout(longPressTimer.current);
  }, []);

  // Bind events directly to child element (display:contents wrapper can't receive events)
  useEffect(() => {
    const el = getChild();
    if (!el) return;

    el.addEventListener("mouseenter", handleMouseEnter);
    el.addEventListener("mouseleave", handleMouseLeave);
    el.addEventListener("touchstart", handleTouchStart, { passive: true });
    el.addEventListener("touchend", handleTouchEnd, { passive: true });
    el.addEventListener("touchcancel", handleTouchCancel, { passive: true });

    return () => {
      el.removeEventListener("mouseenter", handleMouseEnter);
      el.removeEventListener("mouseleave", handleMouseLeave);
      el.removeEventListener("touchstart", handleTouchStart);
      el.removeEventListener("touchend", handleTouchEnd);
      el.removeEventListener("touchcancel", handleTouchCancel);
    };
  }, [
    getChild,
    handleMouseEnter,
    handleMouseLeave,
    handleTouchStart,
    handleTouchEnd,
    handleTouchCancel,
  ]);

  // Close on outside click
  useEffect(() => {
    if (!show) return;
    const handleClick = (e: MouseEvent) => {
      const el = getChild();
      if (el && !el.contains(e.target as Node)) {
        setShow(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [show, getChild]);

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      clearTimeout(hoverTimer.current);
      clearTimeout(longPressTimer.current);
      clearTimeout(touchHideTimer.current);
    };
  }, []);

  const tipStyle = useStickyDropdownPosition(childElRef, show, (rect) => {
    const textLen =
      typeof content === "string"
        ? content.length
        : content?.toString().length ?? 0;
    const estimatedHeight = Math.min(textLen * 0.6, 120) + 24;
    const spaceAbove = rect.top;
    const spaceBelow = window.innerHeight - rect.bottom;

    let showAbove = spaceAbove > estimatedHeight + 8;
    if (placement === "top") showAbove = true;
    else if (placement === "bottom") showAbove = false;
    else showAbove = spaceAbove > spaceBelow;

    resolvedPlacement.current = showAbove ? "top" : "bottom";

    return {
      position: "fixed",
      left: rect.left + rect.width / 2,
      top: showAbove ? rect.top - 8 : rect.bottom + 8,
      transform: showAbove ? "translate(-50%, -100%)" : "translate(-50%, 0)",
      zIndex,
    };
  });

  if (typeof content !== "string" && typeof content !== "number") return null;

  const arrowTop = resolvedPlacement.current === "top";

  return (
    <>
      <span ref={wrapperRef} className="contents">
        {children}
      </span>

      {show &&
        createPortal(
          <span
            className={`fixed max-w-[240px] w-max rounded-lg bg-stone-700 dark:bg-stone-900 px-2.5 py-1.5 text-xs leading-relaxed text-white shadow-lg whitespace-normal pointer-events-none ${
              className ?? ""
            }`}
            style={{
              ...tipStyle,
              zIndex,
            }}
          >
            {content}
            {arrowTop ? (
              <span className="absolute left-1/2 -translate-x-1/2 top-full border-[5px] border-transparent border-t-stone-700 dark:border-t-stone-900" />
            ) : (
              <span className="absolute left-1/2 -translate-x-1/2 bottom-full border-[5px] border-transparent border-b-stone-700 dark:border-b-stone-900" />
            )}
          </span>,
          document.body,
        )}
    </>
  );
}
