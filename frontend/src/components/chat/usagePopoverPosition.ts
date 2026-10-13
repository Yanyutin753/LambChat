import type { CSSProperties } from "react";

interface UsagePopoverPositionOptions {
  triggerRect: DOMRect;
  viewportWidth: number;
  viewportHeight: number;
}

export function getUsagePopoverPosition({
  triggerRect,
  viewportWidth,
  viewportHeight,
}: UsagePopoverPositionOptions): CSSProperties {
  const isMobile = viewportWidth < 640;
  const edgeInset = 16;
  const gap = 8;
  const width = isMobile
    ? Math.min(300, Math.max(0, viewportWidth - edgeInset * 2))
    : 304;
  const left = isMobile
    ? Math.max(edgeInset, (viewportWidth - width) / 2)
    : Math.max(
        edgeInset,
        Math.min(
          triggerRect.left + triggerRect.width / 2 - width / 2,
          viewportWidth - width - edgeInset,
        ),
      );
  const top = triggerRect.bottom + gap;

  return {
    position: "fixed",
    zIndex: 9999,
    width,
    left,
    top,
    maxHeight: Math.max(0, viewportHeight - top - edgeInset),
  };
}
