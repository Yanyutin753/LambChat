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
