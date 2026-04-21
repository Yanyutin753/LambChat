export function getAppViewportHeightCssValue({
  visualViewportHeight,
  windowInnerHeight,
}: {
  visualViewportHeight?: number | null;
  windowInnerHeight?: number | null;
}): string {
  const measuredHeight = visualViewportHeight ?? windowInnerHeight;
  if (!measuredHeight || measuredHeight <= 0) {
    return "100dvh";
  }

  return `${Math.round(measuredHeight)}px`;
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
  nextValue: string,
): boolean {
  const previousPx = parsePixelValue(previousValue);
  const nextPx = parsePixelValue(nextValue);

  if (previousPx === null || nextPx === null) {
    return previousValue !== nextValue;
  }

  return Math.abs(nextPx - previousPx) > 2;
}
