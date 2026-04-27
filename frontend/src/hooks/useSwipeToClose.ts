/**
 * Hook for swipe-to-close gesture on mobile bottom sheets
 */

import { useEffect, useRef, useCallback, type RefObject } from "react";

interface UseSwipeToCloseOptions {
  onClose: () => void;
  enabled?: boolean;
  threshold?: number; // Distance in pixels to trigger close
  velocityThreshold?: number; // Velocity to trigger close
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

      if (dragHandleRef?.current) {
        const target = e.target;
        if (
          !(target instanceof Node) ||
          !dragHandleRef.current.contains(target)
        ) {
          return;
        }
      } else {
        const touch = e.touches[0];
        const rect = elementRef.current.getBoundingClientRect();
        const relativeY = touch.clientY - rect.top;

        // Only handle if touch starts near the top (first 60px for drag handle area)
        if (relativeY > 60) return;
      }

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

    // Only allow downward swipes
    if (deltaY > 0) {
      // Prevent default to avoid scrolling while dragging
      e.preventDefault();
      // Apply transform to follow finger
      elementRef.current.style.transform = `translateY(${deltaY}px)`;
      elementRef.current.style.transition = "none";
    }
  }, []);

  const handleTouchEnd = useCallback(() => {
    if (!isDragging.current || !elementRef.current) return;

    const deltaY = currentY.current - startY.current;
    const deltaTime = Date.now() - startTime.current;
    const velocity = deltaY / deltaTime;

    // Reset transform
    elementRef.current.style.transition = "transform 0.3s ease-out";

    // Check if should close based on distance or velocity
    if (deltaY > threshold || velocity > velocityThreshold) {
      // Animate out and close
      elementRef.current.style.transform = `translateY(100%)`;
      closeTimerRef.current = setTimeout(() => {
        closeTimerRef.current = null;
        onCloseRef.current();
      }, 300);
    } else {
      // Snap back
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
