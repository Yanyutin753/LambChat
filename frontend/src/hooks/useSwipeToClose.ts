/**
 * Hook for swipe-to-close gesture on mobile bottom sheets.
 *
 * Only triggers from the drag handle — swiping on content area never closes the panel.
 */

import { useEffect, useRef, useCallback, type RefObject } from "react";

interface UseSwipeToCloseOptions {
  onClose: () => void;
  enabled?: boolean;
  threshold?: number;
  velocityThreshold?: number;
  dragHandleRef?: RefObject<HTMLElement | null>;
}

export function useSwipeToClose({
  onClose,
  enabled = true,
  threshold = 100,
  velocityThreshold = 0.5,
  dragHandleRef,
}: UseSwipeToCloseOptions) {
  const startY = useRef<number>(0);
  const currentY = useRef<number>(0);
  const startTime = useRef<number>(0);
  const isDragging = useRef<boolean>(false);
  const elementRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleTouchStart = useCallback(
    (e: TouchEvent) => {
      if (!elementRef.current) return;

      if (!dragHandleRef?.current) return;

      const target = e.target;
      if (!(target instanceof Node && dragHandleRef.current.contains(target)))
        return;

      if (e.touches.length !== 1) return;
      const touch = e.touches[0];
      startY.current = touch.clientY;
      currentY.current = touch.clientY;
      startTime.current = Date.now();
      isDragging.current = true;
    },
    [dragHandleRef],
  );

  const handleTouchMove = useCallback((e: TouchEvent) => {
    if (!isDragging.current || !elementRef.current) return;

    const touch = e.touches[0];
    currentY.current = touch.clientY;
    const deltaY = currentY.current - startY.current;

    if (deltaY > 0) {
      e.preventDefault();
      elementRef.current.style.transform = `translateY(${deltaY}px)`;
      elementRef.current.style.transition = "none";
    }
  }, []);

  const handleTouchEnd = useCallback(() => {
    if (!isDragging.current || !elementRef.current) return;

    const deltaY = currentY.current - startY.current;
    const deltaTime = Math.max(1, Date.now() - startTime.current);
    const velocity = deltaY / deltaTime;

    const duration = window.matchMedia?.("(prefers-reduced-motion: reduce)")
      .matches
      ? 0
      : 300;
    elementRef.current.style.transition = `transform ${duration}ms ease-out`;

    if (deltaY > threshold || (deltaY > 20 && velocity > velocityThreshold)) {
      elementRef.current.style.transform = `translateY(100%)`;
      closeTimerRef.current = setTimeout(() => {
        closeTimerRef.current = null;
        onCloseRef.current();
      }, duration);
    } else {
      elementRef.current.style.transform = "translateY(0)";
    }

    isDragging.current = false;
  }, [threshold, velocityThreshold]);

  // Attach/detach listeners
  useEffect(() => {
    if (!enabled) return;

    const element = elementRef.current;
    if (!element) return;

    const cancel = () => {
      isDragging.current = false;
      element.style.transform = "";
      element.style.transition = "";
    };
    const pointerStart = (event: PointerEvent) => {
      if (event.pointerType !== "mouse" || event.button !== 0) return;
      handleTouchStart({
        target: event.target,
        touches: [event],
      } as unknown as TouchEvent);
      if (isDragging.current) element.setPointerCapture?.(event.pointerId);
    };
    const pointerMove = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return;
      handleTouchMove({
        touches: [event],
        preventDefault: () => event.preventDefault(),
      } as unknown as TouchEvent);
    };
    const pointerEnd = (event: PointerEvent) => {
      if (event.pointerType === "mouse") handleTouchEnd();
    };
    element.addEventListener("pointerdown", pointerStart);
    element.addEventListener("pointermove", pointerMove);
    element.addEventListener("pointerup", pointerEnd);
    element.addEventListener("pointercancel", cancel);
    element.addEventListener("touchcancel", cancel);
    element.addEventListener("touchstart", handleTouchStart, { passive: true });
    element.addEventListener("touchmove", handleTouchMove, { passive: false }); // passive: false to allow preventDefault
    element.addEventListener("touchend", handleTouchEnd, { passive: true });

    return () => {
      element.removeEventListener("pointerdown", pointerStart);
      element.removeEventListener("pointermove", pointerMove);
      element.removeEventListener("pointerup", pointerEnd);
      element.removeEventListener("pointercancel", cancel);
      element.removeEventListener("touchcancel", cancel);
      cancel();
      element.removeEventListener("touchstart", handleTouchStart);
      element.removeEventListener("touchmove", handleTouchMove);
      element.removeEventListener("touchend", handleTouchEnd);
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
      }
    };
  }, [enabled, handleTouchStart, handleTouchMove, handleTouchEnd]);

  return elementRef;
}
