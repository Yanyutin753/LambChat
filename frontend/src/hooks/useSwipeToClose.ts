/**
 * Hook for swipe-to-close gesture on mobile bottom sheets.
 *
 * Supports two swipe zones:
 * 1. Drag handle — always triggers swipe-to-close regardless of scroll position
 * 2. Everywhere else — only triggers when the scroll container is at its top
 */

import { useEffect, useRef, useCallback, type RefObject } from "react";

interface UseSwipeToCloseOptions {
  onClose: () => void;
  enabled?: boolean;
  threshold?: number;
  velocityThreshold?: number;
  dragHandleRef?: RefObject<HTMLElement | null>;
  /** Scrollable body ref — swipe from anywhere works only when scrollTop ≤ 0 */
  scrollContainerRef?: RefObject<HTMLElement | null>;
}

export function useSwipeToClose({
  onClose,
  enabled = true,
  threshold = 100,
  velocityThreshold = 0.5,
  dragHandleRef,
  scrollContainerRef,
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

      const touch = e.touches[0];

      // Check if touch is on the drag handle — always allow
      if (dragHandleRef?.current) {
        const target = e.target;
        if (target instanceof Node && dragHandleRef.current.contains(target)) {
          startY.current = touch.clientY;
          currentY.current = touch.clientY;
          startTime.current = Date.now();
          isDragging.current = true;
          return;
        }
      }

      // For non-drag-handle touches, only allow when scrolled to top
      const scrollEl = scrollContainerRef?.current;
      if (scrollEl && scrollEl.scrollTop > 0) return;

      startY.current = touch.clientY;
      currentY.current = touch.clientY;
      startTime.current = Date.now();
      isDragging.current = true;
    },
    [dragHandleRef, scrollContainerRef],
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
    const deltaTime = Date.now() - startTime.current;
    const velocity = deltaY / deltaTime;

    elementRef.current.style.transition = "transform 0.3s ease-out";

    if (deltaY > threshold || velocity > velocityThreshold) {
      elementRef.current.style.transform = `translateY(100%)`;
      closeTimerRef.current = setTimeout(() => {
        closeTimerRef.current = null;
        onCloseRef.current();
      }, 300);
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

    element.addEventListener("touchstart", handleTouchStart, { passive: true });
    element.addEventListener("touchmove", handleTouchMove, { passive: false }); // passive: false to allow preventDefault
    element.addEventListener("touchend", handleTouchEnd, { passive: true });

    return () => {
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
