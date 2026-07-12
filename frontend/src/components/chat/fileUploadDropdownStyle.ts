import type { CSSProperties } from "react";

const UPLOAD_DROPDOWN_WIDTH = 208;
const UPLOAD_DROPDOWN_GUTTER = 8;

export function getFileUploadDropdownStyle(
  rect: DOMRect,
  {
    viewportWidth,
    viewportHeight,
  }: {
    viewportWidth: number;
    viewportHeight: number;
  },
): CSSProperties {
  const width = Math.min(
    UPLOAD_DROPDOWN_WIDTH,
    Math.max(0, viewportWidth - UPLOAD_DROPDOWN_GUTTER * 2),
  );
  const left = Math.max(
    UPLOAD_DROPDOWN_GUTTER,
    Math.min(rect.left, viewportWidth - width - UPLOAD_DROPDOWN_GUTTER),
  );
  return {
    position: "fixed",
    bottom: viewportHeight - rect.top + 8,
    left,
    width,
    zIndex: 9999,
  };
}
