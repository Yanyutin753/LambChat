const DEFAULT_TEXTAREA_MAX_HEIGHT_PX = 250;
const MOBILE_TEXTAREA_VIEWPORT_RATIO = 0.32;
const MOBILE_TEXTAREA_MIN_HEIGHT_PX = 120;

interface TextareaLike {
  style: {
    height: string;
  };
  scrollHeight: number;
  scrollTop: number;
}

export function resizeTextareaForContent(
  textarea: TextareaLike,
  maxHeightPx = DEFAULT_TEXTAREA_MAX_HEIGHT_PX,
): void {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeightPx)}px`;
  textarea.scrollTop = textarea.scrollHeight;
}

export function getTextareaMaxHeightPx({
  isMobile,
  viewportHeight,
}: {
  isMobile: boolean;
  viewportHeight?: number | null;
}): number {
  if (!isMobile || !viewportHeight) {
    return DEFAULT_TEXTAREA_MAX_HEIGHT_PX;
  }

  return Math.min(
    DEFAULT_TEXTAREA_MAX_HEIGHT_PX,
    Math.max(
      MOBILE_TEXTAREA_MIN_HEIGHT_PX,
      Math.round(viewportHeight * MOBILE_TEXTAREA_VIEWPORT_RATIO),
    ),
  );
}
