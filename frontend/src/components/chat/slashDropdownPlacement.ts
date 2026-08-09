export type AnchoredSlashDropdownPlacement = {
  left: number;
  width: number;
  maxHeight: number;
  top?: number;
  bottom?: number;
};

export function getAnchoredSlashDropdownPlacement(
  anchorRect: Pick<DOMRect, "left" | "top" | "bottom">,
  viewportWidth: number,
  viewportHeight: number,
  preferredHeight = 320,
  preferredWidth = 320,
  viewportMargin = 8,
): AnchoredSlashDropdownPlacement {
  const anchorGap = 6;
  const width = Math.min(
    preferredWidth,
    Math.max(0, viewportWidth - viewportMargin * 2),
  );
  const left = Math.max(
    viewportMargin,
    Math.min(anchorRect.left, viewportWidth - width - viewportMargin),
  );
  const viewportMaxHeight = Math.max(0, viewportHeight - viewportMargin * 2);
  const desiredHeight = Math.min(preferredHeight, viewportMaxHeight);
  const spaceBelow =
    viewportHeight - anchorRect.bottom - anchorGap - viewportMargin;
  const spaceAbove = anchorRect.top - anchorGap - viewportMargin;

  if (spaceBelow >= desiredHeight) {
    return {
      left,
      top: anchorRect.bottom + anchorGap,
      width,
      maxHeight: desiredHeight,
    };
  }
  if (spaceAbove >= desiredHeight) {
    return {
      left,
      bottom: viewportHeight - anchorRect.top + anchorGap,
      width,
      maxHeight: desiredHeight,
    };
  }

  const preferredTop =
    spaceBelow >= spaceAbove
      ? anchorRect.bottom + anchorGap
      : anchorRect.top - anchorGap - desiredHeight;
  return {
    left,
    top: Math.max(
      viewportMargin,
      Math.min(preferredTop, viewportHeight - desiredHeight - viewportMargin),
    ),
    width,
    maxHeight: desiredHeight,
  };
}
