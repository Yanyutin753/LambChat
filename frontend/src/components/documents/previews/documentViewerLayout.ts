const DOCUMENT_HORIZONTAL_PADDING = 40;

export function calculateDocumentFitScale(
  viewportWidth: number,
  naturalWidth: number,
  horizontalPadding = DOCUMENT_HORIZONTAL_PADDING,
): number {
  if (viewportWidth <= 0 || naturalWidth <= 0) return 1;
  return Math.min(
    1,
    Math.max(0.1, (viewportWidth - horizontalPadding) / naturalWidth),
  );
}
