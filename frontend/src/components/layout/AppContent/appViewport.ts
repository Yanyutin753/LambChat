/**
 * When no virtual keyboard is open, return null so the CSS fallback `100dvh`
 * is used — this ensures full-screen coverage on iOS PWA standalone mode where
 * `visualViewport.height` can be smaller than the actual screen.
 *
 * When the keyboard IS open (visual viewport significantly smaller than window),
 * return the measured height so the app shrinks to stay above the keyboard.
 */
const KEYBOARD_THRESHOLD_PX = 100;
const VIEWPORT_JITTER_THRESHOLD_PX = 2;

export interface AppViewportState {
  heightCssValue: string | null;
  offsetTopCssValue: string | null;
  keyboardInsetCssValue: string | null;
  keyboardOpen: boolean;
}

export function shouldPreferVisibleViewportHeight({
  isMobileDevice,
  isStandaloneDisplayMode,
  hasVisualViewport,
}: {
  isMobileDevice: boolean;
  isStandaloneDisplayMode: boolean;
  hasVisualViewport: boolean;
}): boolean {
  return isMobileDevice && hasVisualViewport && !isStandaloneDisplayMode;
}

export function isKeyboardViewport({
  visualViewportHeight,
  windowInnerHeight,
}: {
  visualViewportHeight?: number | null;
  windowInnerHeight?: number | null;
}): boolean {
  const vvHeight = visualViewportHeight ?? null;
  const wHeight = windowInnerHeight ?? null;

  return !!vvHeight && !!wHeight && wHeight - vvHeight > KEYBOARD_THRESHOLD_PX;
}

export function getAppViewportHeightCssValue({
  visualViewportHeight,
  windowInnerHeight,
  preferVisibleViewportHeight = false,
}: {
  visualViewportHeight?: number | null;
  windowInnerHeight?: number | null;
  preferVisibleViewportHeight?: boolean;
}): string | null {
  const vvHeight = visualViewportHeight ?? null;
  const wHeight = windowInnerHeight ?? null;

  if (!vvHeight || !wHeight || vvHeight <= 0 || wHeight <= 0) {
    return null;
  }

  // Keyboard likely open — use measured visual viewport height
  if (
    isKeyboardViewport({
      visualViewportHeight: vvHeight,
      windowInnerHeight: wHeight,
    })
  ) {
    return `${Math.round(vvHeight)}px`;
  }

  if (
    preferVisibleViewportHeight &&
    vvHeight < wHeight - VIEWPORT_JITTER_THRESHOLD_PX
  ) {
    return `${Math.round(vvHeight)}px`;
  }

  // No keyboard — let CSS 100dvh handle full-screen height
  return null;
}

export function getAppViewportState({
  visualViewportHeight,
  visualViewportOffsetTop,
  windowInnerHeight,
  editableFocused,
  layoutViewportResized = false,
  preferVisibleViewportHeight = false,
}: {
  visualViewportHeight?: number | null;
  visualViewportOffsetTop?: number | null;
  windowInnerHeight?: number | null;
  editableFocused: boolean;
  layoutViewportResized?: boolean;
  preferVisibleViewportHeight?: boolean;
}): AppViewportState {
  const vvHeight = visualViewportHeight ?? null;
  const offsetTop = visualViewportOffsetTop ?? 0;
  const wHeight = windowInnerHeight ?? null;
  const keyboardOpen =
    editableFocused &&
    (layoutViewportResized ||
      isKeyboardViewport({
        visualViewportHeight: vvHeight,
        windowInnerHeight: wHeight,
      }));

  if (!keyboardOpen || !vvHeight || !wHeight) {
    const visibleViewportHeightCssValue = getAppViewportHeightCssValue({
      visualViewportHeight: vvHeight,
      windowInnerHeight: wHeight,
      preferVisibleViewportHeight,
    });

    return {
      heightCssValue: visibleViewportHeightCssValue,
      offsetTopCssValue: null,
      keyboardInsetCssValue: null,
      keyboardOpen: false,
    };
  }

  const roundedHeight = Math.round(vvHeight);
  const roundedOffsetTop = Math.max(0, Math.round(offsetTop));

  return {
    heightCssValue: `${roundedHeight}px`,
    offsetTopCssValue: roundedOffsetTop > 0 ? `${roundedOffsetTop}px` : null,
    keyboardInsetCssValue: `${Math.max(
      0,
      Math.round(wHeight) - roundedHeight - roundedOffsetTop,
    )}px`,
    keyboardOpen: true,
  };
}

function parsePixelValue(value: string | null | undefined): number | null {
  if (!value || !value.endsWith("px")) {
    return null;
  }

  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function shouldUpdateAppViewportHeight(
  previousValue: string | null | undefined,
  nextValue: string | null,
): boolean {
  if (previousValue === nextValue) return false;
  if (previousValue == null || nextValue == null) return true;

  const previousPx = parsePixelValue(previousValue);
  const nextPx = parsePixelValue(nextValue);

  if (previousPx === null || nextPx === null) {
    return previousValue !== nextValue;
  }

  return Math.abs(nextPx - previousPx) > 2;
}
