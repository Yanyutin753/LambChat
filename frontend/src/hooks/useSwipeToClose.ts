/**
 * Hook for swipe-to-close gesture on mobile bottom sheets
 */

import { useEffect, useRef, useCallback } from "react";

interface UseSwipeToCloseOptions {
  onClose: () => void;
  enabled?: boolean;
  threshold?: number; // Distance in pixels to trigger close
  velocityThreshold?: number; // Velocity to trigger close
}

export function useSwipeToClose({
  onClose,
  enabled = true,
  threshold = 100,
  velocityThreshold = 0.5,
}: UseSwipeToCloseOptions) {
  const startY = useRef<number>(0);
  const currentY = useRef<number>(0);
  const startTime = useRef<number>(0);
  const isDragging = useRef<boolean>(false);
  const elementRef = useRef<HTMLElement | null>(null);

  const handleTouchStart = useCallback((e: TouchEvent) => {
    if (!elementRef.current) return;

    const touch = e.touches[0];
    const rect = elementRef.current.getBoundingClientRect();
    const relativeY = touch.clientY - rect.top;

    // Only handle if touch starts near the top (first 60px for drag handle area)
    if (relativeY > 60) return;

    startY.current = touch.clientY;
    currentY.current = touch.clientY;
    startTime.current = Date.now();
    isDragging.current = true;
  }, []);

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
      setTimeout(() => {
        onClose();
      }, 300);
    } else {
      // Snap back
      elementRef.current.style.transform = "translateY(0)";
    }

    isDragging.current = false;
  }, [onClose, threshold, velocityThreshold]);

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
    };
  }, [enabled, handleTouchStart, handleTouchMove, handleTouchEnd]);

  return elementRef;
}
