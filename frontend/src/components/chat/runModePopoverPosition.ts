import type { CSSProperties } from "react";

interface RunModePopoverPositionOptions {
  triggerRect: DOMRect;
  viewportWidth: number;
  viewportHeight: number;
}

export function getRunModePopoverPosition({
  triggerRect,
  viewportWidth,
  viewportHeight,
}: RunModePopoverPositionOptions): CSSProperties {
  const isMobile = viewportWidth < 640;
  const edgeInset = 16;
  const gap = 8;
  const width = isMobile
    ? Math.min(280, Math.max(0, viewportWidth - edgeInset * 2))
    : 320;
  const left = isMobile
    ? Math.max(edgeInset, (viewportWidth - width) / 2)
    : Math.max(
        edgeInset,
        Math.min(
          triggerRect.left + triggerRect.width / 2 - width / 2,
          viewportWidth - width - edgeInset,
        ),
      );
  const availableAbove = triggerRect.top - edgeInset - gap;

  if (isMobile && availableAbove < 240) {
    return {
      position: "fixed",
      zIndex: 9999,
      width,
      left,
      top: edgeInset,
      maxHeight: viewportHeight - edgeInset * 2,
    };
  }

  return {
    position: "fixed",
    zIndex: 9999,
    width,
    left,
    bottom: viewportHeight - triggerRect.top + gap,
    maxHeight: Math.max(160, availableAbove),
  };
}
