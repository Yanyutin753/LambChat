const DEFAULT_TEXTAREA_MAX_HEIGHT_PX = 150;
const MOBILE_TEXTAREA_VIEWPORT_RATIO = 0.22;
const MOBILE_TEXTAREA_MIN_HEIGHT_PX = 120;
const DEFAULT_MENTION_POPUP_MAX_HEIGHT_PX = 220;
const MIN_MENTION_POPUP_MAX_HEIGHT_PX = 160;
const MENTION_POPUP_VIEWPORT_GAP_PX = 46;
const MENTION_POPUP_INPUT_GAP_PX = 6;

/** Show the expand control only after content grows past this many visual lines. */
export const COMPOSER_EXPAND_MIN_LINES = 3;

interface TextareaLike {
  style: {
    height: string;
  };
  scrollHeight: number;
  scrollTop: number;
  clientHeight: number;
  value?: string;
  selectionEnd?: number;
}

export function resizeTextareaForContent(
  textarea: TextareaLike,
  maxHeightPx = DEFAULT_TEXTAREA_MAX_HEIGHT_PX,
): void {
  const prevScrollTop = textarea.scrollTop;
  const wasAtBottom =
    prevScrollTop + textarea.clientHeight >= textarea.scrollHeight - 1;
  const valueLength = textarea.value?.length ?? 0;
  const caretAtEnd =
    typeof textarea.selectionEnd === "number" &&
    textarea.selectionEnd >= valueLength;

  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeightPx)}px`;
  // 追加输入（视口原本在底部，或光标在末尾）时滚到底，保证最新内容可见；
  // 编辑中间内容时保持原滚动位置，避免视口被强制拉到末尾。
  textarea.scrollTop =
    wasAtBottom || caretAtEnd ? textarea.scrollHeight : prevScrollTop;
}

export function getComposerContentLineCount({
  scrollHeight,
  lineHeight,
  verticalPadding = 0,
}: {
  scrollHeight: number;
  lineHeight: number;
  verticalPadding?: number;
}): number {
  if (lineHeight <= 0) return 1;
  const contentHeight = Math.max(0, scrollHeight - verticalPadding);
  return Math.max(1, Math.ceil(contentHeight / lineHeight));
}

export function shouldShowComposerExpandButton(
  lineCount: number,
  minLines: number = COMPOSER_EXPAND_MIN_LINES,
): boolean {
  return lineCount > minLines;
}

export function measureComposerExpandVisibility(
  textarea: {
    scrollHeight: number;
  } | null,
  metrics?: {
    lineHeight?: number;
    verticalPadding?: number;
    minLines?: number;
  },
): boolean {
  if (!textarea) return false;
  const lineHeight =
    metrics?.lineHeight && metrics.lineHeight > 0 ? metrics.lineHeight : 24;
  const verticalPadding = metrics?.verticalPadding ?? 0;
  const lineCount = getComposerContentLineCount({
    scrollHeight: textarea.scrollHeight,
    lineHeight,
    verticalPadding,
  });
  return shouldShowComposerExpandButton(lineCount, metrics?.minLines);
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

export function getMentionPopupMaxHeightPx({
  inputTop,
  viewportHeight,
}: {
  inputTop?: number | null;
  viewportHeight?: number | null;
}): number {
  if (!inputTop || !viewportHeight) {
    return DEFAULT_MENTION_POPUP_MAX_HEIGHT_PX;
  }

  const availableHeight = Math.round(inputTop - MENTION_POPUP_VIEWPORT_GAP_PX);
  return Math.min(
    DEFAULT_MENTION_POPUP_MAX_HEIGHT_PX,
    Math.max(MIN_MENTION_POPUP_MAX_HEIGHT_PX, availableHeight),
  );
}

export function getMentionPopupFixedPlacement({
  inputRect,
  viewportHeight,
}: {
  inputRect?: Pick<DOMRect, "left" | "top" | "width"> | null;
  viewportHeight?: number | null;
}): {
  left: number;
  width: number;
  bottom: number;
  maxHeight: number;
} | null {
  if (!inputRect || !viewportHeight) {
    return null;
  }

  return {
    left: Math.round(inputRect.left),
    width: Math.round(inputRect.width),
    bottom: Math.round(
      viewportHeight - inputRect.top + MENTION_POPUP_INPUT_GAP_PX,
    ),
    maxHeight: getMentionPopupMaxHeightPx({
      inputTop: inputRect.top,
      viewportHeight,
    }),
  };
}
