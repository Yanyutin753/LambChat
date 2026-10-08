import {
  type CSSProperties,
  type ReactNode,
  useState,
  useId,
  useLayoutEffect,
  useCallback,
  useEffect,
  useRef,
} from "react";
import { createPortal } from "react-dom";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";

type Placement = "top" | "bottom" | "left" | "right" | "auto";
type ResolvedPlacement = Exclude<Placement, "auto">;

interface TooltipProps {
  content: ReactNode;
  placement?: Placement;
  children: ReactNode;
  /** Extra className for the tooltip bubble */
  className?: string;
  /** z-index for the tooltip (default: 60) */
  zIndex?: number;
  /** Delay before showing on mouse hover (ms). */
  hoverDelay?: number;
  /** Force the bubble visible (e.g. driven by a parent's touch state); hover/long-press still work when not forced */
  open?: boolean;
}

/** Long press duration (ms) before tooltip appears on touch */
const LONG_PRESS_MS = 500;
/** Auto-hide delay (ms) after long press tooltip appears */
const TOUCH_AUTO_HIDE_MS = 2000;
/** Finger travel (px) that counts as a scroll gesture and cancels long press */
const TOUCH_MOVE_CANCEL_PX = 10;
/**
 * Grace period (ms) during which mouseenter is ignored after a touch: touch
 * devices fire a synthetic mouseenter right after tap, which would pop the
 * tooltip on a mere tap instead of a deliberate long press.
 */
const TOUCH_MOUSE_GATE_MS = 600;
/** Gap between trigger and bubble (px) */
const TOOLTIP_GAP = 10;
/** Minimum distance between bubble and viewport edge (px) */
const VIEWPORT_PADDING = 8;
const TOOLTIP_MAX_WIDTH = 240;
/** Arrow is a 10px (border-[5px]) triangle; keep it clear of the rounded corners */
const ARROW_SIZE = 10;
const ARROW_MARGIN = 6;

/** Rough bubble size from content, used to pick a placement before measuring */
function estimateTooltipSize(content: ReactNode) {
  const text =
    typeof content === "string" || typeof content === "number"
      ? String(content)
      : "";
  const estimatedWidth = Math.min(
    TOOLTIP_MAX_WIDTH,
    Math.max(72, text.length * 7 + 20),
  );
  const estimatedLines = Math.max(
    1,
    Math.ceil((text.length * 7 + 20) / TOOLTIP_MAX_WIDTH),
  );

  return {
    width: estimatedWidth,
    height: estimatedLines * 24 + 12,
  };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

function resolvePlacement(
  requested: Placement,
  rect: DOMRect,
  width: number,
  height: number,
): ResolvedPlacement {
  if (requested !== "auto") return requested;

  const spaceLeft = rect.left - VIEWPORT_PADDING;
  const spaceRight = window.innerWidth - rect.right - VIEWPORT_PADDING;
  const spaceAbove = rect.top - VIEWPORT_PADDING;
  const spaceBelow = window.innerHeight - rect.bottom - VIEWPORT_PADDING;
  const horizontalFitsLeft = spaceLeft >= width + TOOLTIP_GAP;
  const horizontalFitsRight = spaceRight >= width + TOOLTIP_GAP;

  // Triggers hugging a viewport edge (e.g. the left rail) read better sideways
  if (rect.left <= VIEWPORT_PADDING + 48 && horizontalFitsRight) return "right";
  if (
    window.innerWidth - rect.right <= VIEWPORT_PADDING + 48 &&
    horizontalFitsLeft
  )
    return "left";
  // Only one side fits horizontally: use it
  if (horizontalFitsRight && !horizontalFitsLeft && spaceRight >= spaceBelow)
    return "right";
  if (horizontalFitsLeft && !horizontalFitsRight && spaceLeft > spaceAbove)
    return "left";

  return spaceAbove >= height + TOOLTIP_GAP && spaceAbove >= spaceBelow
    ? "top"
    : "bottom";
}

function getTooltipPosition(
  rect: DOMRect,
  requested: Placement,
  content: ReactNode,
  measuredSize?: { width: number; height: number },
) {
  const { width, height } = measuredSize ?? estimateTooltipSize(content);
  const resolved = resolvePlacement(requested, rect, width, height);
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;

  if (resolved === "right" || resolved === "left") {
    const idealLeft =
      resolved === "right"
        ? rect.right + TOOLTIP_GAP
        : rect.left - TOOLTIP_GAP - width;
    const idealTop = centerY - height / 2;
    const clampedTop = clamp(
      idealTop,
      VIEWPORT_PADDING,
      viewportHeight - height - VIEWPORT_PADDING,
    );

    return {
      resolved,
      style: {
        position: "fixed",
        left: clamp(
          idealLeft,
          VIEWPORT_PADDING,
          viewportWidth - width - VIEWPORT_PADDING,
        ),
        top: clampedTop,
        transform: "none",
      } satisfies CSSProperties,
      arrowStyle: {
        top: clamp(
          centerY - clampedTop,
          ARROW_MARGIN,
          height - ARROW_MARGIN - ARROW_SIZE,
        ),
      } satisfies CSSProperties,
    };
  }

  const idealLeft = centerX - width / 2;
  const left = clamp(
    idealLeft,
    VIEWPORT_PADDING,
    viewportWidth - width - VIEWPORT_PADDING,
  );
  const idealTop =
    resolved === "top"
      ? rect.top - TOOLTIP_GAP - height
      : rect.bottom + TOOLTIP_GAP;

  return {
    resolved,
    style: {
      position: "fixed",
      left,
      top: clamp(
        idealTop,
        VIEWPORT_PADDING,
        viewportHeight - height - VIEWPORT_PADDING,
      ),
      transform: "none",
    } satisfies CSSProperties,
    arrowStyle: {
      left: clamp(
        centerX - left,
        ARROW_MARGIN,
        width - ARROW_MARGIN - ARROW_SIZE,
      ),
    } satisfies CSSProperties,
  };
}

export function Tooltip({
  content,
  placement = "auto",
  children,
  className,
  zIndex = 60,
  hoverDelay = 0,
  open,
}: TooltipProps) {
  const [show, setShow] = useState(false);
  const tooltipId = useId();
  const bubbleRef = useRef<HTMLSpanElement>(null);
  const [measuredSize, setMeasuredSize] = useState<{
    width: number;
    height: number;
  }>();
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const longPressTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const touchHideTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const lastTouchAtRef = useRef(0);
  const keyboardFocusRef = useRef(false);
  const touchStartPosRef = useRef<{ x: number; y: number } | null>(null);
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const childElRef = useRef<HTMLElement | null>(null);
  const resolvedPlacement = useRef<ResolvedPlacement>("top");
  const arrowStyle = useRef<CSSProperties>({});

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
    clearTimeout(hoverTimer.current);
    // Synthetic mouseenter right after a tap is not a real hover
    if (Date.now() - lastTouchAtRef.current < TOUCH_MOUSE_GATE_MS) return;
    clearTimeout(touchHideTimer.current);
    clearTimeout(longPressTimer.current);
    if (hoverDelay)
      hoverTimer.current = setTimeout(() => setShow(true), hoverDelay);
    else setShow(true);
  }, [hoverDelay]);

  const handleMouseLeave = useCallback(() => {
    clearTimeout(hoverTimer.current);
    hoverTimer.current = setTimeout(() => setShow(false), 150);
  }, []);

  // --- Touch: long press to show ---
  const handleTouchStart = useCallback((e: Event) => {
    const touch = (e as TouchEvent).touches?.[0];
    if (touch)
      touchStartPosRef.current = { x: touch.clientX, y: touch.clientY };
    lastTouchAtRef.current = Date.now();
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

  // Finger travel means the user is scrolling, not long-pressing
  const handleTouchMove = useCallback((e: Event) => {
    const start = touchStartPosRef.current;
    const touch = (e as TouchEvent).touches?.[0];
    if (!start || !touch || !longPressTimer.current) return;
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    if (Math.hypot(dx, dy) > TOUCH_MOVE_CANCEL_PX) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = undefined;
    }
  }, []);

  const handleTouchEnd = useCallback(() => {
    clearTimeout(longPressTimer.current);
  }, []);

  const handleTouchCancel = useCallback(() => {
    clearTimeout(longPressTimer.current);
  }, []);

  const handleActivate = useCallback(() => {
    clearTimeout(hoverTimer.current);
    clearTimeout(longPressTimer.current);
    clearTimeout(touchHideTimer.current);
    setShow(false);
  }, []);

  const handleFocus = useCallback(() => {
    if (keyboardFocusRef.current) setShow(true);
  }, []);
  const handleBlur = useCallback(() => setShow(false), []);
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape" && show) {
        event.preventDefault();
        event.stopPropagation();
        handleActivate();
      }
    },
    [handleActivate, show],
  );

  useEffect(() => {
    const markKeyboard = (event: KeyboardEvent) => {
      if (["Tab", "ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
        keyboardFocusRef.current = true;
    };
    const markPointer = () => {
      keyboardFocusRef.current = false;
    };
    document.addEventListener("keydown", markKeyboard, true);
    document.addEventListener("pointerdown", markPointer, true);
    return () => {
      document.removeEventListener("keydown", markKeyboard, true);
      document.removeEventListener("pointerdown", markPointer, true);
    };
  }, []);

  // Bind events directly to child element (display:contents wrapper can't receive events)
  useEffect(() => {
    const el = getChild();
    if (!el) return;

    el.addEventListener("mouseenter", handleMouseEnter);
    el.addEventListener("mouseleave", handleMouseLeave);
    el.addEventListener("touchstart", handleTouchStart, { passive: true });
    el.addEventListener("touchmove", handleTouchMove, { passive: true });
    el.addEventListener("touchend", handleTouchEnd, { passive: true });
    el.addEventListener("touchcancel", handleTouchCancel, { passive: true });
    el.addEventListener("click", handleActivate);
    el.addEventListener("focusin", handleFocus);
    el.addEventListener("focusout", handleBlur);
    el.addEventListener("keydown", handleKeyDown);

    return () => {
      el.removeEventListener("mouseenter", handleMouseEnter);
      el.removeEventListener("mouseleave", handleMouseLeave);
      el.removeEventListener("touchstart", handleTouchStart);
      el.removeEventListener("touchmove", handleTouchMove);
      el.removeEventListener("touchend", handleTouchEnd);
      el.removeEventListener("touchcancel", handleTouchCancel);
      el.removeEventListener("click", handleActivate);
      el.removeEventListener("focusin", handleFocus);
      el.removeEventListener("focusout", handleBlur);
      el.removeEventListener("keydown", handleKeyDown);
    };
  }, [
    getChild,
    handleMouseEnter,
    handleMouseLeave,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
    handleTouchCancel,
    handleActivate,
    handleFocus,
    handleBlur,
    handleKeyDown,
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

  // Forced-open (touch-driven) shows the bubble on top of the internal hover/long-press state
  const visible = open === true || show;

  useLayoutEffect(() => {
    if (!visible) {
      setMeasuredSize(undefined);
      return;
    }
    const rect = bubbleRef.current?.getBoundingClientRect();
    if (rect?.width && rect.height)
      setMeasuredSize({ width: rect.width, height: rect.height });
  }, [visible, content]);

  useEffect(() => {
    const el = getChild();
    if (!visible || !el) return;
    const previous = el.getAttribute("aria-describedby");
    el.setAttribute(
      "aria-describedby",
      [previous, tooltipId].filter(Boolean).join(" "),
    );
    return () => {
      if (previous === null) el.removeAttribute("aria-describedby");
      else el.setAttribute("aria-describedby", previous);
    };
  }, [visible, getChild, tooltipId]);

  const tipStyle = useStickyDropdownPosition(
    childElRef,
    visible,
    (rect) => {
      const position = getTooltipPosition(
        rect,
        placement,
        content,
        measuredSize,
      );
      resolvedPlacement.current = position.resolved;
      arrowStyle.current = position.arrowStyle;
      return {
        ...position.style,
        zIndex,
      };
    },
    measuredSize,
  );

  const arrowClassName = {
    top: "absolute left-0 top-full border-[5px] border-transparent border-t-stone-700 dark:border-t-stone-900",
    bottom:
      "absolute left-0 bottom-full border-[5px] border-transparent border-b-stone-700 dark:border-b-stone-900",
    left: "absolute right-0 top-0 border-[5px] border-transparent border-l-stone-700 dark:border-l-stone-900",
    right:
      "absolute left-0 top-0 border-[5px] border-transparent border-r-stone-700 dark:border-r-stone-900",
  }[resolvedPlacement.current];

  return (
    <>
      <span ref={wrapperRef} className="contents">
        {children}
      </span>

      {visible &&
        createPortal(
          <span
            ref={bubbleRef}
            id={tooltipId}
            role="tooltip"
            data-placement={resolvedPlacement.current}
            className={`fixed z-50 max-w-[min(240px,calc(100vw-16px))] w-max rounded-md border border-white/10 bg-stone-700/95 px-2.5 py-1.5 text-12 font-medium leading-relaxed text-white shadow-xl shadow-black/20 backdrop-blur-sm whitespace-normal pointer-events-none ${
              className ?? ""
            }`}
            style={{
              ...tipStyle,
              zIndex,
            }}
          >
            {content}
            <span
              data-tooltip-arrow
              className={arrowClassName}
              style={arrowStyle.current}
            />
          </span>,
          document.body,
        )}
    </>
  );
}
